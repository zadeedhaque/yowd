"""JsonDataStore: saves and reloads the Registry as one JSON document.

The brief allows files instead of a database.  This class is a Data
Mapper implementing the RecordStore port: domain classes contain no
storage code.  It reads objects only through their public properties
and rebuilds them only through their ``restore`` class methods, so it
never touches private state.  The document itself lives in a
TextStorage (a file on disk, or the browser's storage in the web UI).
"""

import json
from datetime import date, datetime
from decimal import Decimal

from yowd.domain.address import Address
from yowd.domain.allocation import Allocation
from yowd.domain.delivery import Delivery, DeliveryEvent
from yowd.domain.delivery_request import DeliveryRequest
from yowd.domain.parcel import Parcel
from yowd.domain.payment import Payment
from yowd.domain.people import (AvailabilityPeriod, Customer, DeliveryStaff,
                                OfficeStaff, Recipient)
from yowd.domain.ports import RecordStore, TextStorage, VerificationResult
from yowd.domain.quote import Quote
from yowd.domain.statuses import (AllocationStatus, DeliveryStatus,
                                  PaymentMethod, PaymentStatus, QuoteStatus,
                                  RequestStatus, StaffRole)
from yowd.domain.values import ContactDetails, TimeWindow
from yowd.persistence.registry import Registry


class JsonCodec:
    """Converts value objects to and from JSON-friendly values."""

    @staticmethod
    def moment(value: datetime | None) -> str | None:
        """datetime -> ISO text."""
        return value.isoformat() if value else None

    @staticmethod
    def to_moment(value: str | None) -> datetime | None:
        """ISO text -> datetime."""
        return datetime.fromisoformat(value) if value else None

    @staticmethod
    def window(window: TimeWindow) -> list[str]:
        """TimeWindow -> [start, end]."""
        return [window.start.isoformat(), window.end.isoformat()]

    @staticmethod
    def to_window(raw: list[str]) -> TimeWindow:
        """[start, end] -> TimeWindow."""
        return TimeWindow(datetime.fromisoformat(raw[0]),
                          datetime.fromisoformat(raw[1]))

    @staticmethod
    def contact(contact: ContactDetails) -> dict:
        """ContactDetails -> dict."""
        return {"name": contact.name, "phone": contact.phone,
                "email": contact.email, "channel": contact.preferred_channel}

    @staticmethod
    def to_contact(raw: dict) -> ContactDetails:
        """dict -> ContactDetails."""
        return ContactDetails(raw["name"], raw["phone"], raw["email"],
                              raw["channel"])

    @classmethod
    def address(cls, address: Address) -> dict:
        """Address -> dict (including its verification result)."""
        loc = address.location
        return {"street": address.street, "suburb": address.suburb,
                "postcode": address.postcode, "state": address.state,
                "instructions": address.instructions,
                "verified": address.verified,
                "in_area": address.in_operating_area,
                "problem": address.problem,
                "loc": None if loc is None else [loc.latitude,
                                                 loc.longitude]}

    @staticmethod
    def to_address(raw: dict) -> Address:
        """dict -> Address."""
        location = None
        if raw["loc"]:
            location = VerificationResult(True, raw["suburb"],
                                          raw["postcode"], *raw["loc"])
        return Address.restore(raw["street"], raw["suburb"], raw["postcode"],
                               raw["state"], raw["instructions"],
                               raw["verified"], raw["in_area"],
                               raw["problem"], location)


class JsonDataStore(RecordStore):
    """Reads and writes every record as one JSON document."""

    __slots__ = ("__storage", "__config", "__codec")

    def __init__(self, storage: TextStorage, config) -> None:
        self.__storage = storage
        self.__config = config
        self.__codec = JsonCodec()

    # =============================================================== save
    def save(self, registry: Registry) -> None:
        """Write everything (the storage makes the write atomic, QR4)."""
        codec = self.__codec
        data = {
            "counters": registry.counters,
            "customers": [self.__customer(c) for c in registry.customers()],
            "office_staff": [{"id": s.staff_id,
                              "contact": codec.contact(s.contact),
                              "role": s.role.name, "active": s.active}
                             for s in registry.all_office_staff()],
            "delivery_staff": [self.__driver(s)
                               for s in registry.all_delivery_staff()],
            "requests": [self.__request(r) for r in registry.requests()],
            "deliveries": [self.__delivery(d)
                           for d in registry.deliveries()],
        }
        self.__storage.write(json.dumps(data, indent=1))

    def __customer(self, customer: Customer) -> dict:
        codec = self.__codec
        return {"id": customer.customer_id,
                "contact": codec.contact(customer.contact),
                "login": customer.has_login,
                "addresses": [codec.address(a)
                              for a in customer.saved_addresses],
                "recipients": [codec.contact(r.contact)
                               for r in customer.saved_recipients]}

    def __driver(self, staff: DeliveryStaff) -> dict:
        codec = self.__codec
        return {"id": staff.staff_id, "contact": codec.contact(staff.contact),
                "active": staff.active,
                "availability": [{"id": p.period_id,
                                  "window": codec.window(p.window),
                                  "weekly": p.weekly}
                                 for p in staff.availability]}

    def __request(self, request: DeliveryRequest) -> dict:
        codec = self.__codec
        return {
            "id": request.request_id,
            "customer": request.customer.customer_id,
            "pickup": codec.address(request.pickup),
            "dropoff": codec.address(request.dropoff),
            "recipient": codec.contact(request.recipient.contact),
            "pin": request.recipient.handover_pin,
            "preferred": request.preferred_date.isoformat(),
            "created": codec.moment(request.created_at),
            "created_by": request.created_by,
            "status": request.status.name, "flags": list(request.flags),
            "parcels": [{"desc": p.description, "cat": p.category,
                         "dims": [str(p.length_cm), str(p.width_cm),
                                  str(p.height_cm)],
                         "kg": str(p.weight_kg), "collected": p.collected}
                        for p in request.parcels],
            "quotes": [{"id": q.quote_id, "amount": str(q.amount),
                        "original": str(q.original_amount),
                        "pickup": codec.window(q.pickup_window),
                        "delivery": codec.window(q.delivery_window),
                        "issued": codec.moment(q.issued_at),
                        "expires": codec.moment(q.expires_at),
                        "km": q.distance_km,
                        "lines": [[label, str(amount)]
                                  for label, amount in q.breakdown],
                        "status": q.status.name,
                        "by": q.overridden_by, "why": q.override_reason,
                        "responded": codec.moment(q.responded_at)}
                       for q in request.quotes],
        }

    def __delivery(self, delivery: Delivery) -> dict:
        codec = self.__codec
        return {
            "ref": delivery.tracking_ref,
            "request": delivery.request.request_id,
            "quote": delivery.quote.quote_id,
            "events": [{"status": e.status.name,
                        "at": codec.moment(e.occurred_at),
                        "recorded": codec.moment(e.recorded_at),
                        "actor": e.actor_id, "note": e.note,
                        "changes": e.changes_status, "proof": dict(e.proof)}
                       for e in delivery.events],
            "allocations": [{"id": a.allocation_id,
                             "staff": a.staff.staff_id,
                             "window": codec.window(a.window),
                             "by": a.allocated_by,
                             "offered": codec.moment(a.offered_at),
                             "status": a.status.name,
                             "ack": codec.moment(a.acknowledged_at),
                             "closed": codec.moment(a.closed_at),
                             "reason": a.reason}
                            for a in delivery.allocations],
            "payments": [{"id": p.payment_id, "amount": str(p.amount),
                          "method": p.method.name, "staff": p.staff_id,
                          "taken": codec.moment(p.taken_at),
                          "status": p.status.name,
                          "provider": p.provider_reference,
                          "rec_by": p.reconciled_by,
                          "rec_at": codec.moment(p.reconciled_at),
                          "receipt": None if p.receipt is None else
                          p.receipt.number}
                         for p in delivery.payments],
        }

    # =============================================================== load
    def load(self) -> Registry:
        """Rebuild the Registry from storage (bootstrap step 5)."""
        if not self.__storage.exists():
            return Registry()
        data = json.loads(self.__storage.read())
        registry = Registry(data["counters"])
        codec = self.__codec
        for raw in data["customers"]:
            registry.add_customer(Customer(
                raw["id"], codec.to_contact(raw["contact"]), raw["login"],
                [codec.to_address(a) for a in raw["addresses"]],
                [Recipient(codec.to_contact(c)) for c in raw["recipients"]]))
        for raw in data["office_staff"]:
            registry.add_office_staff(OfficeStaff(
                raw["id"], codec.to_contact(raw["contact"]),
                StaffRole[raw["role"]], raw["active"]))
        for raw in data["delivery_staff"]:
            registry.add_delivery_staff(DeliveryStaff(
                raw["id"], codec.to_contact(raw["contact"]), raw["active"],
                [AvailabilityPeriod(p["id"], codec.to_window(p["window"]),
                                    p["weekly"])
                 for p in raw["availability"]]))
        for raw in data["requests"]:
            registry.add_request(self.__to_request(raw, registry))
        for raw in data["deliveries"]:
            registry.add_delivery(self.__to_delivery(raw, registry))
        return registry

    def __to_request(self, raw: dict, registry: Registry) -> DeliveryRequest:
        codec = self.__codec
        parcels = []
        for item in raw["parcels"]:
            parcel = Parcel(item["desc"], item["cat"], *item["dims"],
                            item["kg"], self.__config)
            if item["collected"]:
                parcel.mark_collected()
            parcels.append(parcel)
        quotes = [Quote.restore(
            item["id"], Decimal(item["amount"]), Decimal(item["original"]),
            codec.to_window(item["pickup"]),
            codec.to_window(item["delivery"]),
            codec.to_moment(item["issued"]), codec.to_moment(item["expires"]),
            item["km"], [(label, Decimal(amount))
                         for label, amount in item["lines"]],
            QuoteStatus[item["status"]], item["by"], item["why"],
            codec.to_moment(item["responded"])) for item in raw["quotes"]]
        return DeliveryRequest.restore(
            raw["id"], registry.customer(raw["customer"]),
            codec.to_address(raw["pickup"]), codec.to_address(raw["dropoff"]),
            Recipient(codec.to_contact(raw["recipient"]), raw["pin"]),
            date.fromisoformat(raw["preferred"]),
            codec.to_moment(raw["created"]), raw["created_by"], parcels,
            quotes, RequestStatus[raw["status"]], raw["flags"])

    def __to_delivery(self, raw: dict, registry: Registry) -> Delivery:
        codec = self.__codec
        request = registry.request(raw["request"])
        quote = next(q for q in request.quotes if q.quote_id == raw["quote"])
        delivery = Delivery.restore(raw["ref"], request, quote,
                                    self.__config, [
            DeliveryEvent(DeliveryStatus[e["status"]],
                          codec.to_moment(e["at"]),
                          codec.to_moment(e["recorded"]), e["actor"],
                          e["note"], e["changes"], e["proof"])
            for e in raw["events"]])
        for item in raw["allocations"]:
            delivery.add_allocation(Allocation.restore(
                item["id"], delivery, registry.delivery_staff(item["staff"]),
                codec.to_window(item["window"]), item["by"],
                codec.to_moment(item["offered"]),
                AllocationStatus[item["status"]],
                codec.to_moment(item["ack"]), codec.to_moment(item["closed"]),
                item["reason"]))
        for item in raw["payments"]:
            payment = Payment.restore(
                item["id"], delivery, Decimal(item["amount"]),
                PaymentMethod[item["method"]], item["staff"],
                codec.to_moment(item["taken"]), item["provider"],
                PaymentStatus[item["status"]], item["rec_by"],
                codec.to_moment(item["rec_at"]))
            if item["receipt"]:
                payment.issue_receipt(self.__config, item["receipt"])
            delivery.add_payment(payment)
        return delivery
