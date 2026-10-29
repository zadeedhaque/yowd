"""Melbourne time zone and the clocks that implement the Clock port.

The prototype implements Victoria's daylight-saving rule itself instead
of relying on the operating system's time-zone database, so it gives the
same answers on Windows, Linux, macOS and in the browser (SRS P8).
"""

from datetime import date, datetime, timedelta, timezone, tzinfo

from yowd.domain.ports import Clock


class MelbourneTimezone(tzinfo):
    """Australia/Melbourne: AEST (UTC+10), AEDT (UTC+11) in summer.

    Daylight saving starts at 02:00 standard time on the first Sunday in
    October and ends at 03:00 daylight time on the first Sunday in April.
    """

    __STANDARD = timedelta(hours=10)
    __HOUR = timedelta(hours=1)

    def utcoffset(self, moment: datetime | None) -> timedelta:
        """Offset from UTC for a local Melbourne time."""
        return self.__STANDARD + self.dst(moment)

    def dst(self, moment: datetime | None) -> timedelta:
        """Daylight-saving adjustment for a local time."""
        if moment is None:
            return timedelta(0)
        local = moment.replace(tzinfo=None)
        start = datetime.combine(self.__first_sunday(local.year, 10),
                                 datetime.min.time()) + timedelta(hours=2)
        end = datetime.combine(self.__first_sunday(local.year, 4),
                               datetime.min.time()) + timedelta(hours=2)
        in_summer = local >= start or local < end
        return self.__HOUR if in_summer else timedelta(0)

    def tzname(self, moment: datetime | None) -> str:
        """AEDT in summer, otherwise AEST."""
        return "AEDT" if self.dst(moment) else "AEST"

    def fromutc(self, moment: datetime) -> datetime:
        """Convert a UTC time (tagged with this zone) to local time."""
        utc = moment.replace(tzinfo=None)
        start = datetime.combine(self.__first_sunday(utc.year, 10),
                                 datetime.min.time()) - timedelta(hours=8)
        end = datetime.combine(self.__first_sunday(utc.year, 4),
                               datetime.min.time()) - timedelta(hours=8)
        in_summer = utc >= start or utc < end
        offset = self.__STANDARD + (self.__HOUR if in_summer
                                    else timedelta(0))
        return (utc + offset).replace(tzinfo=self)

    def __repr__(self) -> str:
        return "MelbourneTimezone()"

    @staticmethod
    def __first_sunday(year: int, month: int) -> date:
        first = date(year, month, 1)
        return first + timedelta(days=(6 - first.weekday()) % 7)


MELBOURNE = MelbourneTimezone()


class SystemClock(Clock):
    """The real clock, in Melbourne local time."""

    def now(self) -> datetime:
        """Current time, to the second."""
        return datetime.now(timezone.utc).astimezone(MELBOURNE).replace(
            microsecond=0)


class FixedClock(Clock):
    """A clock that only moves when told to (tests and demos)."""

    __slots__ = ("__now",)

    def __init__(self, fixed: datetime) -> None:
        self.__now = fixed

    def now(self) -> datetime:
        """Return the set time."""
        return self.__now

    def advance(self, **kwargs: float) -> None:
        """Move forward, e.g. ``advance(minutes=20)``."""
        self.__now = self.__now + timedelta(**kwargs)
