"""People classes: Customer, Recipient, OfficeStaff, DeliveryStaff.

Encapsulation convention used in every entity of the domain:

* state is held in double-underscore attributes (``self.__active``).
  Python "name-mangles" them to ``_DeliveryStaff__active``, so they
  cannot be reached as ``staff.__active`` from outside the class and
  cannot clash with a subclass's names - the closest Python has to
  ``private``;
* ``@property`` getters give read-only access, and collections are
  returned as tuples so callers cannot change them in place;
* state only changes through intention-revealing methods
  (``deactivate``, ``withdraw_availability``...) that check the rules;
* ``__slots__`` stops anyone adding stray attributes by mistake.

As in Assignment 2 there is no common superclass: the only shared part
is ContactDetails, which each class holds (composition over inheritance,
Riel heuristic 5.1).
"""

import secrets
from datetime import datetime, timedelta
from typing import Callable, Iterable

from yowd.domain.errors import AuthorisationError, BusinessRuleError
from yowd.domain.ports import AvailabilityListener
from yowd.domain.statuses import StaffRole
from yowd.domain.values import ContactDetails, TimeWindow


class Recipient:
    """The person who receives the parcels; never logs in (DA8)."""

    __slots__ = ("__contact", "__pin")

    def __init__(self, contact: ContactDetails,
                 handover_pin: str = "") -> None:
        self.__contact = contact
        self.__pin = handover_pin

    @property
    def contact(self) -> ContactDetails:
        """Name, phone and email."""
        return self.__contact

    @property
    def handover_pin(self) -> str:
        """PIN the customer passes to the recipient ("" until accepted)."""
        return self.__pin

    def issue_pin(self) -> str:
        """Generate the 4-digit handover PIN once (Task 7)."""
        if self.__pin:
            raise BusinessRuleError("A handover PIN has already been "
                                    "issued.")
        self.__pin = f"{secrets.randbelow(10000):04d}"
        return self.__pin

    def matches(self, other: "Recipient") -> bool:
        """Same person (used to avoid saving duplicates)."""
        return (self.__contact.name.lower() == other.contact.name.lower()
                and self.__contact.phone == other.contact.phone)

    def check_pin(self, pin: str) -> bool:
        """Confirm receipt by giving the PIN at handover (Task 7)."""
        return bool(self.__pin) and pin.strip() == self.__pin

    def copy(self) -> "Recipient":
        """A new recipient with the same details and no PIN."""
        return Recipient(self.__contact)


class Customer:
    """A person or business that asks YOWD to deliver parcels."""

    __slots__ = ("__id", "__contact", "__has_login", "__addresses",
                 "__recipients")

    def __init__(self, customer_id: str, contact: ContactDetails,
                 has_login: bool = True, saved_addresses: Iterable = (),
                 saved_recipients: Iterable[Recipient] = ()) -> None:
        self.__id = customer_id
        self.__contact = contact
        self.__has_login = has_login
        self.__addresses = list(saved_addresses)
        self.__recipients = list(saved_recipients)

    @property
    def customer_id(self) -> str:
        """Identifier, e.g. C004."""
        return self.__id

    @property
    def contact(self) -> ContactDetails:
        """Name, phone, email and channel."""
        return self.__contact

    @property
    def has_login(self) -> bool:
        """False for walk-in or phone (guest) customers (DA7)."""
        return self.__has_login

    @property
    def saved_addresses(self) -> tuple:
        """Addresses used before (QU8)."""
        return tuple(self.__addresses)

    @property
    def saved_recipients(self) -> tuple[Recipient, ...]:
        """Recipients used before (QU8)."""
        return tuple(self.__recipients)

    def remember_address(self, address) -> None:
        """Save an address for next time without duplicates."""
        if not any(a.same_place(address) for a in self.__addresses):
            self.__addresses.append(address)

    def remember_recipient(self, recipient: Recipient) -> None:
        """Save a recipient for next time without duplicates."""
        if not any(r.matches(recipient) for r in self.__recipients):
            self.__recipients.append(recipient.copy())


class OfficeStaff:
    """A YOWD office employee; an owner is office staff with OWNER role."""

    __slots__ = ("__id", "__contact", "__role", "__active")

    def __init__(self, staff_id: str, contact: ContactDetails,
                 role: StaffRole = StaffRole.OFFICE,
                 active: bool = True) -> None:
        self.__id = staff_id
        self.__contact = contact
        self.__role = role
        self.__active = active

    @property
    def staff_id(self) -> str:
        """Identifier, e.g. S002."""
        return self.__id

    @property
    def contact(self) -> ContactDetails:
        """Contact details."""
        return self.__contact

    @property
    def role(self) -> StaffRole:
        """Office or Owner."""
        return self.__role

    @property
    def active(self) -> bool:
        """False once the member has left."""
        return self.__active

    @property
    def is_owner(self) -> bool:
        """True if this member holds the owner role."""
        return self.__role is StaffRole.OWNER

    def require_owner(self, action: str) -> None:
        """Raise AuthorisationError unless the member is an owner."""
        if not self.is_owner:
            raise AuthorisationError(
                f"Only an owner can {action}. Please ask an owner.")


class AvailabilityPeriod:
    """A period a driver can work; optionally repeating every week."""

    __slots__ = ("__id", "__window", "__weekly")

    def __init__(self, period_id: str, window: TimeWindow,
                 weekly: bool = False) -> None:
        self.__id = period_id
        self.__window = window
        self.__weekly = weekly

    @property
    def period_id(self) -> str:
        """Identifier, e.g. AV013."""
        return self.__id

    @property
    def window(self) -> TimeWindow:
        """The (first) window of the period."""
        return self.__window

    @property
    def weekly(self) -> bool:
        """True if the period repeats every week."""
        return self.__weekly

    def covers(self, wanted: TimeWindow) -> bool:
        """True if this period (or a weekly repeat of it) covers wanted."""
        if self.__window.covers(wanted):
            return True
        if not self.__weekly or wanted.start < self.__window.start:
            return False
        weeks = (wanted.start - self.__window.start).days // 7
        return self.__window.shifted(timedelta(weeks=weeks)).covers(wanted)

    def is_current(self, now: datetime) -> bool:
        """True if the period has not completely passed."""
        return self.__weekly or self.__window.end > now

    def label(self) -> str:
        """Readable description of the period."""
        if self.__weekly:
            start, end = self.__window.start, self.__window.end
            return f"Every {start:%a} {start:%H:%M}-{end:%H:%M}"
        return self.__window.label()


class DeliveryStaff:
    """A driver who picks up, takes payment and delivers."""

    __slots__ = ("__id", "__contact", "__active", "__periods",
                 "__listeners")

    def __init__(self, staff_id: str, contact: ContactDetails,
                 active: bool = True,
                 availability: Iterable[AvailabilityPeriod] = ()) -> None:
        self.__id = staff_id
        self.__contact = contact
        self.__active = active
        self.__periods = sorted(availability, key=lambda p: p.window.start)
        self.__listeners: list[AvailabilityListener] = []

    @property
    def staff_id(self) -> str:
        """Identifier, e.g. D001."""
        return self.__id

    @property
    def contact(self) -> ContactDetails:
        """Contact details."""
        return self.__contact

    @property
    def active(self) -> bool:
        """False once the driver has left (history is kept)."""
        return self.__active

    @property
    def availability(self) -> tuple[AvailabilityPeriod, ...]:
        """Declared periods, earliest first."""
        return tuple(self.__periods)

    def add_listener(self, listener: AvailabilityListener) -> None:
        """Register an observer of availability withdrawals."""
        if not isinstance(listener, AvailabilityListener):
            raise TypeError("listener must implement AvailabilityListener")
        if listener not in self.__listeners:
            self.__listeners.append(listener)

    def deactivate(self) -> None:
        """Mark the driver as having left the business (Task 10)."""
        if not self.__active:
            raise BusinessRuleError(f"{self.__id} is already inactive.")
        self.__active = False

    def declare_availability(self, window: TimeWindow, weekly: bool,
                             now: datetime,
                             new_id: Callable[[], str]) -> AvailabilityPeriod:
        """Create and add an availability period (Task 4; Creator).

        The id is only taken once the period has passed every check.
        """
        self.__check_new_period(window, weekly, now)
        period = AvailabilityPeriod(new_id(), window, weekly)
        self.__add(period)
        return period

    def change_availability(self, period_id: str, new_window: TimeWindow,
                            now: datetime) -> AvailabilityPeriod:
        """Replace a period with a new window (Task 4.2)."""
        old = self.__find(period_id)
        self.__periods.remove(old)
        try:
            self.__check_new_period(new_window, old.weekly, now)
        except BusinessRuleError:
            self.__add(old)
            raise
        replacement = AvailabilityPeriod(period_id, new_window, old.weekly)
        self.__add(replacement)
        if not new_window.covers(old.window):
            self.__announce(old)
        return replacement

    def withdraw_availability(self, period_id: str) -> AvailabilityPeriod:
        """Remove a period and tell listeners (Task 4.3)."""
        period = self.__find(period_id)
        self.__periods.remove(period)
        self.__announce(period)
        return period

    def is_available_for(self, wanted: TimeWindow) -> bool:
        """True if active and any period covers the wanted window."""
        return self.__active and any(p.covers(wanted)
                                     for p in self.__periods)

    # ----------------------------------------------------------- private
    def __check_new_period(self, window: TimeWindow, weekly: bool,
                           now: datetime) -> None:
        if not self.__active:
            raise BusinessRuleError("An inactive staff member cannot "
                                    "declare availability.")
        if not weekly and window.end <= now:
            raise BusinessRuleError("That period is already in the past. "
                                    "Please choose a future time.")
        for existing in self.__periods:
            if existing.window.overlaps(window):
                raise BusinessRuleError(
                    f"This overlaps your existing period {existing.label()}."
                    " Change or withdraw that period instead.")

    def __add(self, period: AvailabilityPeriod) -> None:
        self.__periods.append(period)
        self.__periods.sort(key=lambda p: p.window.start)

    def __announce(self, period: AvailabilityPeriod) -> None:
        for listener in self.__listeners:
            listener.availability_withdrawn(self, period)

    def __find(self, period_id: str) -> AvailabilityPeriod:
        for period in self.__periods:
            if period.period_id == period_id:
                return period
        raise BusinessRuleError(f"No availability period '{period_id}'. "
                                "Choose one from the list shown.")
