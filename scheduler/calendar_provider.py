import asyncio
import enum
import logging
import typing
from asyncio import CancelledError
from datetime import datetime, timedelta, tzinfo

import prometheus_client
from dateutil.relativedelta import MO, relativedelta
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


logger = logging.getLogger(__name__)


Event__eq__attributes = (
    "uid",
    "summary",
    "description",
    "start",
    "end",
    "all_day",
    "recurring",
    "location",
    "private",
    "created",
    "last_modified",
    "sequence",
    "attendee",
    "organizer",
)


def Event__eq__(self: Event, other) -> bool:
    if not isinstance(other, Event):
        return NotImplemented

    return all(
        getattr(self, attribute) == getattr(other, attribute)
        for attribute in Event__eq__attributes
    )


Event.__eq__ = Event__eq__


@enum.unique
class Programme(enum.Enum):
    bermudafunk = ("bermudafunk", 1, 1)
    radioaktiv = ("radioaktiv", 2, 2)

    def __new__(cls, name, rds_dataset, solus_selector):
        obj = object.__new__(cls)
        obj._value_ = name
        obj._rds_dataset = rds_dataset
        obj._solus_selector = solus_selector

        return obj

    @property
    def rds_dataset(self) -> int:
        return self._rds_dataset

    @property
    def solus_selector(self) -> int:
        return self._solus_selector


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
    RELOAD_INTERVAL = timedelta(minutes=5)
    RELOAD_RETRY_ON_ERROR = timedelta(seconds=10)

    refreshEventTask: asyncio.Task

    ACTIVE_EVENT = prometheus_client.Enum(
        "calendar_active_event",
        "Active event",
        states=[p.name for p in Programme] + ["none"],
    )
    NEXT_CHANGE_EVENT = prometheus_client.Enum(
        "calendar_next_change_event",
        "Next change event",
        states=[p.name for p in Programme] + ["none"],
    )
    REFRESH_TRIES_TOTAL = prometheus_client.Counter(
        "calendar_refresh_tries", "Method calls to refresh"
    )
    REFRESH_SUCCESSFUL_TOTAL = prometheus_client.Counter(
        "calendar_refresh", "Method calls to refresh successfully"
    )
    REFRESH_FAILURE_TOTAL = prometheus_client.Counter(
        "calendar_refresh_failures", "Refresh failures"
    )

    AIRTIME_SECONDS = prometheus_client.Gauge(
        "calendar_airtime_seconds",
        "Airtime of each programm in two weeks",
        ["programme"],
    )
    AIRTIME_START = prometheus_client.Gauge(
        "calendar_airtime_start_seconds", "Airtime calculation start seconds"
    )
    AIRTIME_STOP = prometheus_client.Gauge(
        "calendar_airtime_stop_seconds", "Airtime calculation start seconds"
    )

    @classmethod
    async def create(cls, ics_url: str, tz: tzinfo):
        self = cls(ics_url=ics_url, tz=tz)
        await self.refresh_events()
        self.refreshEventTask = asyncio.create_task(self.refresh_event_loop())
        return self

    def __init__(
        self,
        ics_url: str,
        tz: tzinfo,
    ):
        self._ics_url = ics_url
        self._tz = tz

        self._events: list[Event] = []

        self._active_event: typing.Optional[Event] = None
        self._next_change_event: typing.Optional[Event] = None

        self._last_load: datetime = self._now()

        self.active_event_observers: list[typing.Callable[[], None]] = []
        self.next_change_event_observers: list[typing.Callable[[], None]] = []

    def _now(self) -> datetime:
        return _now(self._tz)

    async def refresh_events(self):
        self.REFRESH_TRIES_TOTAL.inc()
        logger.debug("Refresh events")
        now = self._now()
        start = (
            now
            - relativedelta(
                weekday=MO, weeks=1, hour=0, minute=0, second=0, microsecond=0
            )
            + timedelta.resolution
        )
        end = start + relativedelta(weekday=MO, weeks=2) - timedelta.resolution * 2

        events = await asyncio.to_thread(
            icalevents.events, url=self._ics_url, start=start, end=end
        )
        events = sorted(events)

        check_events_matching_programmes(events)
        check_continuous_monotonic_events(events)

        self._last_load = now
        self._events = events

        (
            old_active_event,
            self._active_event,
        ) = self._active_event, self._calc_active_event(events)
        self.ACTIVE_EVENT.state(
            self._active_event.summary if self._active_event else "none"
        )

        (
            old_next_change_event,
            self._next_change_event,
        ) = self._next_change_event, self._calc_next_change_event(events)
        self.NEXT_CHANGE_EVENT.state(
            self._next_change_event.summary if self._next_change_event else "none"
        )

        logger.debug(
            f"Old active event {old_active_event}, new active {self._active_event}"
        )
        if old_active_event != self._active_event:
            logger.debug("Calling active event observers")
            for observer in self.active_event_observers:
                observer()

        logger.debug(
            f"Old next change event {old_next_change_event}, new next change event {self._next_change_event}"
        )
        if old_next_change_event != self._next_change_event:
            logger.debug("Calling next change event observers")
            for observer in self.next_change_event_observers:
                observer()

        logger.debug("Refreshed events")
        self.calc_airtime_distribution()

        self.REFRESH_SUCCESSFUL_TOTAL.inc()

    async def refresh_event_loop(self):
        while True:
            try:
                await self.refresh_events()
                time_to_sleep = self.RELOAD_INTERVAL - (self._now() - self._last_load)
                if time_to_sleep.total_seconds() < 1:
                    time_to_sleep = timedelta(seconds=1)
                logger.debug(f"Sleeping {time_to_sleep} between refreshing events")
                await asyncio.sleep(time_to_sleep.total_seconds())
            except CancelledError:
                return
            except Exception as e:
                logger.error(f"Error happened during refreshing events {e!r}")
                self.REFRESH_FAILURE_TOTAL.inc()
                await asyncio.sleep(self.RELOAD_RETRY_ON_ERROR.total_seconds())

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    @property
    def active_event(self) -> typing.Optional[Event]:
        self._active_event = self._calc_active_event(self._events)
        return self._active_event

    @property
    def next_change_event(self) -> typing.Optional[Event]:
        self._next_change_event = self._calc_next_change_event(self._events)
        return self._next_change_event

    def _calc_active_event(
        self, events: list[Event], now: datetime = None
    ) -> typing.Optional[Event]:
        now = now or self._now()
        for event in events:
            if event.start <= now <= event.end:
                return event
        return None

    def _calc_next_change_event(
        self, events: list[Event], now: datetime = None
    ) -> typing.Optional[Event]:
        now = now or self._now()

        current_event = self._calc_active_event(events=events, now=now)
        if current_event is None:
            return events[0]
        for event in events:
            if (
                current_event.end <= event.start
                and event.summary != current_event.summary
            ):
                return event

        return None

    def calc_airtime_distribution(self):
        airtime_by_programme = {p: timedelta() for p in Programme}
        events = self.events

        for event in events:
            airtime_by_programme[Programme[event.summary]] += event.end - event.start

        for programme, airtime in airtime_by_programme.items():
            self.AIRTIME_SECONDS.labels(programme.name).set(airtime.total_seconds())

        self.AIRTIME_START.set(events[0].start.timestamp())
        self.AIRTIME_STOP.set(events[-1].end.timestamp())
