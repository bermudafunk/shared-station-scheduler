import asyncio
import enum
import typing
from asyncio import CancelledError
from datetime import datetime, timedelta, tzinfo

from icalevents import icalevents
from icalevents.icalparser import Event

try:
    from itertools import pairwise
except ImportError:

    def pairwise(iterable):
        from itertools import tee

        a, b = tee(iterable)
        next(b, None)
        return zip(a, b)


@enum.unique
class Programme(enum.Enum):
    bermudafunk = enum.auto()
    radioaktiv = enum.auto()


programme_names = {programme.name.lower() for programme in set(Programme)}


def _now(tz: tzinfo = None) -> datetime:
    return datetime.now(tz)


def check_events_matching_programmes(events: list[Event]):
    for event in events:
        if event.summary.lower() not in programme_names:
            raise Exception(f"unknown event {event}")


def check_continuous_monotonic_events(events: list[Event]):
    for a, b in pairwise(events):  # type: Event, Event
        if not a.end == b.start:
            raise Exception(f"non continuous events detected {a} {b}")
        if a.start == a.end:
            raise Exception(f"events duration zero {a}")


class ProgrammeEventProvider:
    DEFAULT_SPAN = timedelta(days=14)

    RELOAD_INTERVAL = timedelta(minutes=5)
    RELOAD_RETRY_ON_ERROR = timedelta(seconds=30)

    @classmethod
    async def create(cls, ics_url: str, tz: tzinfo):
        self = cls(ics_url=ics_url, tz=tz)
        await self.refresh_events()
        return self

    def __init__(
        self,
        ics_url: str,
        tz: tzinfo,
    ):
        self._ics_url = ics_url
        self._tz = tz

        self._events: list[Event] = []

        self._last_load: datetime = self._now()

    def _now(self) -> datetime:
        return _now(self._tz)

    async def refresh_events(self, start: datetime = None, end: datetime = None):
        start = start or self._now()
        end = end or (start + self.DEFAULT_SPAN)

        events = await asyncio.to_thread(
            icalevents.events, url=self._ics_url, start=start, end=end
        )
        events = sorted(events)

        if len(events) == 0:
            raise Exception("No events loaded")

        if not events[0].start <= start:
            raise Exception(f"No event active at start {start}, {events[0]}")

        if not events[-1].end >= end:
            raise Exception(f"No event active at end {end}, {events[-1]}")

        check_events_matching_programmes(events)
        check_continuous_monotonic_events(events)

        self._last_load = start
        self._events = events

    async def refresh_event_task(self):
        while True:
            try:
                await self.refresh_events()
                time_to_sleep = self.RELOAD_INTERVAL - (self._now() - self._last_load)
                await asyncio.sleep(time_to_sleep.total_seconds())
            except CancelledError:
                return
            except Exception as e:
                print(e)
                await asyncio.sleep(self.RELOAD_RETRY_ON_ERROR.total_seconds())

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    def get_active_event(self, now: datetime = None) -> Event:
        return self._get_active_event(events=self.events, now=now)

    def _get_active_event(self, events: list[Event], now: datetime = None) -> Event:
        now = now or self._now()
        events = events
        for event in events:
            if event.start <= now <= event.end:
                return event
        raise Exception(f"No active event {now}")

    def get_next_change_event(self, now: datetime = None) -> typing.Optional[Event]:
        return self._get_next_change_event(events=self.events, now=now)

    def _get_next_change_event(
        self, events: list[Event], now: datetime = None
    ) -> typing.Optional[Event]:
        now = now or self._now()

        current_event = self._get_active_event(events=events, now=now)
        for event in events:
            if (
                current_event.end <= event.start
                and event.summary != current_event.summary
            ):
                return event

        return None
