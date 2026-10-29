"""Registry: the collections of customers, staff, requests, deliveries.

In Assignment 2 the Registry both kept the collections *and* hid the
storage.  The detailed design splits these: Registry keeps and searches
the live objects; JsonDataStore (Data Mapper) converts them to and from
the file.  Domain classes only ever see the Registry (DA2).
"""

from datetime import datetime

from yowd.domain.errors import NotFoundError
from yowd.domain.statuses import PaymentMethod, PaymentStatus, RequestStatus


class Registry:
    """Finds and stores domain objects; does not own their life cycle."""

    __WIDTHS = {"C": 3, "S": 3, "D": 3, "R": 4, "Q": 4, "A": 4, "P": 4,
                "AV": 3, "INV": 5, "YW": 5}
    __slots__ = ("__customers", "__office", "__drivers", "__requests",
                 "__deliveries", "__counters")

    def __init__(self, counters: dict[str, int] | None = None) -> None:
        self.__customers: dict[str, object] = {}
        self.__office: dict[str, object] = {}
        self.__drivers: dict[str, object] = {}
        self.__requests: dict[str, object] = {}
        self.__deliveries: dict[str, object] = {}
        self.__counters: dict[str, int] = dict(counters or {})

    @property
    def counters(self) -> dict[str, int]:
        """A copy of the id counters (for saving)."""
        return dict(self.__counters)

    # --------------------------------------------------------------- ids
    def next_id(self, prefix: str) -> str:
        """Next identifier for a prefix, e.g. R0007 or YW10003."""
        start = 10000 if prefix == "YW" else 0
        value = self.__counters.get(prefix, start) + 1
        self.__counters[prefix] = value
        return f"{prefix}{value:0{self.__WIDTHS.get(prefix, 4)}d}"

    # --------------------------------------------------------- customers
    def add_customer(self, customer) -> None:
        """Register a customer."""
        self.__customers[customer.customer_id] = customer

    def customers(self) -> list:
        """All customers."""
        return list(self.__customers.values())

    def customer(self, customer_id: str):
        """Customer by id."""
        return self.__get(self.__customers, customer_id, "Customer")

    def find_customer(self, email_or_phone: str):
        """Returning customer by email or phone, or None (Task 1a)."""
        key = email_or_phone.strip().lower().replace(" ", "")
        for customer in self.__customers.values():
            if key and key in (customer.contact.email,
                               customer.contact.phone):
                return customer
        return None

    # ------------------------------------------------------------- staff
    def add_office_staff(self, staff) -> None:
        """Register an office staff member."""
        self.__office[staff.staff_id] = staff

    def add_delivery_staff(self, staff) -> None:
        """Register a delivery staff member."""
        self.__drivers[staff.staff_id] = staff

    def office_staff(self, staff_id: str):
        """Active office staff member by id."""
        staff = self.__get(self.__office, staff_id.upper(), "Office staff")
        if not staff.active:
            raise NotFoundError(f"{staff_id} is no longer active.")
        return staff

    def delivery_staff(self, staff_id: str):
        """Delivery staff member by id (active or not)."""
        return self.__get(self.__drivers, staff_id.upper(), "Delivery staff")

    def all_delivery_staff(self) -> list:
        """Every driver, including inactive ones (history kept)."""
        return list(self.__drivers.values())

    def all_office_staff(self) -> list:
        """Every office staff member."""
        return list(self.__office.values())

    def active_delivery_staff(self) -> list:
        """Drivers who can be allocated work."""
        return [s for s in self.__drivers.values() if s.active]

    # ---------------------------------------------------------- requests
    def add_request(self, request) -> None:
        """Store a new delivery request."""
        self.__requests[request.request_id] = request

    def request(self, request_id: str):
        """Request by id."""
        return self.__get(self.__requests, request_id.upper(), "Request")

    def requests(self) -> list:
        """All requests, oldest first."""
        return list(self.__requests.values())

    def requests_for(self, customer) -> list:
        """A customer's own requests (QS2)."""
        return [r for r in self.__requests.values()
                if r.customer is customer]

    def requests_for_review(self) -> list:
        """Flagged requests waiting for the office (Task 1c)."""
        return [r for r in self.__requests.values() if r.needs_office_review]

    def expire_due_quotes(self, now: datetime) -> list:
        """Expire unanswered quotes; return the affected requests."""
        return [r for r in self.__requests.values()
                if r.expire_quote_if_due(now)]

    def quotes_awaiting(self, customer, now: datetime) -> list:
        """Requests of this customer with an open quote (Task 3.2)."""
        self.expire_due_quotes(now)
        return [r for r in self.requests_for(customer)
                if r.status is RequestStatus.QUOTED]

    # -------------------------------------------------------- deliveries
    def add_delivery(self, delivery) -> None:
        """Store a delivery created from an accepted request."""
        self.__deliveries[delivery.tracking_ref] = delivery

    def delivery(self, tracking_ref: str):
        """Delivery by tracking reference."""
        return self.__get(self.__deliveries, tracking_ref.strip().upper(),
                          "Delivery")

    def deliveries(self) -> list:
        """All deliveries."""
        return list(self.__deliveries.values())

    def active_allocations_for(self, staff_id: str) -> list:
        """Offered or acknowledged allocations of one driver."""
        return [d.current_allocation for d in self.__deliveries.values()
                if d.current_allocation is not None
                and d.current_allocation.staff.staff_id == staff_id]

    def unreconciled_cash(self, staff_id: str) -> list:
        """Cash payments held by a driver and not yet reconciled."""
        return [p for d in self.__deliveries.values() for p in d.payments
                if p.staff_id == staff_id
                and p.method is PaymentMethod.CASH
                and p.status is PaymentStatus.COMPLETED]

    # ------------------------------------------------------------ helper
    @staticmethod
    def __get(collection: dict, key: str, label: str):
        try:
            return collection[key]
        except KeyError as exc:
            raise NotFoundError(f"{label} '{key}' was not found. Check the "
                                "reference and try again.") from exc
