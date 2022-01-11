import asyncio
import functools
import logging
import signal

from prometheus_async.aio.web import start_http_server

from scheduler import Main
from scheduler.logging_stats import export_root_logger_stats

logging.basicConfig(
    format="%(asctime)s : %(levelname)8s : %(funcName)-20s : %(lineno)4d : %(message)s",
    level=logging.DEBUG,
)

export_root_logger_stats()


async def main():
    def ask_exit(signame):
        logging.debug("got signal %s: exit" % signame)
        for task in asyncio.all_tasks():
            task.cancel()

    loop = asyncio.get_running_loop()

    for signame in {"SIGINT", "SIGTERM"}:
        loop.add_signal_handler(
            getattr(signal, signame), functools.partial(ask_exit, signame)
        )

    exporter = await start_http_server(port=9530)
    main = await Main.create()

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main(), debug=True)
