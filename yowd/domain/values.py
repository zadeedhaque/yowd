"""Value objects (A2 data holders): ContactDetails, TimeWindow, ReportPeriod.

Value objects are immutable: ``frozen=True`` dataclasses raise
``FrozenInstanceError`` on any assignment, which is how Python enforces
"read-only" without access modifiers.  Each one validates itself on
creation, so an invalid value can never exist in the domain.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from yowd.domain.clock import MELBOURNE
from yowd.domain.errors import ValidationError


@dataclass(frozen=True)
class ContactDetails:
    """Name, phone, email and preferred notification channel."""

    name: str
    phone: str
    email: str = ""
    preferred_channel: str = "SMS"

    _EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
    _AU_PHONE = re.compile(r"^(?:\+61|0)[2-478]\d{8}$")
    _CHANNELS = ("SMS", "Email")

    def __post_init__(self) -> None:
        name = (self.name or "").strip()
        if not name:
            raise ValidationError("Name cannot be blank. Please enter a "
                                  "name.")
        if len(name) > 60:
            raise ValidationError("Name must be 60 characters or fewer.")
        phone = self.normalise_phone(self.phone)
        if not self._AU_PHONE.match(phone):
            raise ValidationError(
                "Phone must be an Australian number, e.g. 0412 345 678 or "
                "03 9214 8000.")
        email = (self.email or "").strip().lower()
        if email and not self._EMAIL.match(email):
            raise ValidationError(
                "Email is not valid. Use the form name@example.com, or "
                "leave it blank.")
        if self.preferred_channel not in self._CHANNELS:
            raise ValidationError("Preferred channel must be SMS or Email.")
        # Normalised values are stored through object.__setattr__, the
        # documented way for a frozen dataclass to set its own fields.
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "phone", phone)
        object.__setattr__(self, "email", email)

    @staticmethod
    def normalise_phone(raw: str) -> str:
        """Strip spaces, dashes and brackets from a phone number."""
        return re.sub(r"[\s\-()]", "", raw or "")


@dataclass(frozen=True)
class TimeWindow:
    """A start and end time in Melbourne local time (SRS P8)."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValidationError("Times must include the Melbourne time "
                                  "zone.")
        if self.end <= self.start:
            raise ValidationError("The end time must be after the start "
                                  "time.")

    @classmethod
    def on_day(cls, day: date, start: time, end: time) -> "TimeWindow":
        """Build a window on ``day`` between two clock times."""
        return cls(datetime.combine(day, start, MELBOURNE),
                   datetime.combine(day, end, MELBOURNE))

    def covers(self, other: "TimeWindow") -> bool:
        """True if ``other`` lies completely inside this window."""
        return self.start <= other.start and other.end <= self.end

    def overlaps(self, other: "TimeWindow") -> bool:
        """True if the two windows share any time."""
        return self.start < other.end and other.start < self.end

    def shifted(self, delta: timedelta) -> "TimeWindow":
        """Return the same window moved by ``delta``."""
        return TimeWindow(self.start + delta, self.end + delta)

    def label(self) -> str:
        """Human readable form, e.g. 'Fri 30 Oct 10:00-12:00'."""
        if self.start.date() == self.end.date():
            return (f"{self.start:%a %d %b} {self.start:%H:%M}-"
                    f"{self.end:%H:%M}")
        return f"{self.start:%a %d %b %H:%M} - {self.end:%a %d %b %H:%M}"


class ReportPeriod:
    """A reporting period: day, week, month, year or year-to-date."""

    KINDS = ("day", "week", "month", "year", "ytd")
    __NAMES = {"day": "Day", "week": "Week", "month": "Month",
               "year": "Year", "ytd": "Year to date"}
    __slots__ = ("__kind", "__first", "__last")

    def __init__(self, kind: str, reference: date) -> None:
        if kind not in self.KINDS:
            raise ValidationError(
                "Period must be one of: day, week, month, year, ytd.")
        self.__kind = kind
        self.__first, self.__last = self.__bounds(kind, reference)

    @property
    def kind(self) -> str:
        """day, week, month, year or ytd."""
        return self.__kind

    @property
    def first_day(self) -> date:
        """First day inside the period."""
        return self.__first

    @property
    def last_day(self) -> date:
        """Last day inside the period."""
        return self.__last

    def contains(self, moment: datetime) -> bool:
        """True if ``moment`` falls on a day inside the period."""
        day = moment.astimezone(MELBOURNE).date()
        return self.__first <= day <= self.__last

    def label(self) -> str:
        """Readable description of the period."""
        return (f"{self.__NAMES[self.__kind]} ({self.__first:%d %b %Y} to "
                f"{self.__last:%d %b %Y})")

    @staticmethod
    def __bounds(kind: str, ref: date) -> tuple[date, date]:
        if kind == "day":
            return ref, ref
        if kind == "week":
            monday = ref - timedelta(days=ref.weekday())
            return monday, monday + timedelta(days=6)
        if kind == "month":
            first = ref.replace(day=1)
            following = (first + timedelta(days=32)).replace(day=1)
            return first, following - timedelta(days=1)
        if kind == "year":
            return date(ref.year, 1, 1), date(ref.year, 12, 31)
        return date(ref.year, 1, 1), ref
