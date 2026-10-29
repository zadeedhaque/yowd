"""Payment and Receipt.

One Payment class handles card and cash; the method is data, not a
subclass (A2 Section 3.3).  Receipt is a new data holder added during
detailed design so the tax-invoice fields have one home (P4, DA15).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from yowd.domain.errors import BusinessRuleError, ValidationError
from yowd.domain.ports import PaymentGateway
from yowd.domain.statuses import PaymentMethod, PaymentStatus


@dataclass(frozen=True)
class Receipt:
    """Tax invoice issued once a payment completes."""

    number: str
    issued_at: datetime
    business_name: str
    abn: str
    business_address: str
    customer_name: str
    tracking_ref: str
    amount: Decimal
    gst: Decimal
    method: str

    def lines(self) -> list[str]:
        """Text lines of the tax invoice."""
        return [f"TAX INVOICE {self.number}",
                f"{self.business_name}  ABN {self.abn}",
                self.business_address,
                f"Date: {self.issued_at:%d/%m/%Y %H:%M}",
                f"Customer: {self.customer_name}",
                f"Delivery: {self.tracking_ref}",
                f"Total (incl. GST): ${self.amount:.2f}",
                f"GST included:      ${self.gst:.2f}",
                f"Paid by: {self.method}"]


class Payment:
    """Money collected for a delivery, by card or in cash."""

    __slots__ = ("__id", "__delivery", "__amount", "__method", "__staff",
                 "__taken", "__status", "__provider_ref", "__rec_by",
                 "__rec_at", "__receipt")

    def __init__(self, payment_id: str, delivery, amount: Decimal,
                 method: PaymentMethod, staff_id: str,
                 taken_at: datetime, provider_reference: str = "") -> None:
        if amount <= 0:
            raise ValidationError("Payment amount must be above $0.00.")
        self.__id = payment_id
        self.__delivery = delivery
        self.__amount = amount
        self.__method = method
        self.__staff = staff_id
        self.__taken = taken_at
        self.__status = PaymentStatus.COMPLETED
        self.__provider_ref = provider_reference
        self.__rec_by = ""
        self.__rec_at: datetime | None = None
        self.__receipt: Receipt | None = None

    @classmethod
    def take(cls, payment_id: str, delivery, method: PaymentMethod,
             staff_id: str, now: datetime, gateway: PaymentGateway,
             card_last_four: str = "") -> "Payment":
        """Collect the amount owing (Task 6.4).

        Card payments go through the PaymentGateway so card details
        never enter YOWD's system (QS5); cash is recorded as held by the
        driver until the office reconciles it (DA11).
        """
        amount = delivery.amount_owing
        if amount <= 0:
            raise BusinessRuleError("Nothing is owed on this delivery.")
        reference = ""
        if method is PaymentMethod.CARD:
            if not (card_last_four.isdigit() and len(card_last_four) == 4):
                raise ValidationError("Enter the last 4 digits shown on "
                                      "the card terminal.")
            result = gateway.charge(amount, card_last_four)
            if not result.approved:
                raise BusinessRuleError(result.message)
            reference = result.reference
        return cls(payment_id, delivery, amount, method, staff_id, now,
                   reference)

    @classmethod
    def restore(cls, payment_id: str, delivery, amount: Decimal,
                method: PaymentMethod, staff_id: str, taken_at: datetime,
                provider_reference: str, status: PaymentStatus,
                reconciled_by: str,
                reconciled_at: datetime | None) -> "Payment":
        """Rebuild a stored payment (its receipt is re-issued after)."""
        payment = cls(payment_id, delivery, amount, method, staff_id,
                      taken_at, provider_reference)
        payment.__status = status
        payment.__rec_by = reconciled_by
        payment.__rec_at = reconciled_at
        return payment

    # ----------------------------------------------------------- read-only
    @property
    def payment_id(self) -> str:
        """Identifier, e.g. P0009."""
        return self.__id

    @property
    def delivery(self):
        """The Delivery paid for."""
        return self.__delivery

    @property
    def amount(self) -> Decimal:
        """Amount collected, including GST."""
        return self.__amount

    @property
    def method(self) -> PaymentMethod:
        """Card or Cash."""
        return self.__method

    @property
    def staff_id(self) -> str:
        """Driver who collected it."""
        return self.__staff

    @property
    def taken_at(self) -> datetime:
        """When it was collected."""
        return self.__taken

    @property
    def status(self) -> PaymentStatus:
        """Completed or Reconciled."""
        return self.__status

    @property
    def provider_reference(self) -> str:
        """Payment provider's reference (card only)."""
        return self.__provider_ref

    @property
    def reconciled_by(self) -> str:
        """Office staff id who reconciled the cash."""
        return self.__rec_by

    @property
    def reconciled_at(self) -> datetime | None:
        """When the cash was reconciled."""
        return self.__rec_at

    @property
    def receipt(self) -> Receipt | None:
        """The tax invoice, once issued."""
        return self.__receipt

    # --------------------------------------------------------- behaviour
    def issue_receipt(self, config, number: str) -> Receipt:
        """Produce the tax invoice (P4) - GST is 1/11 of the total."""
        if self.__receipt is not None:
            raise BusinessRuleError("A receipt has already been issued.")
        gst = (self.__amount * config.gst_rate / (1 + config.gst_rate)
               ).quantize(Decimal("0.01"), ROUND_HALF_UP)
        self.__receipt = Receipt(
            number, self.__taken, config.business_name,
            config.business_abn, config.business_address,
            self.__delivery.request.customer.contact.name,
            self.__delivery.tracking_ref, self.__amount, gst,
            self.__method.value + (f" ({self.__provider_ref})"
                                   if self.__provider_ref else ""))
        return self.__receipt

    def reconcile(self, officer_id: str, now: datetime) -> None:
        """Office confirms cash handed in by the driver."""
        if self.__method is not PaymentMethod.CASH:
            raise BusinessRuleError("Only cash payments are reconciled.")
        if self.__status is PaymentStatus.RECONCILED:
            raise BusinessRuleError("This payment is already reconciled.")
        self.__status = PaymentStatus.RECONCILED
        self.__rec_by = officer_id
        self.__rec_at = now
