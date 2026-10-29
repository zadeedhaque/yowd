"""DeliveryRequest: what the customer asks for, before acceptance."""

from datetime import date, datetime
from typing import Iterable

from yowd.domain.delivery import Delivery
from yowd.domain.errors import BusinessRuleError, ValidationError
from yowd.domain.statuses import QuoteStatus, RequestStatus


class DeliveryRequest:
    """Parcels from a pickup address to a recipient at a drop-off."""

    MAX_PARCELS = 10
    __slots__ = ("__id", "__customer", "__pickup", "__dropoff",
                 "__recipient", "__preferred", "__created", "__created_by",
                 "__parcels", "__quotes", "__status", "__flags",
                 "__delivery")

    def __init__(self, request_id: str, customer, pickup, dropoff,
                 recipient, preferred_date: date,
                 created_at: datetime, created_by: str) -> None:
        self.__id = request_id
        self.__customer = customer
        self.__pickup = pickup
        self.__dropoff = dropoff
        self.__recipient = recipient
        self.__preferred = preferred_date
        self.__created = created_at
        self.__created_by = created_by
        self.__parcels: list = []
        self.__quotes: list = []
        self.__status = RequestStatus.REQUESTED
        self.__flags: list[str] = []
        self.__delivery: Delivery | None = None

    @classmethod
    def restore(cls, request_id: str, customer, pickup, dropoff, recipient,
                preferred_date: date, created_at: datetime,
                created_by: str, parcels: Iterable, quotes: Iterable,
                status: RequestStatus,
                flags: Iterable[str]) -> "DeliveryRequest":
        """Rebuild a stored request (its delivery is linked later)."""
        request = cls(request_id, customer, pickup, dropoff, recipient,
                      preferred_date, created_at, created_by)
        request.__parcels = list(parcels)
        request.__quotes = list(quotes)
        request.__status = status
        request.__flags = list(flags)
        return request

    # ----------------------------------------------------------- read-only
    @property
    def request_id(self) -> str:
        """Identifier, e.g. R0011."""
        return self.__id

    @property
    def customer(self):
        """The customer who asked (and pays)."""
        return self.__customer

    @property
    def pickup(self):
        """Pickup Address."""
        return self.__pickup

    @property
    def dropoff(self):
        """Drop-off Address."""
        return self.__dropoff

    @property
    def recipient(self):
        """The Recipient."""
        return self.__recipient

    @property
    def preferred_date(self) -> date:
        """Preferred pickup date."""
        return self.__preferred

    @property
    def created_at(self) -> datetime:
        """When the request was logged."""
        return self.__created

    @property
    def created_by(self) -> str:
        """Customer or staff id that logged it (P1)."""
        return self.__created_by

    @property
    def parcels(self) -> tuple:
        """The parcels, in entry order."""
        return tuple(self.__parcels)

    @property
    def quotes(self) -> tuple:
        """Every quote version, oldest first."""
        return tuple(self.__quotes)

    @property
    def status(self) -> RequestStatus:
        """Requested, Quoted, Accepted, Rejected or Cancelled."""
        return self.__status

    @property
    def flags(self) -> tuple[str, ...]:
        """Problems that need office review."""
        return tuple(self.__flags)

    @property
    def delivery(self) -> Delivery | None:
        """The Delivery created on acceptance, if any."""
        return self.__delivery

    @property
    def needs_office_review(self) -> bool:
        """True if flagged and still waiting for the office."""
        return bool(self.__flags) and \
            self.__status is RequestStatus.REQUESTED

    @property
    def current_quote(self):
        """The newest quote version, or None."""
        return self.__quotes[-1] if self.__quotes else None

    # --------------------------------------------------------- behaviour
    def add_parcel(self, parcel) -> None:
        """Add a validated parcel (the Parcel checked its own limits)."""
        if len(self.__parcels) >= self.MAX_PARCELS:
            raise ValidationError(f"A request can hold at most "
                                  f"{self.MAX_PARCELS} parcels.")
        self.__parcels.append(parcel)

    def check_addresses(self, address_service, config) -> bool:
        """Ask both addresses to verify themselves; flag problems."""
        if not self.__parcels:
            raise ValidationError("Add at least one parcel before "
                                  "submitting.")
        self.__flags = []
        for label, address in (("Pickup", self.__pickup),
                               ("Drop-off", self.__dropoff)):
            if not address.verify(address_service, config):
                self.__flags.append(f"{label}: {address.problem}")
        if self.__pickup.same_place(self.__dropoff):
            self.__flags.append("Pickup and drop-off are the same address.")
        return not self.__flags

    def add_quote(self, quote) -> None:
        """Keep every version; earlier open versions are superseded."""
        if self.__status not in (RequestStatus.REQUESTED,
                                 RequestStatus.QUOTED):
            raise BusinessRuleError(
                f"Request {self.__id} is {self.__status.value} and "
                "cannot be quoted.")
        for old in self.__quotes:
            old.supersede()
        self.__quotes.append(quote)
        self.__status = RequestStatus.QUOTED

    def expire_quote_if_due(self, now: datetime) -> bool:
        """Expire an unanswered quote; the request becomes Rejected."""
        quote = self.current_quote
        if quote is not None and self.__status is RequestStatus.QUOTED \
                and quote.expire_if_due(now):
            self.__status = RequestStatus.REJECTED
            return True
        return False

    def accept_quote(self, tracking_ref: str, config,
                     now: datetime) -> Delivery:
        """Customer accepts: create the Delivery (Creator, Task 3)."""
        quote = self.__open_quote()
        try:
            quote.accept(now)
        except BusinessRuleError:
            if quote.status is QuoteStatus.EXPIRED:
                self.__status = RequestStatus.REJECTED
            raise
        self.__status = RequestStatus.ACCEPTED
        self.__recipient.issue_pin()
        self.__delivery = Delivery(tracking_ref, self, quote, config)
        return self.__delivery

    def link_delivery(self, delivery: Delivery) -> None:
        """Re-attach a stored delivery when records are reloaded."""
        if self.__delivery is not None or \
                self.__status is not RequestStatus.ACCEPTED:
            raise BusinessRuleError(f"{self.__id} cannot take a delivery.")
        self.__delivery = delivery

    def decline_quote(self, now: datetime) -> None:
        """Customer declines: the request becomes Rejected (A2 2.2)."""
        self.__open_quote().decline(now)
        self.__status = RequestStatus.REJECTED

    def cancel(self, reason: str) -> None:
        """Office cancels a flagged request that cannot be served."""
        if self.__status not in (RequestStatus.REQUESTED,
                                 RequestStatus.QUOTED):
            raise BusinessRuleError("Only a request that has not been "
                                    "accepted can be cancelled here.")
        self.__status = RequestStatus.CANCELLED
        self.__flags.append(f"Cancelled: {reason}")

    # ----------------------------------------------------------- private
    def __open_quote(self):
        quote = self.current_quote
        if quote is None or self.__status is not RequestStatus.QUOTED:
            raise BusinessRuleError(
                f"Request {self.__id} has no quote waiting for a "
                "response.")
        return quote
