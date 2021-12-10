import enum
import typing
from datetime import datetime, tzinfo

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


def check_continuous_monotonic_events(events: list[Event]) -> bool:
    for a, b in pairwise(events):  # type: Event, Event
        if not a.end == b.start:
            return False
        if a.start == a.end:
            return False
    return True


def check_events_matching_programmes(events: list[Event]) -> bool:
    return all(event.summary.lower() in programme_names for event in events)


def validate_events(events: list[Event]) -> bool:
    return check_events_matching_programmes(
        events
    ) and check_continuous_monotonic_events(events)


class ProgrammeEventProvider:
    def __init__(self, ics_url: str, tz: tzinfo):
        self.__ics_url = str(ics_url)
        self.__tz = tz

    @property
    def ics_url(self) -> str:
        return self.__ics_url

    @property
    def tz(self) -> tzinfo:
        return self.__tz

    def _load_events(self, start: datetime = None, end: datetime = None) -> list[Event]:
        return icalevents.events(url=self.__ics_url, start=start, end=end)

    def get_active_event(self, now: datetime = None):
        now = now if now else datetime.now(self.__tz)
        events = self._load_events(start=now)
        for event in events:
            if event.start <= now <= event.end:
                return event
        raise Exception(f"No active event {now}")

    def get_next_real_change_event(
        self, now: datetime = None
    ) -> typing.Optional[Event]:
        now = now if now else datetime.now(self.__tz)

        current_event = self.get_active_event(now=now)
        events = self._load_events(start=now)
        for event in events:
            if (
                current_event.end <= event.start
                and event.summary != current_event.summary
            ):
                return event

        return None
