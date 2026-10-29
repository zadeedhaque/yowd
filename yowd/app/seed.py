"""SampleDataSeeder: first-run sample data (staff, customers, history).

Used only when no records exist, so a fresh install can be demonstrated
and the statistics have past deliveries to report on.  The seeder only
uses the public behaviour of the domain classes - it accepts quotes,
acknowledges allocations, takes payments and changes statuses exactly as
the real users would, just with past times.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from yowd.domain.address import Address
from yowd.domain.allocation import Allocation
from yowd.domain.clock import MELBOURNE
from yowd.domain.delivery_request import DeliveryRequest
from yowd.domain.parcel import Parcel
from yowd.domain.payment import Payment
from yowd.domain.people import (AvailabilityPeriod, Customer, DeliveryStaff,
                                OfficeStaff, Recipient)
from yowd.domain.ports import AddressService, Clock
from yowd.domain.quote import Quote
from yowd.domain.statuses import DeliveryStatus, PaymentMethod, StaffRole
from yowd.domain.values import ContactDetails, TimeWindow


class SampleDataSeeder:
    """Fills an empty Registry with a believable month of activity."""

    # (street, suburb, postcode) used for historical deliveries.
    __PLACES = (("88 Swan Street", "Richmond", "3121"),
                ("15 Nicholson Street", "Footscray", "3011"),
                ("201 Glenferrie Road", "Hawthorn", "3122"),
                ("4 Lygon Street", "Carlton", "3053"),
                ("77 Chapel Street", "Prahran", "3181"),
                ("9 Station Street", "Box Hill", "3128"),
                ("31 Sydney Road", "Brunswick", "3056"),
                ("120 Burke Road", "Camberwell", "3124"))
    # days ago, customer, pickup, drop-off, driver, outcome, method
    __PLAN = ((20, 0, 0, 1, 0, "delivered", PaymentMethod.CARD),
              (18, 1, 3, 2, 1, "delivered", PaymentMethod.CASH),
              (15, 2, 4, 5, 0, "late", PaymentMethod.CARD),
              (12, 1, 3, 6, 2, "delivered", PaymentMethod.CARD),
              (9, 0, 2, 7, 0, "failed", PaymentMethod.CASH),
              (6, 1, 3, 0, 1, "delivered", PaymentMethod.CARD),
              (3, 2, 5, 4, 0, "delivered", PaymentMethod.CASH),
              (1, 1, 6, 3, 2, "delivered", PaymentMethod.CASH))
    __OFFICE = "S002"

    __slots__ = ("__registry", "__config", "__clock", "__addresses")

    def __init__(self, registry, config, clock: Clock,
                 address_service: AddressService) -> None:
        self.__registry = registry
        self.__config = config
        self.__clock = clock
        self.__addresses = address_service

    def seed(self) -> None:
        """Create staff, availability, customers and past deliveries."""
        now = self.__clock.now()
        drivers = self.__add_people(now)
        customers = self.__registry.customers()
        for days, cust, pick, drop, drv, outcome, method in self.__PLAN:
            when = datetime.combine((now - timedelta(days=days)).date(),
                                    time(9, 0), MELBOURNE)
            request = self.__request(customers[cust], pick, drop, when)
            self.__run(request, drivers[drv], outcome, when, method,
                       reconciled=days > 2)
        declined_at = datetime.combine((now - timedelta(days=4)).date(),
                                       time(11, 0), MELBOURNE)
        declined = self.__request(customers[2], 0, 6, declined_at)
        declined.decline_quote(declined_at + timedelta(hours=1))
        tomorrow = datetime.combine(now.date(), time(8, 0),
                                    MELBOURNE) + timedelta(days=1)
        waiting = self.__request(customers[1], 3, 2, tomorrow)
        self.__accept(waiting, now)

    # ------------------------------------------------------------ people
    def __add_people(self, now: datetime) -> list[DeliveryStaff]:
        registry = self.__registry
        registry.add_office_staff(OfficeStaff(
            registry.next_id("S"),
            ContactDetails("Maya Fernando", "0390012001",
                           "maya@yowd.com.au"), StaffRole.OWNER))
        registry.add_office_staff(OfficeStaff(
            registry.next_id("S"),
            ContactDetails("Josh Patel", "0390012002", "josh@yowd.com.au")))
        monday = (now - timedelta(days=now.weekday() + 21)).date()
        drivers = []
        for name, phone, days, start, end in (
                ("Liam Nguyen", "0411222001", range(0, 5), 8, 18),
                ("Aisha Rahman", "0411222002", (1, 3, 5), 7, 15),
                ("Tom Walker", "0411222003", (0, 2, 4, 5), 12, 20)):
            staff = DeliveryStaff(
                registry.next_id("D"), ContactDetails(name, phone),
                availability=self.__weekly(monday, days, start, end))
            registry.add_delivery_staff(staff)
            drivers.append(staff)
        for name, phone, email in (
                ("Sarah Chen", "0422333001", "sarah.chen@example.com"),
                ("Bella's Bakery", "0398765432", "orders@bellas.com.au"),
                ("David Okafor", "0422333003", "d.okafor@example.com")):
            registry.add_customer(Customer(
                registry.next_id("C"), ContactDetails(name, phone, email)))
        return drivers

    def __weekly(self, monday: date, days, start: int,
                 end: int) -> list[AvailabilityPeriod]:
        return [AvailabilityPeriod(
            self.__registry.next_id("AV"),
            TimeWindow.on_day(monday + timedelta(days=offset), time(start),
                              time(end)), weekly=True) for offset in days]

    # ----------------------------------------------------------- history
    def __request(self, customer, pick: int, drop: int,
                  when: datetime) -> DeliveryRequest:
        """A verified request with one parcel and an issued quote."""
        registry, config = self.__registry, self.__config
        pickup = Address(*self.__PLACES[pick])
        dropoff = Address(*self.__PLACES[drop])
        request = DeliveryRequest(
            registry.next_id("R"), customer, pickup, dropoff,
            Recipient(ContactDetails("Alex Morgan", "0433444555")),
            when.date(), when, customer.customer_id)
        request.add_parcel(Parcel("Boxed goods", "General goods", "40",
                                  "30", "20", "3", config))
        request.check_addresses(self.__addresses, config)
        distance = self.__addresses.distance_km(pickup.location,
                                                dropoff.location)
        amount = max((config.rate("base_fee") + Decimal(str(distance))
                      * config.rate("per_km")).quantize(Decimal("0.01")),
                     config.rate("minimum_price"))
        pickup_w = TimeWindow(when + timedelta(hours=2),
                              when + timedelta(hours=4))
        request.add_quote(Quote(
            registry.next_id("Q"), amount, pickup_w,
            pickup_w.shifted(timedelta(hours=2)), when,
            when + timedelta(hours=24), distance))
        registry.add_request(request)
        return request

    def __accept(self, request: DeliveryRequest, when: datetime):
        delivery = request.accept_quote(self.__registry.next_id("YW"),
                                        self.__config, when)
        delivery.start(request.customer.customer_id, when)
        self.__registry.add_delivery(delivery)
        return delivery

    def __run(self, request, staff, outcome: str, when: datetime,
              method: PaymentMethod, reconciled: bool) -> None:
        """Run a request through its life cycle to ``outcome``."""
        registry, office = self.__registry, self.__OFFICE
        delivery = self.__accept(request, when)
        window = delivery.quote.pickup_window
        allocation = Allocation(registry.next_id("A"), delivery, staff,
                                window, office, when)
        delivery.add_allocation(allocation)
        delivery.change_status(DeliveryStatus.SCHEDULED, office, when, when)
        allocation.acknowledge(staff.staff_id, when + timedelta(minutes=4))
        start = window.start + timedelta(minutes=20)
        payment = Payment(registry.next_id("P"), delivery,
                          delivery.quote.amount, method, staff.staff_id,
                          start, "SIM-0900" if method is PaymentMethod.CARD
                          else "")
        if method is PaymentMethod.CASH and reconciled:
            payment.reconcile(office, start + timedelta(hours=8))
        payment.issue_receipt(self.__config, registry.next_id("INV"))
        delivery.add_payment(payment)
        for parcel in request.parcels:
            parcel.mark_collected()
        delivery.change_status(DeliveryStatus.PICKED_UP, staff.staff_id,
                               start, start, "1 parcel(s) collected")
        moved = start + timedelta(minutes=5)
        delivery.change_status(DeliveryStatus.IN_TRANSIT, staff.staff_id,
                               moved, moved, "Driver left for drop-off")
        end = delivery.quote.delivery_window.start + timedelta(minutes=30)
        if outcome == "late":
            end = delivery.quote.delivery_window.end + timedelta(minutes=40)
        if outcome == "failed":
            delivery.record_note(staff.staff_id, end, end,
                                 "Failed attempt: Recipient not home")
            later = end + timedelta(days=1)
            delivery.change_status(DeliveryStatus.FAILED, office, later,
                                   later, "Parcel damaged in transit")
        else:
            delivery.change_status(
                DeliveryStatus.DELIVERED, staff.staff_id, end, end,
                "Received by Alex Morgan",
                {"receiver_name": "Alex Morgan", "photo": "pod_photo.jpg",
                 "pin_checked": "yes"})
        allocation.complete(end)
