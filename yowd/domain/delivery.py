"""Delivery and DeliveryEvent: an accepted request being carried out.

Delivery is the Observer *subject*; every history change is announced to
registered DeliveryObservers (NotificationService).  DeliveryEvent is
immutable (frozen dataclass, read-only proof mapping): a correction is
always a new event (QS3, Riel H10).
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Iterable, Mapping

from yowd.domain.errors import BusinessRuleError
from yowd.domain.ports import DeliveryObserver
from yowd.domain.statuses import DeliveryStatus, PaymentStatus


@dataclass(frozen=True)
class DeliveryEvent:
    """One entry in a delivery's history.

    ``changes_status`` is False for events that are recorded without a
    status change, such as an arrival or a failed attempt that will be
    retried (A2 Section 2.2 correction of Task 8).
    """

    status: DeliveryStatus
    occurred_at: datetime
    recorded_at: datetime
    actor_id: str
    note: str = ""
    changes_status: bool = True
    proof: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # A read-only view, so the proof cannot be edited after the fact.
        object.__setattr__(self, "proof",
                           MappingProxyType(dict(self.proof)))


class Delivery:
    """The central record of what happened to the parcels."""

    __slots__ = ("__ref", "__request", "__quote", "__config", "__events",
                 "__allocations", "__payments", "__observers")

    def __init__(self, tracking_ref: str, request, quote, config) -> None:
        self.__ref = tracking_ref
        self.__request = request
        self.__quote = quote
        self.__config = config
        self.__events: list[DeliveryEvent] = []
        self.__allocations: list = []
        self.__payments: list = []
        self.__observers: list[DeliveryObserver] = []

    @classmethod
    def restore(cls, tracking_ref: str, request, quote, config,
                events: Iterable[DeliveryEvent]) -> "Delivery":
        """Rebuild a stored delivery without re-announcing its history.

        Allocations and payments refer back to the delivery, so the
        caller adds them afterwards with ``add_allocation`` and
        ``add_payment``.
        """
        delivery = cls(tracking_ref, request, quote, config)
        delivery.__events = list(events)
        request.link_delivery(delivery)
        return delivery

    # ----------------------------------------------------------- read-only
    @property
    def tracking_ref(self) -> str:
        """Tracking reference, e.g. YW10010."""
        return self.__ref

    @property
    def request(self):
        """The DeliveryRequest this delivery came from."""
        return self.__request

    @property
    def quote(self):
        """The accepted Quote."""
        return self.__quote

    @property
    def events(self) -> tuple[DeliveryEvent, ...]:
        """Full history, oldest first (never edited)."""
        return tuple(self.__events)

    @property
    def allocations(self) -> tuple:
        """Every allocation, including revoked ones (DA6)."""
        return tuple(self.__allocations)

    @property
    def payments(self) -> tuple:
        """Every payment taken for this delivery."""
        return tuple(self.__payments)

    @property
    def status(self) -> DeliveryStatus:
        """Current status = latest status-changing event."""
        for event in reversed(self.__events):
            if event.changes_status:
                return event.status
        return DeliveryStatus.ACCEPTED

    @property
    def is_closed(self) -> bool:
        """True if no further status change is allowed."""
        return not self.__config.allowed_next(self.status)

    @property
    def current_allocation(self):
        """The active (offered or acknowledged) allocation, if any."""
        for allocation in reversed(self.__allocations):
            if allocation.is_active:
                return allocation
        return None

    @property
    def amount_paid(self) -> Decimal:
        """Total of completed or reconciled payments."""
        return sum((p.amount for p in self.__payments
                    if p.status in (PaymentStatus.COMPLETED,
                                    PaymentStatus.RECONCILED)),
                   Decimal("0.00"))

    @property
    def amount_owing(self) -> Decimal:
        """Quoted amount less what has been paid."""
        return max(self.__quote.amount - self.amount_paid, Decimal("0.00"))

    @property
    def proof_of_delivery(self) -> Mapping[str, str]:
        """Proof held on the Delivered event, if delivered."""
        for event in reversed(self.__events):
            if event.status is DeliveryStatus.DELIVERED and event.proof:
                return event.proof
        return MappingProxyType({})

    # --------------------------------------------------------- observers
    def add_observer(self, observer: DeliveryObserver) -> None:
        """Register an observer of this delivery's history."""
        if not isinstance(observer, DeliveryObserver):
            raise TypeError("observer must implement DeliveryObserver")
        if observer not in self.__observers:
            self.__observers.append(observer)

    # --------------------------------------------------------- behaviour
    def start(self, actor_id: str, now: datetime) -> None:
        """Record the first event when the quote is accepted."""
        if self.__events:
            raise BusinessRuleError("This delivery has already started.")
        self.__add(DeliveryEvent(DeliveryStatus.ACCEPTED, now, now,
                                 actor_id, "Quote accepted by customer"))

    def change_status(self, target: DeliveryStatus, actor_id: str,
                      occurred_at: datetime, recorded_at: datetime,
                      note: str = "",
                      proof: Mapping[str, str] | None = None
                      ) -> DeliveryEvent:
        """Move to ``target`` if SystemConfiguration allows it."""
        self.__config.check_transition(self.status, target)
        event = DeliveryEvent(target, occurred_at, recorded_at, actor_id,
                              note, True, dict(proof or {}))
        self.__add(event)
        return event

    def record_note(self, actor_id: str, occurred_at: datetime,
                    recorded_at: datetime, note: str) -> DeliveryEvent:
        """Record an event that does not change the status."""
        event = DeliveryEvent(self.status, occurred_at, recorded_at,
                              actor_id, note, False)
        self.__add(event)
        return event

    def add_allocation(self, allocation) -> None:
        """Attach an allocation; only one may be active at a time (DA6)."""
        if allocation.is_active and self.current_allocation is not None:
            raise BusinessRuleError(f"{self.__ref} already has an active "
                                    "allocation.")
        self.__allocations.append(allocation)

    def is_allocated_to(self, staff_id: str) -> bool:
        """True if the active allocation belongs to ``staff_id``."""
        allocation = self.current_allocation
        return allocation is not None and \
            allocation.staff.staff_id == staff_id

    def add_payment(self, payment) -> None:
        """Attach a payment created for this delivery."""
        self.__payments.append(payment)

    def delivered_at(self) -> datetime | None:
        """Time the parcels were handed over, if delivered."""
        for event in self.__events:
            if event.status is DeliveryStatus.DELIVERED and \
                    event.changes_status:
                return event.occurred_at
        return None

    # ----------------------------------------------------------- private
    def __add(self, event: DeliveryEvent) -> None:
        self.__events.append(event)
        for observer in self.__observers:
            observer.delivery_changed(self, event)
