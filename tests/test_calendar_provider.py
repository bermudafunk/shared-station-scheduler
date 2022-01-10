import asyncio
import functools
from datetime import datetime

import pytest
from dateutil.tz import gettz
from pytest_httpserver import HTTPServer

from scheduler import calendar_provider

tz = gettz("Europe/Berlin")


def now(static_now: datetime):
    def deco(func):
        original_now = calendar_provider._now

        def custom_now(*_, **__):
            return static_now

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            calendar_provider._now = custom_now
            await func(*args, **kwargs)
            calendar_provider._now = original_now

        return wrapper

    return deco


class TestProgrammeEventProvider:
    @now(datetime(2021, 12, 11, 14, 23, 00, tzinfo=tz))
    @pytest.mark.asyncio
    async def test_pep(self, shared_datadir, httpserver: HTTPServer):
        content = (shared_datadir / "test_ics_1").read_text()
        httpserver.expect_request("/ics").respond_with_data(content)

        pep = await calendar_provider.ProgrammeEventProvider.create(
            ics_url=httpserver.url_for("/ics"), tz=tz
        )
        ev = pep.active_event
        assert ev.start == datetime(2021, 12, 11, 00, 00, 00, tzinfo=tz)
        assert ev.end == datetime(2021, 12, 12, 00, 00, 00, tzinfo=tz)

        ev = pep.next_change_event

        assert ev.start == datetime(2021, 12, 12, 20, 00, 00, tzinfo=tz)
        assert ev.end == datetime(2021, 12, 12, 22, 00, 00, tzinfo=tz)

        pep.refreshEventTask.cancel()
        try:
            await pep.refreshEventTask
        except asyncio.CancelledError:
            pass

    @now(datetime(2022, 1, 10, 10, 10, 00, tzinfo=tz))
    @pytest.mark.asyncio
    async def test_pep2(self, shared_datadir, httpserver: HTTPServer):
        content = (shared_datadir / "test_ics_2").read_text()
        httpserver.expect_request("/ics").respond_with_data(content)

        pep = await calendar_provider.ProgrammeEventProvider.create(
            ics_url=httpserver.url_for("/ics"), tz=tz
        )

        ev = pep.active_event
        assert ev.start == datetime(2022, 1, 10, 8, 0, 0, tzinfo=tz)
        assert ev.end == datetime(2022, 1, 10, 10, 15, 0, tzinfo=tz)
        assert ev.summary == "radioaktiv"

        ev = pep.next_change_event
        assert ev.start == datetime(2022, 1, 10, 10, 15, 0, tzinfo=tz)
        assert ev.end == datetime(2022, 1, 10, 12, 0, 0, tzinfo=tz)
        assert ev.summary == "bermudafunk"

        pep.refreshEventTask.cancel()
        try:
            await pep.refreshEventTask
        except asyncio.CancelledError:
            pass
