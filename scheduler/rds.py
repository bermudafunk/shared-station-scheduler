import asyncio
import logging
from asyncio import StreamReader, StreamWriter
from typing import Any, Iterable

import serial
from serial_asyncio import open_serial_connection

logger = logging.getLogger(__name__)


async def drain_reader(reader: StreamReader):
    while data := await reader.read(1):
        logger.debug(f"Received some data via serial port: {data!r}")


async def open_serial_writer(port: str, baudrate: int) -> StreamWriter:
    reader, writer = await open_serial_connection(
        url=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )
    asyncio.create_task(drain_reader(reader))
    return writer


class DummyStreamWriter(StreamWriter):
    def __init__(self, *_, **__) -> None:
        pass

    @property
    def transport(self):
        return None

    def write(self, data: bytes) -> None:
        logging.debug(data)

    def writelines(self, data: Iterable[bytes]) -> None:
        for d in data:
            logging.debug(d)

    def write_eof(self) -> None:
        logging.debug("DummyStreamWriter EOF")

    def can_write_eof(self) -> bool:
        return True

    def close(self) -> None:
        pass

    def is_closing(self) -> bool:
        return False

    async def wait_closed(self) -> None:
        pass

    def get_extra_info(self, name: str, default: Any = ...) -> Any:
        return None

    async def drain(self) -> None:
        pass


def open_dummy_writer() -> StreamWriter:
    return DummyStreamWriter()
