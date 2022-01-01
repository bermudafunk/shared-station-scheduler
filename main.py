import asyncio
import functools
import signal
import time
import typing

import aiohttp
from uecp.commands import DataSetSelectCommand
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
        try:
            rds_dataset = Programme[self._pep.active_event.summary].rds_dataset
            command = DataSetSelectCommand(select_data_set_number=rds_dataset)

            frame = UECPFrame()
            frame.add_command(command)

            self._uecp_writer.write(frame.encode())
            await asyncio.wait_for(self._uecp_writer.drain(), 10)
        except Exception as e:
            print(f"During setting the rds data set an error occurred {e!r}")

    async def ensure_rds_encoder_state(self):
        try:
            while True:
                await self.set_rds_encoder_state()
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass

    async def set_solus_selector_state(self):
        selector_value = Programme[self._pep.active_event.summary].solus_selector
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            ) as session:
                await session.post(
                    config.UKW_SELECTOR_URL,
                    json={"position": selector_value},
                )
        except Exception as e:
            print(f"During setting the selector an error occurred {e!r}")

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
    def ask_exit(signame):
        print("got signal %s: exit" % signame)
        for task in asyncio.all_tasks():
            task.cancel()

    loop = asyncio.get_running_loop()

    for signame in {"SIGINT", "SIGTERM"}:
        loop.add_signal_handler(
            getattr(signal, signame), functools.partial(ask_exit, signame)
        )

    main = await Main.create()

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
