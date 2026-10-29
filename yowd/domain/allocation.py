"""Allocation: one delivery assigned to one driver for a window."""

from datetime import datetime, timedelta

from yowd.domain.errors import BusinessRuleError
from yowd.domain.statuses import AllocationStatus


class Allocation:
    """Has its own life: offered, acknowledged, revoked or completed."""

    __slots__ = ("__id", "__delivery", "__staff", "__window", "__by",
                 "__offered", "__status", "__acked", "__closed", "__reason")

    def __init__(self, allocation_id: str, delivery, staff, window,
                 allocated_by: str, offered_at: datetime) -> None:
        self.__id = allocation_id
        self.__delivery = delivery
        self.__staff = staff
        self.__window = window
        self.__by = allocated_by
        self.__offered = offered_at
        self.__status = AllocationStatus.OFFERED
        self.__acked: datetime | None = None
        self.__closed: datetime | None = None
        self.__reason = ""

    @classmethod
    def restore(cls, allocation_id: str, delivery, staff, window,
                allocated_by: str, offered_at: datetime,
                status: AllocationStatus, acknowledged_at: datetime | None,
                closed_at: datetime | None, reason: str) -> "Allocation":
        """Rebuild a stored allocation exactly as it was saved."""
        allocation = cls(allocation_id, delivery, staff, window,
                         allocated_by, offered_at)
        allocation.__status = status
        allocation.__acked = acknowledged_at
        allocation.__closed = closed_at
        allocation.__reason = reason
        return allocation

    # ----------------------------------------------------------- read-only
    @property
    def allocation_id(self) -> str:
        """Identifier, e.g. A0009."""
        return self.__id

    @property
    def delivery(self):
        """The Delivery allocated."""
        return self.__delivery

    @property
    def staff(self):
        """The DeliveryStaff allocated."""
        return self.__staff

    @property
    def window(self):
        """Pickup window of the job."""
        return self.__window

    @property
    def allocated_by(self) -> str:
        """Office staff id who allocated it."""
        return self.__by

    @property
    def offered_at(self) -> datetime:
        """When the job was offered."""
        return self.__offered

    @property
    def status(self) -> AllocationStatus:
        """Offered, Acknowledged, Revoked or Completed."""
        return self.__status

    @property
    def acknowledged_at(self) -> datetime | None:
        """When the driver accepted the job."""
        return self.__acked

    @property
    def closed_at(self) -> datetime | None:
        """When it was revoked or completed."""
        return self.__closed

    @property
    def reason(self) -> str:
        """Why it was revoked ("" otherwise)."""
        return self.__reason

    @property
    def is_active(self) -> bool:
        """Offered or acknowledged."""
        return self.__status in (AllocationStatus.OFFERED,
                                 AllocationStatus.ACKNOWLEDGED)

    # --------------------------------------------------------- behaviour
    def acknowledge(self, staff_id: str, now: datetime) -> None:
        """The driver accepts the job on their device (Task 5.4)."""
        if staff_id != self.__staff.staff_id:
            raise BusinessRuleError("This job is not allocated to you.")
        if self.__status is not AllocationStatus.OFFERED:
            raise BusinessRuleError(
                f"This job is {self.__status.value.lower()} and cannot be "
                "acknowledged.")
        self.__status = AllocationStatus.ACKNOWLEDGED
        self.__acked = now

    def is_overdue(self, now: datetime, timeout_minutes: int) -> bool:
        """True if still unacknowledged after the timeout (DA9)."""
        return (self.__status is AllocationStatus.OFFERED
                and now - self.__offered > timedelta(
                    minutes=timeout_minutes))

    def revoke(self, now: datetime, reason: str) -> None:
        """Withdraw the job; the record is kept (DA6)."""
        if not self.is_active:
            raise BusinessRuleError("Only an active allocation can be "
                                    "revoked.")
        self.__status = AllocationStatus.REVOKED
        self.__closed = now
        self.__reason = reason

    def complete(self, now: datetime) -> None:
        """Close the allocation when the delivery reaches an end state."""
        if self.is_active:
            self.__status = AllocationStatus.COMPLETED
            self.__closed = now
