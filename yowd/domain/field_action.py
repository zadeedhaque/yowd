"""FieldAction (Command) and OfflineSyncQueue (Invoker).

A driver's doorstep action is wrapped as a FieldAction holding all the
data needed to apply it later, including the time it happened on the
device (QR3, DA12).  When the driver is offline the actions wait in the
OfflineSyncQueue, which is saved on the device so it survives a restart
(QR6) and uploads the actions in the order they happened.

FieldAction is an abstract class using the Template Method pattern:
``execute`` does the checks every action needs, then calls the abstract
``_apply`` that each concrete command (arrival, pickup, ...) overrides.
Adding a new kind of doorstep action is a new subclass, not another
``if`` in existing code (open/closed principle).
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Callable, Mapping

from yowd.domain.errors import BusinessRuleError, DmsError, ValidationError
from yowd.domain.payment import Payment
from yowd.domain.ports import PaymentGateway, TextStorage
from yowd.domain.statuses import (AllocationStatus, DeliveryStatus,
                                  FieldActionKind, PaymentMethod)


@dataclass(frozen=True)
class FieldServices:
    """What a FieldAction needs from the server when it executes."""

    config: object
    gateway: PaymentGateway
    next_id: Callable[[str], str]
    now: datetime


class FieldAction(ABC):
    """One thing a driver did at a pickup or drop-off (Command)."""

    KIND: FieldActionKind
    __TYPES: dict[FieldActionKind, type] = {}

    def __init__(self, tracking_ref: str, staff_id: str,
                 device_time: datetime, data: Mapping | None = None,
                 online: bool = True) -> None:
        self.__ref = tracking_ref
        self.__staff = staff_id
        self.__time = device_time
        self.__data = MappingProxyType(dict(data or {}))
        self.__online = online
        self.__uploaded: datetime | None = None

    def __init_subclass__(cls, **kwargs) -> None:
        """Register each concrete command under its kind (factory)."""
        super().__init_subclass__(**kwargs)
        FieldAction.__TYPES[cls.KIND] = cls

    @classmethod
    def create(cls, kind: FieldActionKind, tracking_ref: str,
               staff_id: str, device_time: datetime,
               data: Mapping | None = None,
               online: bool = True) -> "FieldAction":
        """Factory: build the concrete command for ``kind``."""
        return cls.__TYPES[kind](tracking_ref, staff_id, device_time, data,
                                 online)

    # ----------------------------------------------------------- read-only
    @property
    def kind(self) -> FieldActionKind:
        """Which doorstep action this is."""
        return self.KIND

    @property
    def tracking_ref(self) -> str:
        """Delivery the action belongs to."""
        return self.__ref

    @property
    def staff_id(self) -> str:
        """Driver who did it."""
        return self.__staff

    @property
    def device_time(self) -> datetime:
        """When it happened on the phone (kept as occurred-at)."""
        return self.__time

    @property
    def data(self) -> Mapping:
        """Captured values (read-only)."""
        return self.__data

    @property
    def captured_online(self) -> bool:
        """False if captured with no signal."""
        return self.__online

    @property
    def uploaded_at(self) -> datetime | None:
        """When the server received it."""
        return self.__uploaded

    # --------------------------------------------------------- execution
    def execute(self, delivery, services: FieldServices) -> str:
        """Apply this action to the delivery; return a result message.

        Raises a DmsError subclass when the action conflicts with what
        happened in the meantime (e.g. the delivery was reallocated).
        """
        self.__uploaded = services.now
        self.__check_still_mine(delivery)
        return self._apply(delivery, services)

    @abstractmethod
    def _apply(self, delivery, services: FieldServices) -> str:
        """Do the work of this particular action (hook method)."""

    # ------------------------------------------------------ persistence
    def to_dict(self) -> dict:
        """Device-side storage form."""
        return {"kind": self.KIND.name, "ref": self.__ref,
                "staff": self.__staff,
                "device_time": self.__time.isoformat(),
                "data": dict(self.__data), "online": self.__online}

    @classmethod
    def from_dict(cls, raw: Mapping) -> "FieldAction":
        """Rebuild a queued action read from the device."""
        return cls.create(FieldActionKind[raw["kind"]], raw["ref"],
                          raw["staff"],
                          datetime.fromisoformat(raw["device_time"]),
                          raw["data"], raw["online"])

    def label(self) -> str:
        """Readable one-line description."""
        return (f"{self.__time:%H:%M:%S} {self.KIND.value} "
                f"{self.__ref}")

    # ----------------------------------------------------------- private
    def __check_still_mine(self, delivery) -> None:
        if delivery.status is DeliveryStatus.CANCELLED:
            raise BusinessRuleError(
                f"{delivery.tracking_ref} was cancelled while you were "
                "offline. The office has been alerted.")
        allocation = delivery.current_allocation
        if allocation is None or allocation.staff.staff_id != self.__staff:
            raise BusinessRuleError(
                f"{delivery.tracking_ref} is no longer allocated to you. "
                "The office has been alerted.")
        if allocation.status is not AllocationStatus.ACKNOWLEDGED:
            raise BusinessRuleError("Acknowledge the job before recording "
                                    "work on it.")


class ArrivalAction(FieldAction):
    """Driver arrived at the pickup (Task 6.1)."""

    KIND = FieldActionKind.ARRIVED_PICKUP

    def _apply(self, delivery, services: FieldServices) -> str:
        delivery.record_note(self.staff_id, self.device_time, services.now,
                             "Driver arrived at pickup")
        return f"Arrival recorded at {self.device_time:%H:%M}."


class PickupAction(FieldAction):
    """Parcels checked off and payment taken (Tasks 6.2-6.5)."""

    KIND = FieldActionKind.PICKUP_AND_PAYMENT

    def _apply(self, delivery, services: FieldServices) -> str:
        expected = len(delivery.request.parcels)
        collected = int(self.data.get("collected", 0))
        if collected != expected:
            raise ValidationError(
                f"{collected} of {expected} parcels checked off. Check off "
                "every parcel, or record a failed attempt and call the "
                "office if parcels are missing.")
        message = self.__take_payment(delivery, services)
        for parcel in delivery.request.parcels:
            parcel.mark_collected()
        delivery.change_status(DeliveryStatus.PICKED_UP, self.staff_id,
                               self.device_time, services.now,
                               f"{collected} parcel(s) collected")
        return "Pickup recorded." + message

    def __take_payment(self, delivery, services: FieldServices) -> str:
        if delivery.amount_owing <= 0:
            return ""
        method = PaymentMethod(self.data.get("method", "Cash"))
        if method is PaymentMethod.CARD and not self.captured_online:
            raise BusinessRuleError(
                "Card payments need a connection (DA10). Take cash, or "
                "wait for signal.")
        payment = Payment.take(
            services.next_id("P"), delivery, method, self.staff_id,
            self.device_time, services.gateway,
            str(self.data.get("card_last_four", "")))
        receipt = payment.issue_receipt(services.config,
                                        services.next_id("INV"))
        delivery.add_payment(payment)
        return (f" {method.value} payment of ${payment.amount:.2f} "
                f"recorded; receipt {receipt.number} issued.")


class DepartAction(FieldAction):
    """Driver left for the drop-off (Task 6.6)."""

    KIND = FieldActionKind.DEPART

    def _apply(self, delivery, services: FieldServices) -> str:
        delivery.change_status(DeliveryStatus.IN_TRANSIT, self.staff_id,
                               self.device_time, services.now,
                               "Driver left for drop-off")
        return "Status is now In Transit."


class DeliverAction(FieldAction):
    """Parcels handed over with PIN and proof (Task 7)."""

    KIND = FieldActionKind.DELIVER

    def _apply(self, delivery, services: FieldServices) -> str:
        receiver = str(self.data.get("receiver_name", "")).strip()
        if not receiver:
            raise ValidationError("Enter the name of the person who took "
                                  "the parcels.")
        if not delivery.request.recipient.check_pin(
                str(self.data.get("pin", ""))):
            raise ValidationError("The handover PIN is wrong. Ask the "
                                  "recipient to check the PIN the "
                                  "customer gave them.")
        proof = {"receiver_name": receiver,
                 "photo": str(self.data.get("photo", "")),
                 "pin_checked": "yes"}
        delivery.change_status(DeliveryStatus.DELIVERED, self.staff_id,
                               self.device_time, services.now,
                               f"Received by {receiver}", proof)
        delivery.current_allocation.complete(services.now)
        return (f"Delivered; proof of delivery stored (received by "
                f"{receiver}).")


class FailedAttemptAction(FieldAction):
    """Nobody home, address not found, ... (Task 6d / Task 7 variants)."""

    KIND = FieldActionKind.FAILED_ATTEMPT

    def _apply(self, delivery, services: FieldServices) -> str:
        reason = str(self.data.get("reason", "")).strip()
        if not reason:
            raise ValidationError("Choose a reason for the failed "
                                  "attempt.")
        delivery.record_note(self.staff_id, self.device_time, services.now,
                             f"Failed attempt: {reason}")
        return "Failed attempt recorded; the office will re-arrange it."


class OfflineSyncQueue:
    """Keeps FieldActions on the driver's device until uploaded."""

    __slots__ = ("__staff", "__storage", "__pending", "__online")

    def __init__(self, staff_id: str,
                 storage: TextStorage | None = None) -> None:
        self.__staff = staff_id
        self.__storage = storage
        self.__pending: list[FieldAction] = []
        self.__online = True
        self.__load()

    @property
    def staff_id(self) -> str:
        """Driver who owns this device queue."""
        return self.__staff

    @property
    def online(self) -> bool:
        """True while the phone has signal."""
        return self.__online

    @property
    def pending(self) -> tuple[FieldAction, ...]:
        """Actions waiting to be uploaded, oldest first."""
        return tuple(self.__pending)

    def go_offline(self) -> None:
        """Signal lost: new actions will be queued."""
        self.__online = False

    def go_online(self) -> None:
        """Signal back: actions can be uploaded."""
        self.__online = True

    def enqueue(self, action: FieldAction) -> None:
        """Store an action captured with no signal."""
        if action.staff_id != self.__staff:
            raise BusinessRuleError("This action belongs to another "
                                    "driver's device.")
        self.__pending.append(action)
        self.__pending.sort(key=lambda a: a.device_time)
        self.__save()

    def flush(self, upload: Callable[[FieldAction], str]
              ) -> list[tuple[FieldAction, str, bool]]:
        """Upload queued actions in time order; return the outcomes.

        A conflicting action is reported back (and to the office) rather
        than lost, so the driver can see what happened.
        """
        if not self.__online:
            raise BusinessRuleError("Still offline. Go online first.")
        results = []
        for action in sorted(self.__pending, key=lambda a: a.device_time):
            try:
                results.append((action, upload(action), True))
            except DmsError as error:
                results.append((action, str(error), False))
        self.__pending.clear()
        self.__save()
        return results

    def __save(self) -> None:
        if self.__storage is not None:
            self.__storage.write(json.dumps(
                [a.to_dict() for a in self.__pending], indent=1))

    def __load(self) -> None:
        if self.__storage is not None and self.__storage.exists():
            raw = json.loads(self.__storage.read() or "[]")
            self.__pending = [FieldAction.from_dict(r) for r in raw]
