"""Interfaces ("ports") that the domain depends on.

Python has no ``interface`` keyword, so each interface is an abstract
base class (``abc.ABC``) whose methods are all ``@abstractmethod``.
This gives the two guarantees a real interface gives:

* a class that claims to implement the interface but misses a method
  cannot be instantiated (``TypeError`` at construction, not a crash
  later);
* code depends only on the abstract type, so a test can pass in a fake
  (e.g. ``FixedClock`` or ``MemoryOutbox``) without touching the domain.

The domain owns these interfaces and the infrastructure implements them
(dependency inversion), so ``yowd.domain`` never imports a concrete
adapter, file or library.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


# ------------------------------------------------------------------ time
class Clock(ABC):
    """Supplies the current Melbourne local time."""

    @abstractmethod
    def now(self) -> datetime:
        """Current time as a timezone-aware datetime."""


# ------------------------------------------------------- address service
@dataclass(frozen=True)
class VerificationResult:
    """Outcome of verifying an address (value object)."""

    verified: bool
    suburb: str
    postcode: str
    latitude: float = 0.0
    longitude: float = 0.0
    message: str = ""


class AddressService(ABC):
    """What YOWD needs from any address/mapping provider (Adapter)."""

    @abstractmethod
    def verify(self, suburb: str, postcode: str) -> VerificationResult:
        """Check that the suburb and postcode exist and match."""

    @abstractmethod
    def distance_km(self, origin: VerificationResult,
                    destination: VerificationResult) -> float:
        """Travel distance between two verified locations."""

    def suburbs(self) -> list[tuple[str, str]]:
        """Known (suburb, postcode) pairs for pick lists.

        A concrete (non-abstract) default: providers that cannot list
        suburbs simply inherit this and return none.
        """
        return []


# ------------------------------------------------------- payment gateway
@dataclass(frozen=True)
class GatewayResult:
    """Outcome reported by the payment provider (value object)."""

    approved: bool
    reference: str
    message: str


class PaymentGateway(ABC):
    """What YOWD needs from any card payment provider (Adapter)."""

    @abstractmethod
    def charge(self, amount: Decimal, card_last_four: str) -> GatewayResult:
        """Ask the provider to take a card payment."""


# -------------------------------------------------------------- observers
class DeliveryObserver(ABC):
    """Anything that wants to hear about delivery history changes."""

    @abstractmethod
    def delivery_changed(self, delivery, event) -> None:
        """Called after a new event is added to a delivery's history."""


class AvailabilityListener(ABC):
    """Anything that wants to hear when a driver withdraws availability."""

    @abstractmethod
    def availability_withdrawn(self, staff, period) -> None:
        """Called after ``staff`` has removed ``period``."""


# ------------------------------------------------------------- messaging
class MessageOutbox(ABC):
    """Where sent SMS/email messages go (provider stand-in)."""

    @abstractmethod
    def post(self, stamp: datetime, line: str) -> None:
        """Record one sent message."""


# --------------------------------------------------------------- storage
class TextStorage(ABC):
    """A named text document (a file, or browser storage)."""

    @abstractmethod
    def exists(self) -> bool:
        """True if the document has been written before."""

    @abstractmethod
    def read(self) -> str:
        """Return the whole document."""

    @abstractmethod
    def write(self, text: str) -> None:
        """Replace the whole document safely."""

    @abstractmethod
    def delete(self) -> None:
        """Remove the document if it exists."""


class RecordStore(ABC):
    """Saves and reloads the Registry (Repository persistence)."""

    @abstractmethod
    def load(self):
        """Return a Registry rebuilt from storage (empty if none)."""

    @abstractmethod
    def save(self, registry) -> None:
        """Persist every record in the registry."""
