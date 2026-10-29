"""Quote: a price and pickup/delivery windows, valid until it expires."""

from datetime import datetime
from decimal import Decimal

from yowd.domain.errors import BusinessRuleError, ValidationError
from yowd.domain.statuses import QuoteStatus
from yowd.domain.values import TimeWindow


class Quote:
    """One version of the price offered for a DeliveryRequest."""

    __slots__ = ("__id", "__amount", "__original", "__pickup",
                 "__delivery", "__issued", "__expires", "__km", "__lines",
                 "__status", "__by", "__reason", "__responded")

    def __init__(self, quote_id: str, amount: Decimal,
                 pickup_window: TimeWindow, delivery_window: TimeWindow,
                 issued_at: datetime, expires_at: datetime,
                 distance_km: float = 0.0,
                 breakdown: list[tuple[str, Decimal]] | None = None,
                 priced_by: str = "", price_reason: str = "") -> None:
        if amount <= 0:
            raise ValidationError("A quote must be above $0.00.")
        if expires_at <= issued_at:
            raise ValidationError("A quote must expire after it is issued.")
        self.__id = quote_id
        self.__amount = amount
        self.__original = amount
        self.__pickup = pickup_window
        self.__delivery = delivery_window
        self.__issued = issued_at
        self.__expires = expires_at
        self.__km = distance_km
        self.__lines = list(breakdown or [])
        self.__status = QuoteStatus.ISSUED
        self.__by = priced_by
        self.__reason = price_reason
        self.__responded: datetime | None = None

    @classmethod
    def restore(cls, quote_id: str, amount: Decimal, original: Decimal,
                pickup_window: TimeWindow, delivery_window: TimeWindow,
                issued_at: datetime, expires_at: datetime,
                distance_km: float, breakdown: list, status: QuoteStatus,
                priced_by: str, price_reason: str,
                responded_at: datetime | None) -> "Quote":
        """Rebuild a stored quote exactly as it was saved."""
        quote = cls(quote_id, original, pickup_window, delivery_window,
                    issued_at, expires_at, distance_km, breakdown,
                    priced_by, price_reason)
        quote.__amount = amount
        quote.__status = status
        quote.__responded = responded_at
        return quote

    # ----------------------------------------------------------- read-only
    @property
    def quote_id(self) -> str:
        """Identifier, e.g. Q0011."""
        return self.__id

    @property
    def amount(self) -> Decimal:
        """Current price including GST."""
        return self.__amount

    @property
    def original_amount(self) -> Decimal:
        """Price before any office override (QS4)."""
        return self.__original

    @property
    def pickup_window(self) -> TimeWindow:
        """Estimated pickup window."""
        return self.__pickup

    @property
    def delivery_window(self) -> TimeWindow:
        """Estimated delivery window."""
        return self.__delivery

    @property
    def issued_at(self) -> datetime:
        """When the quote was issued."""
        return self.__issued

    @property
    def expires_at(self) -> datetime:
        """When the quote stops being valid (DA9)."""
        return self.__expires

    @property
    def distance_km(self) -> float:
        """Distance used for pricing."""
        return self.__km

    @property
    def breakdown(self) -> tuple[tuple[str, Decimal], ...]:
        """Itemised price lines."""
        return tuple(self.__lines)

    @property
    def status(self) -> QuoteStatus:
        """Issued, accepted, declined, expired or superseded."""
        return self.__status

    @property
    def overridden_by(self) -> str:
        """Staff id who set or changed the price ("" if system price)."""
        return self.__by

    @property
    def override_reason(self) -> str:
        """Why the price was set by hand."""
        return self.__reason

    @property
    def responded_at(self) -> datetime | None:
        """When the customer answered."""
        return self.__responded

    # --------------------------------------------------------- behaviour
    def is_valid(self, now: datetime) -> bool:
        """True if issued and not yet past its expiry."""
        return self.__status is QuoteStatus.ISSUED and now < self.__expires

    def expire_if_due(self, now: datetime) -> bool:
        """Mark the quote expired if its time is up; True if it did."""
        if self.__status is QuoteStatus.ISSUED and now >= self.__expires:
            self.__status = QuoteStatus.EXPIRED
            return True
        return False

    def accept(self, now: datetime) -> None:
        """Record acceptance; refuses an expired or answered quote."""
        self.expire_if_due(now)
        if self.__status is QuoteStatus.EXPIRED:
            raise BusinessRuleError(
                "This quote has expired. Please submit the request again "
                "for a new quote.")
        if self.__status is not QuoteStatus.ISSUED:
            raise BusinessRuleError(
                f"This quote is already {self.__status.value.lower()}.")
        self.__status = QuoteStatus.ACCEPTED
        self.__responded = now

    def decline(self, now: datetime) -> None:
        """Record that the customer declined."""
        if self.__status is not QuoteStatus.ISSUED:
            raise BusinessRuleError(
                f"This quote is already {self.__status.value.lower()}.")
        self.__status = QuoteStatus.DECLINED
        self.__responded = now

    def supersede(self) -> None:
        """Replace by a newer version (kept for history)."""
        if self.__status is QuoteStatus.ISSUED:
            self.__status = QuoteStatus.SUPERSEDED

    def override_price(self, staff_id: str, amount: Decimal,
                       reason: str) -> None:
        """Office staff change the price with a reason (Task 2.3)."""
        if self.__status is not QuoteStatus.ISSUED:
            raise BusinessRuleError("Only an open quote can be changed.")
        if amount <= 0:
            raise ValidationError("The new price must be above $0.00.")
        if not reason.strip():
            raise ValidationError("A reason is required for a price "
                                  "override.")
        self.__amount = amount.quantize(Decimal("0.01"))
        self.__by = staff_id
        self.__reason = reason.strip()
