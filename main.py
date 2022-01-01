import asyncio
import time
import typing

import aiohttp
from uecp.commands import DataSetSelectCommand, RDSEnabledSetCommand
from uecp.frame import UECPFrame

from scheduler import config
from scheduler.calendar_provider import Programme, ProgrammeEventProvider
from scheduler.rds import open_serial_writer


class Main:
    def __init__(
        self,
        programme_event_provider: ProgrammeEventProvider,
        uecp_writer: asyncio.StreamWriter,
    ):
        self._pep = programme_event_provider
        self._uecp_writer = uecp_writer

        self.ensure_rds_encoder_state_task: typing.Optional[asyncio.Task] = None
        self.ensure_solus_selector_state_task: typing.Optional[asyncio.Task] = None
        self.change_on_change_event_task: typing.Optional[asyncio.Task] = None

    @classmethod
    async def create(cls) -> "Main":
        programme_event_provider = await ProgrammeEventProvider.create(
            config.CALENDAR_URL, config.TIMEZONE
        )
        uecp_writer = await open_serial_writer(
            config.UECP_SERIAL_PORT, config.UECP_SERIAL_BAUDRATE
        )

        self = cls(programme_event_provider, uecp_writer)
        self.ensure_tasks()

        return self

    def ensure_tasks(self):
        if self._pep.active_event:
            if (
                self.ensure_rds_encoder_state_task is None
                or self.ensure_rds_encoder_state_task.done()
            ):
                self.ensure_rds_encoder_state_task = asyncio.create_task(
                    self.ensure_rds_encoder_state()
                )
            if (
                self.ensure_solus_selector_state_task is None
                or self.ensure_solus_selector_state_task.done()
            ):
                self.ensure_solus_selector_state_task = asyncio.create_task(
                    self.ensure_solus_selector_state()
                )
        else:
            if self.ensure_rds_encoder_state_task is not None:
                self.ensure_rds_encoder_state_task.cancel()
                self.ensure_rds_encoder_state_task.result()
                self.ensure_rds_encoder_state_task = None
            if self.ensure_solus_selector_state_task is not None:
                self.ensure_solus_selector_state_task.cancel()
                self.ensure_solus_selector_state_task.result()
                self.ensure_solus_selector_state_task = None

        if self._pep.next_change_event:
            if (
                self.change_on_change_event_task is None
                or self.change_on_change_event_task.done()
            ):
                self.change_on_change_event_task = asyncio.create_task(
                    self.change_on_change_event()
                )
        else:
            if self.change_on_change_event_task is not None:
                self.change_on_change_event_task.cancel()
                self.change_on_change_event_task.result()
                self.change_on_change_event_task = None

    async def set_rds_encoder_state(self):
        rds_dataset = Programme[self._pep.active_event.summary].rds_dataset
        command = DataSetSelectCommand(select_data_set_number=rds_dataset)

        frame = UECPFrame()
        frame.add_command(command)

        self._uecp_writer.write(frame.encode())
        await self._uecp_writer.drain()

    async def rds_on_off(self, enable):
        frame = UECPFrame()
        frame.add_command(RDSEnabledSetCommand(enable=enable))

        self._uecp_writer.write(frame.encode())
        await self._uecp_writer.drain()

    async def ensure_rds_encoder_state(self):
        try:
            while True:
                await self.rds_on_off(False)
                await asyncio.sleep(5)
                await self.rds_on_off(True)
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass

    async def set_solus_selector_state(self):
        selector_value = Programme[self._pep.active_event.summary].solus_selector
        async with aiohttp.ClientSession() as session:
            await session.post(
                config.UKW_SELECTOR_URL,
                json={"position": selector_value},
            )

    async def ensure_solus_selector_state(self):
        try:
            while True:
                await self.set_solus_selector_state()
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass

    async def change_on_change_event(self):
        try:
            while (event := self._pep.next_change_event) is not None:
                time_to_sleep = event.time_left().total_seconds()
                if time_to_sleep < 0.5:
                    time.sleep(time_to_sleep)
                    await asyncio.gather(
                        self.set_rds_encoder_state(), self.set_solus_selector_state()
                    )
                else:
                    time_to_sleep = min(3600, time_to_sleep)
                    await asyncio.sleep(time_to_sleep)
        except asyncio.CancelledError:
            pass


async def main():
    main = await Main.create()

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
