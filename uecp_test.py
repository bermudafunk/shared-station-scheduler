import asyncio
import itertools
from asyncio import StreamWriter

from uecp.commands import ProgrammeServiceNameSetCommand, RadioTextSetCommand
from uecp.frame import UECPFrame

from scheduler import config
from scheduler.rds import open_serial_writer

sequence_number = itertools.cycle(range(1, 256))
a_b_toggle = itertools.cycle([True, False])


async def set_rds_encoder_state(uecp_writer: StreamWriter):
    for programme in itertools.cycle(
        [
            ("R-AKTIV", "radioaktiv ist Hip"),
            ("bermuda", "bermudafunk ist auch Hip"),
        ]
    ):
        print(f"Set ps to {programme}")
        command = ProgrammeServiceNameSetCommand(ps=programme[0])

        frame = UECPFrame()
        frame.sequence_counter = next(sequence_number)
        frame.add_command(command)
        frame.add_command(
            RadioTextSetCommand(text=programme[1], a_b_toggle=next(a_b_toggle))
        )

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
