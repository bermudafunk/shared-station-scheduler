import asyncio
import functools
from datetime import datetime

import icalevents
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

    @now(datetime(2022, 1, 11, 7, 0, 1, tzinfo=tz))
    @pytest.mark.asyncio
    async def test_pep3(self, shared_datadir, httpserver: HTTPServer):
        content = (shared_datadir / "test_ics_3").read_text()
        httpserver.expect_request("/ics").respond_with_data(content)

        ccme = calendar_provider.check_continuous_monotonic_events

        def null_op(*_, **__):
            pass

        calendar_provider.check_continuous_monotonic_events = null_op

        pep = await calendar_provider.ProgrammeEventProvider.create(
            ics_url=httpserver.url_for("/ics"), tz=tz
        )

        assert pep.active_event is not None

        calendar_provider.check_continuous_monotonic_events = ccme

    def test_icalevents(self):
        from datetime import datetime
        import textwrap
        import zoneinfo

        tz = zoneinfo.ZoneInfo("Europe/Berlin")
        ics = textwrap.dedent(
            """\
        BEGIN:VCALENDAR
        VERSION:2.0
        BEGIN:VTIMEZONE
        TZID:Europe/Berlin
        BEGIN:STANDARD
        DTSTART:19701025T030000
        RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10
        TZNAME:CET
        TZOFFSETFROM:+0200
        TZOFFSETTO:+0100
        END:STANDARD
        BEGIN:DAYLIGHT
        DTSTART:19700329T020000
        RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=3
        TZNAME:CEST
        TZOFFSETFROM:+0100
        TZOFFSETTO:+0200
        END:DAYLIGHT
        END:VTIMEZONE
        BEGIN:VEVENT
        DTSTART;TZID=Europe/Berlin:20211129T000000
        DTEND;TZID=Europe/Berlin:20211129T080000
        RRULE:FREQ=WEEKLY;UNTIL=20221230T230000Z;BYDAY=MO,TU,WE
        END:VEVENT
        END:VCALENDAR
        """
        ).encode()

        events = icalevents.icalevents.events(
            string_content=ics,
            start=datetime(2022, 1, 11, 7, 59, 59, tzinfo=tz),
            end=datetime(2022, 1, 11, 10, 0, 1, tzinfo=tz),
        )
        assert len(events) == 1
