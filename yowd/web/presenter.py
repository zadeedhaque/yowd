"""Presenter: turns domain objects into plain dictionaries for the web.

Only this class knows the shape of the JSON the browser receives, so a
change to the page never reaches the domain (and vice versa).
"""

from decimal import Decimal


class Presenter:
    """Read-only views of domain objects (no business rules)."""

    @staticmethod
    def money(amount: Decimal) -> str:
        """'$44.44'"""
        return f"${amount:.2f}"

    @staticmethod
    def moment(value) -> str:
        """'Thu 29 Oct 15:00' or ''."""
        return f"{value:%a %d %b %H:%M}" if value else ""

    @classmethod
    def contact(cls, contact) -> dict:
        """Name, phone, email."""
        return {"name": contact.name, "phone": contact.phone,
                "email": contact.email,
                "channel": contact.preferred_channel}

    @classmethod
    def customer(cls, customer) -> dict:
        """A customer with saved addresses and recipients."""
        return {"id": customer.customer_id,
                "contact": cls.contact(customer.contact),
                "has_login": customer.has_login,
                "addresses": [cls.address(a)
                              for a in customer.saved_addresses],
                "recipients": [cls.contact(r.contact)
                               for r in customer.saved_recipients]}

    @staticmethod
    def address(address) -> dict:
        """Address fields plus a formatted line."""
        return {"street": address.street, "suburb": address.suburb,
                "postcode": address.postcode,
                "instructions": address.instructions,
                "line": address.formatted(), "problem": address.problem}

    @staticmethod
    def parcel(parcel) -> dict:
        """Parcel fields and summary."""
        return {"description": parcel.description,
                "category": parcel.category,
                "length": f"{parcel.length_cm:g}",
                "width": f"{parcel.width_cm:g}",
                "height": f"{parcel.height_cm:g}",
                "weight": f"{parcel.weight_kg:g}",
                "band": parcel.size_category, "summary": parcel.summary(),
                "collected": parcel.collected}

    @classmethod
    def quote(cls, quote) -> dict | None:
        """A quote with its itemised lines."""
        if quote is None:
            return None
        return {"id": quote.quote_id, "amount": cls.money(quote.amount),
                "lines": [[label, cls.money(amount)]
                          for label, amount in quote.breakdown],
                "pickup": quote.pickup_window.label(),
                "delivery": quote.delivery_window.label(),
                "expires": f"{quote.expires_at:%a %d %b %Y %H:%M}",
                "status": quote.status.value,
                "set_by": quote.overridden_by,
                "reason": quote.override_reason}

    @classmethod
    def request(cls, request) -> dict:
        """A delivery request and its latest quote."""
        delivery = request.delivery
        return {"id": request.request_id,
                "customer": request.customer.contact.name,
                "created": cls.moment(request.created_at),
                "pickup": cls.address(request.pickup),
                "dropoff": cls.address(request.dropoff),
                "recipient": cls.contact(request.recipient.contact),
                "parcels": [cls.parcel(p) for p in request.parcels],
                "status": request.status.value,
                "flags": list(request.flags),
                "quote": cls.quote(request.current_quote),
                "tracking": delivery.tracking_ref if delivery else "",
                "delivery_status": delivery.status.value if delivery else "",
                "pin": request.recipient.handover_pin if delivery else ""}

    @classmethod
    def delivery(cls, delivery, staff_view: bool = False) -> dict:
        """Tracking view; payments and allocations only for staff."""
        request = delivery.request
        allocation = delivery.current_allocation
        proof = dict(delivery.proof_of_delivery)
        view = {
            "ref": delivery.tracking_ref,
            "status": delivery.status.value,
            "from": request.pickup.suburb,
            "to": request.dropoff.formatted(),
            "recipient": request.recipient.contact.name,
            "parcels": len(request.parcels),
            "pickup": delivery.quote.pickup_window.label(),
            "delivery": delivery.quote.delivery_window.label(),
            "driver": (allocation.staff.contact.name.split()[0]
                       if allocation else ""),
            "proof": proof,
            "events": [{"when": cls.moment(e.occurred_at),
                        "status": e.status.value if e.changes_status
                        else "", "note": e.note}
                       for e in delivery.events],
        }
        if staff_view:
            view["allocations"] = [
                {"id": a.allocation_id, "staff": a.staff.staff_id,
                 "name": a.staff.contact.name, "status": a.status.value,
                 "offered": cls.moment(a.offered_at), "reason": a.reason}
                for a in delivery.allocations]
            view["payments"] = [
                {"id": p.payment_id, "amount": cls.money(p.amount),
                 "method": p.method.value, "status": p.status.value,
                 "receipt": p.receipt.lines() if p.receipt else []}
                for p in delivery.payments]
            view["owing"] = cls.money(delivery.amount_owing)
            view["customer"] = cls.contact(request.customer.contact)
        return view

    @classmethod
    def job(cls, allocation) -> dict:
        """A driver's job card."""
        delivery = allocation.delivery
        request = delivery.request
        return {"ref": delivery.tracking_ref,
                "window": allocation.window.label(),
                "job_status": allocation.status.value,
                "status": delivery.status.value,
                "pickup": cls.address(request.pickup),
                "dropoff": cls.address(request.dropoff),
                "customer": cls.contact(request.customer.contact),
                "recipient": cls.contact(request.recipient.contact),
                "parcels": [cls.parcel(p) for p in request.parcels],
                "owing": cls.money(delivery.amount_owing),
                "owing_value": str(delivery.amount_owing)}

    @staticmethod
    def staff(staff) -> dict:
        """Delivery or office staff summary."""
        return {"id": staff.staff_id, "name": staff.contact.name,
                "phone": staff.contact.phone,
                "active": staff.active}

    @staticmethod
    def period(period) -> dict:
        """An availability period."""
        return {"id": period.period_id, "label": period.label(),
                "weekly": period.weekly,
                "day": f"{period.window.start:%Y-%m-%d}",
                "start": f"{period.window.start:%H:%M}",
                "end": f"{period.window.end:%H:%M}"}

    @staticmethod
    def report(report) -> dict:
        """Statistics rows plus CSV text for download."""
        return {"rows": [list(row) for row in report.rows()],
                "csv": report.to_csv(), "file": report.file_name()}
