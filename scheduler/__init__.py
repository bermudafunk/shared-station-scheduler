import asyncio
import logging
import time
import typing

import aiohttp
from uecp.commands import DataSetSelectCommand
from uecp.frame import UECPFrame

from scheduler import config
from scheduler.calendar_provider import Programme, ProgrammeEventProvider
from scheduler.rds import open_dummy_writer, open_serial_writer

logger = logging.getLogger(__name__)


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

        self._event_changed_signal = asyncio.Event()

        self._pep.active_event_observers += [
            self._event_changed_signal.set,
            self.set_once,
            self.ensure_tasks,
        ]
        self._pep.next_change_event_observers += [
            self._event_changed_signal.set,
            self.ensure_tasks,
        ]

    @classmethod
    async def create(cls, enable_uecp=config.UECP_SERIAL_ENABLE) -> "Main":
        programme_event_provider = await ProgrammeEventProvider.create(
            config.CALENDAR_URL, config.TIMEZONE
        )
        uecp_writer = (
            await open_serial_writer(
                config.UECP_SERIAL_PORT, config.UECP_SERIAL_BAUDRATE
            )
            if enable_uecp
            else open_dummy_writer()
        )

        self = cls(programme_event_provider, uecp_writer)
        self.ensure_tasks()

        return self

    def set_once(self):
        return [
            asyncio.create_task(self.set_rds_encoder_state()),
            asyncio.create_task(self.set_solus_selector_state()),
        ]

    def ensure_tasks(self):
        logger.debug("Ensure tasks")
        if self._pep.active_event:
            if (
                self.ensure_rds_encoder_state_task is None
                or self.ensure_rds_encoder_state_task.done()
            ):
                logger.debug("Create ensure rds encoder state task")
                self.ensure_rds_encoder_state_task = asyncio.create_task(
                    self.ensure_rds_encoder_state()
                )
            if (
                self.ensure_solus_selector_state_task is None
                or self.ensure_solus_selector_state_task.done()
            ):
                logger.debug("Create ensure solus selector state task")
                self.ensure_solus_selector_state_task = asyncio.create_task(
                    self.ensure_solus_selector_state()
                )
        else:
            if self.ensure_rds_encoder_state_task is not None:
                logger.debug("Cancel ensure rds encoder state task")
                try:
                    self.ensure_rds_encoder_state_task.cancel()
                except Exception as e:
                    logger.debug(
                        f"Exception during canceling ensure rds encoder state task: {e!r}"
                    )
                finally:
                    self.ensure_rds_encoder_state_task = None
            if self.ensure_solus_selector_state_task is not None:
                logger.debug("Cancel ensure solus selector state task")
                try:
                    self.ensure_solus_selector_state_task.cancel()
                except Exception as e:
                    logger.debug(
                        f"Exception during canceling solus selector state task {e!r}"
                    )
                finally:
                    self.ensure_solus_selector_state_task = None

        if self._pep.next_change_event:
            if (
                self.change_on_change_event_task is None
                or self.change_on_change_event_task.done()
            ):
                logger.debug("Create change on change event task")
                self.change_on_change_event_task = asyncio.create_task(
                    self.change_on_change_event()
                )
        else:
            if self.change_on_change_event_task is not None:
                logger.debug("Cancel change on change event task")
                try:
                    self.change_on_change_event_task.cancel()
                except Exception as e:
                    logger.debug(
                        f"Exception occured during canceling change on change event task {e!r}"
                    )
                finally:
                    self.change_on_change_event_task = None

    async def set_rds_encoder_state(self):
        if not self._pep.active_event:
            logger.debug("Setting rds encoder: No active event!?")
            return
        try:
            programme = Programme[self._pep.active_event.summary]
            logger.debug(f"Set active dataset to {programme}")
            rds_dataset = programme.rds_dataset
            command = DataSetSelectCommand(select_data_set_number=rds_dataset)

            frame = UECPFrame()
            frame.add_command(command)

            self._uecp_writer.write(frame.encode())
            await asyncio.wait_for(self._uecp_writer.drain(), 10)
        except Exception as e:
            logger.debug(f"During setting the rds data set an error occurred {e!r}")

    async def ensure_rds_encoder_state(self):
        try:
            while True:
                await self.set_rds_encoder_state()
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.debug("Canceled ensure rds encoder state")

    async def set_solus_selector_state(self):
        if not self._pep.active_event:
            logger.debug("Setting solus selector: No active event!?")
            return
        programme = Programme[self._pep.active_event.summary]
        logger.debug(f"Set active selector to {programme}")
        selector_value = programme.solus_selector
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            ) as session:
                await session.post(
                    config.UKW_SELECTOR_URL,
                    json={"position": selector_value},
                )
        except Exception as e:
            logger.debug(f"During setting the selector an error occurred {e!r}")

    async def ensure_solus_selector_state(self):
        try:
            while True:
                await self.set_solus_selector_state()
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.debug("Canceled solus selector state")

    async def change_on_change_event(self):
        try:
            while (event := self._pep.next_change_event) is not None:
                self._event_changed_signal.clear()
                time_to_sleep = event.time_left().total_seconds()
                if time_to_sleep < 0.5:
                    time.sleep(time_to_sleep - 0.003)
                    await asyncio.wait(self.set_once())
                else:
                    time_to_sleep -= 0.5
                    time_to_sleep = min(3500, time_to_sleep)
                    logger.debug(f"Sleeping now {time_to_sleep} seconds")
                    done, pending = await asyncio.wait(
                        [
                            asyncio.create_task(asyncio.sleep(time_to_sleep)),
                            asyncio.create_task(self._event_changed_signal.wait()),
                        ],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()
        except asyncio.CancelledError:
            logger.debug("Canceled change on change event")
