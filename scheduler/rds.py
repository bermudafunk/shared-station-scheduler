import asyncio
import logging
from asyncio import StreamReader, StreamWriter

import serial
from serial_asyncio import open_serial_connection

logger = logging.getLogger(__name__)


async def drain_reader(reader: StreamReader):
    while data := await reader.read():
        logger.warning(f"Received some data via serial port: {data!r}")


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
