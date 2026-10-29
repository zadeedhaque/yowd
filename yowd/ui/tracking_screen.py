"""Tracking screen (Task 8) for recipients, customers and the office."""

from yowd.domain.errors import DmsError
from yowd.ui.console import Console


class TrackingScreen:
    """Shows the status and history of one delivery.

    Recipients see only the delivery behind the tracking reference and
    no payment details (QS2).  Office staff also see allocations and
    payments.
    """

    def __init__(self, console: Console, system) -> None:
        self.__io = console
        self.__system = system

    def run(self, staff_view: bool = False) -> None:
        """Ask for a reference and show the delivery."""
        self.__io.header("Track a delivery",
                         "Office view" if staff_view else "")
        ref = self.__io.text("* Tracking reference", hint="e.g. YW10001")
        try:
            delivery = self.__system.track(ref)
        except DmsError as error:
            self.__io.error(str(error))
            return
        self.show(delivery, staff_view)
        self.__io.pause()

    def show(self, delivery, staff_view: bool = False) -> None:
        """Print the delivery card and its history."""
        request = delivery.request
        quote = delivery.quote
        self.__io.section(f"Delivery {delivery.tracking_ref}")
        self.__io.info(f"Current status:  {delivery.status.value}")
        self.__io.info(f"From:            {request.pickup.suburb}")
        self.__io.info(f"To:              {request.dropoff.formatted()}")
        self.__io.info(f"Recipient:       {request.recipient.contact.name}")
        self.__io.info(f"Parcels:         {len(request.parcels)}")
        self.__io.info(f"Pickup window:   {quote.pickup_window.label()}")
        self.__io.info(f"Delivery window: {quote.delivery_window.label()}")
        allocation = delivery.current_allocation
        if allocation is not None:
            first = allocation.staff.contact.name.split()[0]
            self.__io.info(f"Driver:          {first} "
                           f"({allocation.status.value})")
        proof = delivery.proof_of_delivery
        if proof:
            self.__io.info(f"Proof:           received by "
                           f"{proof['receiver_name']}, photo "
                           f"{proof['photo'] or 'n/a'}, PIN checked")
        self.__io.section("History (never edited; newest last)")
        rows = [[f"{e.occurred_at:%d/%m %H:%M}", e.status.value
                 if e.changes_status else "-", e.note]
                for e in delivery.events]
        self.__io.table(["When", "Status", "Detail"], rows)
        if staff_view:
            self.__staff_details(delivery)

    def __staff_details(self, delivery) -> None:
        self.__io.section("Allocations")
        self.__io.table(
            ["Id", "Driver", "Status", "Offered", "Note"],
            [[a.allocation_id, a.staff.staff_id, a.status.value,
              f"{a.offered_at:%d/%m %H:%M}", a.reason]
             for a in delivery.allocations])
        self.__io.section("Payments")
        self.__io.table(
            ["Id", "Amount", "Method", "Status", "Receipt"],
            [[p.payment_id, f"${p.amount:.2f}", p.method.value,
              p.status.value, p.receipt.number if p.receipt else "-"]
             for p in delivery.payments])
        self.__io.info(f"Amount owing: ${delivery.amount_owing:.2f}")
        for payment in delivery.payments:
            if payment.receipt is not None:
                self.__io.section("Receipt / tax invoice sent to customer")
                for line in payment.receipt.lines():
                    self.__io.info(line)
