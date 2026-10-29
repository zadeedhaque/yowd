"""InputParser: turns text typed into a screen into checked values.

Kept separate from the facade (single responsibility) so the console,
the web UI and the unit tests share one set of parsing rules.  Every
method raises ValidationError with a message that says what to type.
"""

from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from yowd.domain.clock import MELBOURNE
from yowd.domain.errors import ValidationError
from yowd.domain.values import TimeWindow


class InputParser:
    """Stateless parsing rules shared by every user interface."""

    DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d")
    EARLIEST = time(6, 0)
    LATEST = time(22, 0)
    MAX_DAYS_AHEAD = 14

    @staticmethod
    def money(raw: str) -> Decimal:
        """A dollar amount above zero, e.g. '45.50' or '$45.50'."""
        try:
            value = Decimal(str(raw).strip().lstrip("$"))
        except InvalidOperation as exc:
            raise ValidationError("Enter an amount such as 45.50.") from exc
        if not value.is_finite() or value <= 0:
            raise ValidationError("The amount must be above $0.00.")
        return value.quantize(Decimal("0.01"))

    @classmethod
    def day(cls, raw: str, message: str = "Enter the date as DD/MM/YYYY."
            ) -> date:
        """A date as DD/MM/YYYY (console) or YYYY-MM-DD (web forms)."""
        for pattern in cls.DATE_FORMATS:
            try:
                return datetime.strptime(str(raw).strip(), pattern).date()
            except ValueError:
                continue
        raise ValidationError(message)

    @classmethod
    def preferred_date(cls, raw: str, today: date) -> date:
        """Pickup date from today up to 14 days ahead; blank = today."""
        if not str(raw).strip():
            return today
        chosen = cls.day(raw, "Enter the date as DD/MM/YYYY, or press "
                              "Enter for today.")
        if chosen < today or (chosen - today).days > cls.MAX_DAYS_AHEAD:
            raise ValidationError("Choose a date from today up to 14 days "
                                  "ahead.")
        return chosen

    @classmethod
    def report_date(cls, raw: str, today: date) -> date:
        """Any date inside a report period; blank = today."""
        return today if not str(raw).strip() else cls.day(raw)

    @classmethod
    def clock_time(cls, raw: str) -> time:
        """A 24-hour time HH:MM."""
        try:
            return datetime.strptime(str(raw).strip(), "%H:%M").time()
        except ValueError as exc:
            raise ValidationError("Enter times as HH:MM (24-hour), e.g. "
                                  "08:00.") from exc

    @classmethod
    def window(cls, day: str, start: str, end: str) -> TimeWindow:
        """A working window between 06:00 and 22:00 on one day."""
        chosen = cls.day(day, "Enter the day as DD/MM/YYYY.")
        begin, finish = cls.clock_time(start), cls.clock_time(end)
        if not cls.EARLIEST <= begin < finish <= cls.LATEST:
            raise ValidationError("Times must be between 06:00 and 22:00 "
                                  "and the end must be after the start.")
        return TimeWindow(datetime.combine(chosen, begin, MELBOURNE),
                          datetime.combine(chosen, finish, MELBOURNE))
