"""DeliveryManagementSystem: the single entry point (Facade).

It starts the system in a fixed order (bootstrap), checks the acting
user's role, passes each request to the domain object responsible for
it, and saves the records after every change.  It holds no business
rules itself (Riel H4).

Every collaborator that touches the outside world - the clock, storage,
address and payment providers - is passed in (dependency injection), so
a unit test can build the whole system in memory with a FixedClock.
"""

from datetime import datetime

from yowd.app.input_parser import InputParser
from yowd.app.seed import SampleDataSeeder
from yowd.app.workspace import Workspace
from yowd.config.system_configuration import SystemConfiguration
from yowd.domain.address import Address
from yowd.domain.clock import SystemClock
from yowd.domain.delivery_request import DeliveryRequest
from yowd.domain.dispatcher import Dispatcher
from yowd.domain.errors import (AuthorisationError, BusinessRuleError,
                                DmsError, NotFoundError, ValidationError)
from yowd.domain.field_action import (FieldAction, FieldServices,
                                      OfflineSyncQueue)
from yowd.domain.parcel import Parcel
from yowd.domain.people import (AvailabilityPeriod, Customer, DeliveryStaff,
                                OfficeStaff, Recipient)
from yowd.domain.ports import AddressService, Clock, PaymentGateway
from yowd.domain.pricing import PricingPolicy
from yowd.domain.statistics import StatisticsCalculator, StatisticsReport
from yowd.domain.statuses import FieldActionKind, RequestStatus
from yowd.domain.values import ContactDetails, ReportPeriod
from yowd.persistence.json_store import JsonDataStore
from yowd.services.address_service import GazetteerAddressService
from yowd.services.notification_service import NotificationService
from yowd.services.outbox import StorageOutbox
from yowd.services.payment_gateway import SimulatedPaymentGateway


class DeliveryManagementSystem:
    """Facade between any user interface and the domain."""

    __slots__ = ("__workspace", "__clock", "__parser", "__config",
                 "__addresses", "__gateway", "__notifier", "__store",
                 "__registry", "__dispatcher", "__pricing", "__statistics")

    def __init__(self, workspace: Workspace, clock: Clock | None = None,
                 address_service: AddressService | None = None,
                 payment_gateway: PaymentGateway | None = None) -> None:
        self.__workspace = workspace
        self.__clock = clock or SystemClock()
        self.__parser = InputParser()
        self.__bootstrap(address_service or GazetteerAddressService(),
                         payment_gateway or SimulatedPaymentGateway())

    # ========================================================= bootstrap
    def __bootstrap(self, addresses: AddressService,
                    gateway: PaymentGateway) -> None:
        """Create the long-lived objects in dependency order."""
        # 2. Business settings - everything below reads them.
        self.__config = SystemConfiguration.load(self.__workspace.config())
        # 3. External service adapters (injected or the defaults).
        self.__addresses = addresses
        self.__gateway = gateway
        # 4. Notification service must exist before deliveries load.
        self.__notifier = NotificationService(
            self.__config, self.__clock,
            StorageOutbox(self.__workspace.outbox()))
        # 5. Registry rebuilt from storage (seeded on first run).
        self.__store = JsonDataStore(self.__workspace.records(),
                                     self.__config)
        self.__registry = self.__store.load()
        if not self.__registry.all_office_staff():
            SampleDataSeeder(self.__registry, self.__config, self.__clock,
                             self.__addresses).seed()
        # 6. Dispatcher, registered as listener of every driver; the
        #    notifier observes every delivery.
        self.__dispatcher = Dispatcher(self.__registry, self.__config,
                                       self.__clock, self.__notifier)
        for staff in self.__registry.all_delivery_staff():
            staff.add_listener(self.__dispatcher)
        for delivery in self.__registry.deliveries():
            delivery.add_observer(self.__notifier)
        # 7. PricingPolicy needs settings, AddressService and Dispatcher.
        self.__pricing = PricingPolicy(self.__config, self.__addresses,
                                       self.__dispatcher)
        # 8. StatisticsCalculator needs only the Registry.
        self.__statistics = StatisticsCalculator(self.__registry)
        # Housekeeping: expire quotes that ran out while closed.
        self.__registry.expire_due_quotes(self.__clock.now())
        self.save()

    def save(self) -> None:
        """Persist every record (called after each change)."""
        self.__store.save(self.__registry)

    # ===================================================== screen support
    def now(self) -> datetime:
        """Current Melbourne time, for screens."""
        return self.__clock.now()

    @property
    def parser(self) -> InputParser:
        """Shared input parsing rules."""
        return self.__parser

    def heading(self) -> str:
        """Business name and area shown on the home screen (SRS D3)."""
        return (f"{self.__config.business_name} - "
                f"{self.__config.operating_area_name}")

    def parcel_categories(self) -> tuple[list[str], list[str]]:
        """(categories carried, categories refused)."""
        return (self.__config.parcel_categories,
                self.__config.prohibited_categories)

    def known_suburbs(self) -> list[tuple[str, str]]:
        """(suburb, postcode) pairs the address service knows, if any."""
        return self.__addresses.suburbs()

    def recent_notifications(self) -> list[str]:
        """Messages sent since the screen last asked."""
        return self.__notifier.drain()

    # ======================================================= customers
    def register_customer(self, name: str, phone: str, email: str,
                          channel: str = "SMS",
                          has_login: bool = True) -> Customer:
        """Create a customer without duplicates (Task 1.1)."""
        contact = ContactDetails(name, phone, email, channel)
        for key in (contact.email, contact.phone):
            existing = self.__registry.find_customer(key) if key else None
            if existing is not None:
                raise BusinessRuleError(
                    f"A customer with {key} already exists "
                    f"({existing.customer_id}). Log in instead.")
        customer = Customer(self.__registry.next_id("C"), contact,
                            has_login)
        self.__registry.add_customer(customer)
        self.save()
        return customer

    def find_customer(self, email_or_phone: str) -> Customer:
        """Returning customer (Task 1 variant a)."""
        customer = self.__registry.find_customer(email_or_phone)
        if customer is None:
            raise NotFoundError("No customer has that email or phone. "
                                "Check it or register as a new customer.")
        return customer

    def lookup_customer(self, email_or_phone: str) -> Customer | None:
        """Customer by email or phone, or None (walk-in, Task 1b)."""
        return self.__registry.find_customer(email_or_phone)

    # ======================================================== requests
    def make_address(self, street: str, suburb: str, postcode: str,
                     instructions: str = "") -> Address:
        """Validate address fields as they are entered (P2)."""
        return Address(street, suburb, postcode, "VIC", instructions)

    def make_recipient(self, name: str, phone: str,
                       email: str = "") -> Recipient:
        """Validate recipient details as they are entered."""
        return Recipient(ContactDetails(name, phone, email))

    def make_parcel(self, description: str, category: str, length: str,
                    width: str, height: str, weight: str) -> Parcel:
        """Validate a parcel as it is entered (Parcel checks itself)."""
        return Parcel(description, category, length, width, height,
                      weight, self.__config)

    def parse_preferred_date(self, raw: str):
        """Preferred pickup date: today up to 14 days ahead."""
        return self.__parser.preferred_date(raw, self.now().date())

    def submit_request(self, customer: Customer, pickup: Address,
                       dropoff: Address, recipient: Recipient,
                       parcels: list[Parcel], preferred,
                       actor_id: str) -> DeliveryRequest:
        """Log a request (Task 1) and quote it straight away (Task 2).

        A request with an unverified or out-of-area address is saved but
        flagged for office review instead of being priced.
        """
        now = self.now()
        request = DeliveryRequest(self.__registry.next_id("R"), customer,
                                  pickup, dropoff, recipient, preferred,
                                  now, actor_id)
        for parcel in parcels:
            request.add_parcel(parcel)
        clean = request.check_addresses(self.__addresses, self.__config)
        self.__registry.add_request(request)
        customer.remember_address(pickup)
        customer.remember_recipient(recipient)
        if clean:
            request.add_quote(self.__pricing.create_quote(
                self.__registry.next_id("Q"), request, now))
            self.__notifier.send_quote(customer.contact, request)
        else:
            self.__notifier.notify_office("Review", ref=request.request_id)
        self.save()
        return request

    def quotes_awaiting(self, customer: Customer) -> list[DeliveryRequest]:
        """Customer's quotes still waiting for an answer (Task 3.2)."""
        result = self.__registry.quotes_awaiting(customer, self.now())
        self.save()
        return result

    def requests_of(self, customer: Customer) -> list[DeliveryRequest]:
        """All of a customer's requests (QS2: only their own)."""
        return self.__registry.requests_for(customer)

    def respond_to_quote(self, customer: Customer, request_id: str,
                         accept: bool):
        """Accept (creates the Delivery) or decline a quote (Task 3)."""
        request = self.__registry.request(request_id)
        if request.customer is not customer:
            raise AuthorisationError("You can only answer your own "
                                     "quotes.")
        now = self.now()
        try:
            if not accept:
                request.decline_quote(now)
                return None
            delivery = request.accept_quote(self.__registry.next_id("YW"),
                                            self.__config, now)
            delivery.add_observer(self.__notifier)
            delivery.start(customer.customer_id, now)
            self.__registry.add_delivery(delivery)
            return delivery
        finally:
            self.save()

    # ===================================================== office staff
    def login_office(self, staff_id: str) -> OfficeStaff:
        """Sign-in is provided by the platform (DA4); look up the user."""
        return self.__registry.office_staff(staff_id.strip())

    def requests_for_review(self, officer: OfficeStaff) -> list:
        """Flagged requests (Task 1 variant c)."""
        self.__office_only(officer)
        return self.__registry.requests_for_review()

    def manual_quote(self, officer: OfficeStaff, request_id: str,
                     amount: str, reason: str) -> DeliveryRequest:
        """Office prices a flagged request by hand."""
        self.__office_only(officer)
        request = self.__registry.request(request_id)
        if not request.needs_office_review:
            raise BusinessRuleError(f"{request_id} is not waiting for "
                                    "review.")
        if not reason.strip():
            raise ValidationError("Enter a reason for the manual price.")
        request.add_quote(self.__pricing.create_quote(
            self.__registry.next_id("Q"), request, self.now(),
            self.__parser.money(amount), officer.staff_id, reason.strip()))
        self.__notifier.send_quote(request.customer.contact, request)
        self.save()
        return request

    def reject_request(self, officer: OfficeStaff, request_id: str,
                       reason: str) -> None:
        """Office cancels a request YOWD cannot serve."""
        self.__office_only(officer)
        if not reason.strip():
            raise ValidationError("Enter a reason the customer will see.")
        self.__registry.request(request_id).cancel(reason.strip())
        self.save()

    def override_quote(self, officer: OfficeStaff, request_id: str,
                       amount: str, reason: str) -> DeliveryRequest:
        """Office changes an open quote's price with a reason (T2.3)."""
        self.__office_only(officer)
        request = self.__registry.request(request_id)
        if request.status is not RequestStatus.QUOTED:
            raise BusinessRuleError(f"{request_id} has no open quote.")
        request.current_quote.override_price(
            officer.staff_id, self.__parser.money(amount), reason)
        self.__notifier.send_quote(request.customer.contact, request)
        self.save()
        return request

    def unallocated(self, officer: OfficeStaff) -> list:
        """Deliveries awaiting allocation, in pickup order (Task 5.1)."""
        self.__office_only(officer)
        self.__dispatcher.check_acknowledgements()
        self.save()
        return self.__dispatcher.unallocated()

    def candidates_for(self, officer: OfficeStaff, tracking_ref: str):
        """Drivers free for the delivery's pickup window (Task 5.2)."""
        self.__office_only(officer)
        delivery = self.__registry.delivery(tracking_ref)
        return self.__dispatcher.available_staff(
            delivery.quote.pickup_window)

    def allocate(self, officer: OfficeStaff, tracking_ref: str,
                 staff_id: str):
        """Office confirms the allocation (Task 5.3)."""
        self.__office_only(officer)
        delivery = self.__registry.delivery(tracking_ref)
        staff = self.__registry.delivery_staff(staff_id)
        allocation = self.__dispatcher.allocate(delivery, staff, officer)
        self.save()
        return allocation

    def reconcile_cash(self, officer: OfficeStaff, staff_id: str) -> list:
        """Mark a driver's cash as handed in (DA11)."""
        self.__office_only(officer)
        payments = self.__registry.unreconciled_cash(staff_id.strip().upper())
        if not payments:
            raise BusinessRuleError(f"{staff_id} holds no unreconciled "
                                    "cash.")
        for payment in payments:
            payment.reconcile(officer.staff_id, self.now())
        self.save()
        return payments

    def cash_holders(self, officer: OfficeStaff) -> list:
        """(driver, unreconciled payments) for drivers holding cash."""
        self.__office_only(officer)
        holders = []
        for staff in self.__registry.all_delivery_staff():
            cash = self.__registry.unreconciled_cash(staff.staff_id)
            if cash:
                holders.append((staff, cash))
        return holders

    def open_quotes(self, officer: OfficeStaff) -> list[DeliveryRequest]:
        """Requests with a quote awaiting the customer (for overrides)."""
        self.__office_only(officer)
        self.__registry.expire_due_quotes(self.now())
        return [r for r in self.__registry.requests()
                if r.status is RequestStatus.QUOTED]

    # ============================================================ owner
    def statistics(self, owner: OfficeStaff, kind: str, reference: str,
                   staff_id: str = "") -> StatisticsReport:
        """Statistics for a period, overall or per driver (Task 9)."""
        self.__office_only(owner)
        owner.require_owner("view business statistics")
        ref_date = self.__parser.report_date(reference, self.now().date())
        staff = self.__registry.delivery_staff(staff_id) if staff_id \
            else None
        return self.__statistics.report(ReportPeriod(kind, ref_date), staff)

    def parse_report_date(self, raw: str):
        """Reference date for a report; blank means today."""
        return self.__parser.report_date(raw, self.now().date())

    def export_statistics(self, report: StatisticsReport) -> str:
        """Save the report as CSV (P5); return the file name."""
        name = report.file_name()
        self.__workspace.export(name).write(report.to_csv())
        return name

    def staff_overview(self, owner: OfficeStaff) -> list:
        """Every driver with their number of open jobs (Task 10)."""
        self.__office_only(owner)
        owner.require_owner("manage delivery staff")
        return [(s, len(self.__registry.active_allocations_for(s.staff_id)))
                for s in self.__registry.all_delivery_staff()]

    def add_driver(self, owner: OfficeStaff, name: str, phone: str,
                   email: str) -> DeliveryStaff:
        """Owner adds a delivery staff member (Task 10)."""
        self.__office_only(owner)
        owner.require_owner("add delivery staff")
        contact = ContactDetails(name, phone, email)
        staff = DeliveryStaff(self.__registry.next_id("D"), contact)
        staff.add_listener(self.__dispatcher)
        self.__registry.add_delivery_staff(staff)
        self.save()
        return staff

    def deactivate_driver(self, owner: OfficeStaff, staff_id: str) -> list:
        """Mark a leaver inactive and release their jobs (Task 10)."""
        self.__office_only(owner)
        owner.require_owner("remove delivery staff")
        staff = self.__registry.delivery_staff(staff_id)
        staff.deactivate()
        released = self.__dispatcher.staff_deactivated(staff,
                                                       owner.staff_id)
        self.save()
        return released

    # ========================================================= drivers
    def login_driver(self, staff_id: str) -> DeliveryStaff:
        """Look up an active driver (sign-in by the platform, DA4)."""
        staff = self.__registry.delivery_staff(staff_id.strip())
        if not staff.active:
            raise AuthorisationError(f"{staff_id} is no longer active.")
        return staff

    def device_queue(self, staff: DeliveryStaff) -> OfflineSyncQueue:
        """The driver's on-device queue (bootstrap step 9)."""
        return OfflineSyncQueue(staff.staff_id,
                                self.__workspace.device_queue(staff.staff_id))

    def jobs_of(self, staff: DeliveryStaff) -> list:
        """Active allocations of a driver, in pickup order (QS2)."""
        self.__dispatcher.check_acknowledgements()
        jobs = self.__registry.active_allocations_for(staff.staff_id)
        return sorted(jobs, key=lambda a: a.window.start)

    def acknowledge(self, staff: DeliveryStaff, tracking_ref: str):
        """Driver accepts an offered job (Task 5.4)."""
        delivery = self.__registry.delivery(tracking_ref)
        allocation = delivery.current_allocation
        if allocation is None:
            raise BusinessRuleError(f"{tracking_ref} is not allocated.")
        allocation.acknowledge(staff.staff_id, self.now())
        self.save()
        return allocation

    def parse_window(self, day: str, start: str, end: str):
        """Validate a day and two clock times typed by a driver."""
        return self.__parser.window(day, start, end)

    def declare_availability(self, staff: DeliveryStaff, day: str,
                             start: str, end: str,
                             weekly: bool) -> AvailabilityPeriod:
        """Driver declares a period (Task 4.1)."""
        period = staff.declare_availability(
            self.__parser.window(day, start, end), weekly, self.now(),
            lambda: self.__registry.next_id("AV"))
        self.save()
        return period

    def change_availability(self, staff: DeliveryStaff, period_id: str,
                            day: str, start: str, end: str):
        """Driver changes a declared period (Task 4.2)."""
        period = staff.change_availability(
            period_id.strip().upper(),
            self.__parser.window(day, start, end), self.now())
        self.save()
        return period

    def withdraw_availability(self, staff: DeliveryStaff, period_id: str):
        """Driver withdraws a period at short notice (Task 4.3)."""
        period = staff.withdraw_availability(period_id.strip().upper())
        self.save()
        return period

    def new_field_action(self, staff: DeliveryStaff, kind: FieldActionKind,
                         tracking_ref: str, data: dict | None = None,
                         online: bool = True) -> FieldAction:
        """Capture a doorstep action on the driver's device (Command)."""
        return FieldAction.create(kind, tracking_ref, staff.staff_id,
                                  self.now(), data, online)

    def perform_field_action(self, action: FieldAction) -> str:
        """Execute a FieldAction uploaded from a driver's device."""
        delivery = self.__registry.delivery(action.tracking_ref)
        services = FieldServices(self.__config, self.__gateway,
                                 self.__registry.next_id, self.now())
        try:
            return action.execute(delivery, services)
        except DmsError as error:
            if not action.captured_online:
                self.__notifier.notify_office(
                    "Sync conflict", ref=action.tracking_ref,
                    reason=str(error))
            raise
        finally:
            self.save()

    # ========================================================= tracking
    def track(self, tracking_ref: str):
        """Recipient/customer tracking by reference (Task 8)."""
        return self.__registry.delivery(tracking_ref)

    # =========================================================== private
    @staticmethod
    def __office_only(user) -> None:
        if not isinstance(user, OfficeStaff) or not user.active:
            raise AuthorisationError("Only active office staff can do "
                                     "this.")
