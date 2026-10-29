"""NotificationService: decides who to tell and sends the message.

Observer of every Delivery (A2 Section 6.3).  The prototype has no SMS
or email provider, so messages go to a MessageOutbox (a log file) and
kept in memory so the console can show them (DA13: a failed message is
logged and never blocks a business step).
"""

from yowd.domain.ports import Clock, DeliveryObserver, MessageOutbox
from yowd.domain.statuses import DeliveryStatus


class NotificationService(DeliveryObserver):
    """Sends SMS/email messages through the (simulated) providers."""

    OFFICE = "YOWD office"
    __STATUS_EVENTS = {
        DeliveryStatus.PICKED_UP: "Picked up",
        DeliveryStatus.IN_TRANSIT: "In Transit",
        DeliveryStatus.DELIVERED: "Delivered",
        DeliveryStatus.FAILED: "Failed",
        DeliveryStatus.CANCELLED: "Cancelled",
    }
    __slots__ = ("__config", "__clock", "__outbox", "__recent")

    def __init__(self, config, clock: Clock,
                 outbox: MessageOutbox | None = None) -> None:
        self.__config = config
        self.__clock = clock
        self.__outbox = outbox
        self.__recent: list[str] = []

    # ------------------------------------------------- observer callback
    def delivery_changed(self, delivery, event) -> None:
        """Tell the customer and recipient about status changes."""
        ref = delivery.tracking_ref
        if not event.changes_status:
            if event.note.startswith("Failed attempt"):
                reason = event.note.split(": ", 1)[-1]
                self.send(delivery.request.customer.contact,
                          "Failed attempt", ref=ref, reason=reason)
                self.notify_office("Failed attempt", ref=ref,
                                   reason=reason)
            return
        if event.status is DeliveryStatus.SCHEDULED:
            self.send(delivery.request.customer.contact, "Scheduled",
                      ref=ref,
                      window=delivery.quote.pickup_window.label())
            return
        template = self.__STATUS_EVENTS.get(event.status)
        if template is None:
            return
        values = {"ref": ref,
                  "receiver": event.proof.get("receiver_name", ""),
                  "reason": event.note}
        self.send(delivery.request.customer.contact, template, **values)
        self.send(delivery.request.recipient.contact, template, **values)

    # ------------------------------------------------------------ sending
    def send(self, contact, template: str, **values: str) -> str:
        """Fill the template and send it on the preferred channel."""
        try:
            text = self.__config.template(template).format(**values)
        except KeyError:
            text = f"{template}: {values}"
        channel = contact.preferred_channel
        target = contact.phone if channel == "SMS" or not contact.email \
            else contact.email
        line = f"[{channel} to {contact.name} {target}] {text}"
        self.__deliver(line)
        return line

    def notify_office(self, template: str, **values: str) -> str:
        """Alert office staff (dispatch screen and log)."""
        try:
            text = self.__config.template(template).format(**values)
        except KeyError:
            text = f"{template}: {values}"
        line = f"[ALERT to {self.OFFICE}] {text}"
        self.__deliver(line)
        return line

    def send_quote(self, contact, request) -> str:
        """Send the quote link to the customer (Task 2.4)."""
        quote = request.current_quote
        return self.send(contact, "Quote", ref=request.request_id,
                         amount=f"{quote.amount:.2f}",
                         expiry=f"{quote.expires_at:%a %d %b %H:%M}")

    def drain(self) -> list[str]:
        """Return and clear messages not yet shown on screen."""
        shown, self.__recent = self.__recent, []
        return shown

    def __deliver(self, line: str) -> None:
        self.__recent.append(line)
        if self.__outbox is None:
            return
        try:
            self.__outbox.post(self.__clock.now(), line)
        except OSError:
            # DA13: a notification failure must never stop the business.
            pass
