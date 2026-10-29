"""Enumerations (data holders) used across the domain.

Assignment 2 had a single ``DeliveryStatus`` enumeration that mixed the
states of a *request* (Requested, Quoted, Rejected) with the states of a
*delivery*.  The detailed design splits these so that each class owns
the states that apply to it (see report Section 1.3, change C4).
"""

from enum import Enum


class RequestStatus(Enum):
    """Life cycle of a DeliveryRequest before it becomes a Delivery."""

    REQUESTED = "Requested"
    QUOTED = "Quoted"
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"
    CANCELLED = "Cancelled"


class DeliveryStatus(Enum):
    """Life cycle of a Delivery (SRS Section 2.2 vocabulary)."""

    ACCEPTED = "Accepted"
    SCHEDULED = "Scheduled"
    PICKED_UP = "Picked up"
    IN_TRANSIT = "In Transit"
    DELIVERED = "Delivered"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    REDIRECTED = "Redirected"
    RETURNED = "Returned"

    @classmethod
    def from_label(cls, label: str) -> "DeliveryStatus":
        """Return the status whose display label is ``label``."""
        for status in cls:
            if status.value == label:
                return status
        raise ValueError(f"Unknown delivery status: {label}")


class QuoteStatus(Enum):
    """Life cycle of a Quote."""

    ISSUED = "Issued"
    ACCEPTED = "Accepted"
    DECLINED = "Declined"
    EXPIRED = "Expired"
    SUPERSEDED = "Superseded"


class AllocationStatus(Enum):
    """Life cycle of an Allocation."""

    OFFERED = "Offered"
    ACKNOWLEDGED = "Acknowledged"
    REVOKED = "Revoked"
    COMPLETED = "Completed"


class PaymentMethod(Enum):
    """How the customer pays at pickup."""

    CASH = "Cash"
    CARD = "Card"


class PaymentStatus(Enum):
    """Life cycle of a Payment."""

    COMPLETED = "Completed"
    RECONCILED = "Reconciled"


class StaffRole(Enum):
    """Role of an OfficeStaff member (owner is a role, not a subclass)."""

    OFFICE = "Office"
    OWNER = "Owner"


class FieldActionKind(Enum):
    """What a driver recorded at the door (Command type)."""

    ARRIVED_PICKUP = "Arrived at pickup"
    PICKUP_AND_PAYMENT = "Pickup and payment"
    DEPART = "Departed for drop-off"
    DELIVER = "Delivered"
    FAILED_ATTEMPT = "Failed attempt"
