"""SimulatedPaymentGateway: the PaymentGateway adapter for the prototype.

The brief says payments need not be processed for real, so this adapter
only returns a provider reference and a message.  Card details never
enter the system (QS5): the driver enters only the last four digits
shown by the card terminal, as a confirmation.
"""

import itertools
from decimal import Decimal

from yowd.domain.ports import GatewayResult, PaymentGateway


class SimulatedPaymentGateway(PaymentGateway):
    """Pretends to be a provider; approves every well-formed request."""

    __slots__ = ("__counter",)

    def __init__(self, first_reference: int = 1001) -> None:
        self.__counter = itertools.count(first_reference)

    def charge(self, amount: Decimal, card_last_four: str) -> GatewayResult:
        """Return an approved result with a simulated reference."""
        reference = f"SIM-{next(self.__counter)}"
        return GatewayResult(
            True, reference,
            f"Payment of ${amount:.2f} processed by the payment provider "
            f"(simulated, card ending {card_last_four}).")
