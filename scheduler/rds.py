from asyncio import StreamWriter

import serial
from serial_asyncio import open_serial_connection


async def open_serial_writer(port: str, baudrate: int) -> StreamWriter:
    _, writer = await open_serial_connection(
        url=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )
    return writer
