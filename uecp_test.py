import asyncio
import itertools
from asyncio import StreamWriter

from uecp.commands import ProgrammeServiceNameSetCommand
from uecp.frame import UECPFrame

from scheduler import config
from scheduler.rds import open_serial_writer

sequence_number = itertools.cycle(range(1, 256))


async def set_rds_encoder_state(uecp_writer: StreamWriter):
    for programme in itertools.cycle(
        [
            "R-AKTIV",
            "bermuda",
        ]
    ):
        print(f"Set ps to {programme}")
        command = ProgrammeServiceNameSetCommand(ps=programme)

        frame = UECPFrame()
        frame.sequence_counter = next(sequence_number)
        frame.add_command(command)

        data = frame.encode()
        uecp_writer.write(data)
        print(data.hex())
        await asyncio.wait_for(uecp_writer.drain(), 10)
        await asyncio.sleep(15)


async def main():
    uecp_writer = await open_serial_writer(
        config.UECP_SERIAL_PORT, config.UECP_SERIAL_BAUDRATE
    )
    await set_rds_encoder_state(uecp_writer)


if __name__ == "__main__":
    asyncio.run(main(), debug=True)
