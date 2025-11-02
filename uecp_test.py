import asyncio
import itertools
from asyncio import StreamWriter

from uecp.commands import RadioTextBufferConfiguration, RadioTextSetCommand
from uecp.frame import UECPFrame

from scheduler import config
from scheduler.rds import open_serial_writer

a_b_toggle = itertools.cycle([True, False])


async def set_rds_encoder_state(uecp_writer: StreamWriter):
    frame = UECPFrame()
    frame.add_command(
        RadioTextSetCommand(
            text="radioaktiv - Campusradio Rhein-Neckar e.V.",
            number_of_transmissions=10,
            a_b_toggle=False,
        ),
        RadioTextSetCommand(
            text="radioaktiv - Dein Abend!",
            number_of_transmissions=10,
            a_b_toggle=True,
            buffer_configuration=RadioTextBufferConfiguration.APPEND,
        ),
    )

    data = frame.encode()
    uecp_writer.write(data)
    print(data.hex())
    await asyncio.wait_for(uecp_writer.drain(), 10)


async def main():
    uecp_writer = await open_serial_writer(
        config.UECP_SERIAL_PORT, config.UECP_SERIAL_BAUDRATE
    )
    await set_rds_encoder_state(uecp_writer)


if __name__ == "__main__":
    asyncio.run(main(), debug=True)
