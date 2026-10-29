"""Customer portal screens (Tasks 1, 2, 3 and 8 for customers)."""

from yowd.domain.errors import DmsError
from yowd.ui.console import Console
from yowd.ui.request_form import QuoteScreen, RequestForm


class CustomerPortal:
    """Sign in or register, then log requests and answer quotes."""

    def __init__(self, console: Console, system) -> None:
        self.__io = console
        self.__system = system

    def run(self) -> None:
        """Entry point from the main menu."""
        self.__io.header("Customer portal", "Sign in")
        choice = self.__io.menu([("1", "I am a returning customer"),
                                 ("2", "Register as a new customer"),
                                 ("0", "Back to main menu")])
        if choice == "0":
            return
        customer = self.__sign_in() if choice == "1" else self.__register()
        if customer is not None:
            self.__home(customer)

    def __sign_in(self):
        key = self.__io.text("* Email or mobile number")
        try:
            customer = self.__system.find_customer(key)
        except DmsError as error:
            self.__io.error(str(error))
            return None
        self.__io.ok(f"Welcome back, {customer.contact.name}.")
        return customer

    def __register(self):
        self.__io.section("New customer details")
        while True:
            name = self.__io.text("* Full name or business name")
            phone = self.__io.text("* Mobile number", hint="04xx xxx xxx")
            email = self.__io.text("* Email")
            channel = self.__io.choose("* Send updates by SMS (S) or Email "
                                       "(E)", ["S", "E"])
            try:
                customer = self.__system.register_customer(
                    name, phone, email, "SMS" if channel == "S" else
                    "Email")
            except DmsError as error:
                self.__io.error(str(error))
                if not self.__io.yes_no("Try again?"):
                    return None
                continue
            self.__io.ok(f"Registered as customer {customer.customer_id}.")
            return customer

    def __home(self, customer) -> None:
        while True:
            waiting = len(self.__system.quotes_awaiting(customer))
            self.__io.header("Customer portal",
                             f"{customer.customer_id} {customer.contact.name}")
            choice = self.__io.menu([
                ("1", "Log a new delivery request"),
                ("2", f"Quotes awaiting my response ({waiting})"),
                ("3", "My requests and deliveries"),
                ("0", "Log out")])
            if choice == "0":
                self.__io.ok("Logged out.")
                return
            if choice == "1":
                RequestForm(self.__io, self.__system, customer,
                            customer.customer_id).run()
            elif choice == "2":
                self.__answer_quotes(customer)
            else:
                self.__my_requests(customer)

    def __answer_quotes(self, customer) -> None:
        requests = self.__system.quotes_awaiting(customer)
        self.__io.section("Quotes awaiting your response")
        rows = [[r.request_id, f"${r.current_quote.amount:.2f}",
                 r.dropoff.suburb,
                 f"{r.current_quote.expires_at:%a %d %b %H:%M}"]
                for r in requests]
        self.__io.table(["Request", "Price", "To", "Expires"], rows)
        if not requests:
            return
        ids = [r.request_id for r in requests]
        chosen = self.__io.choose("Request to answer (or 0 to go back)",
                                  ids + ["0"])
        if chosen != "0":
            request = next(r for r in requests if r.request_id == chosen)
            QuoteScreen(self.__io, self.__system, customer).show(request)

    def __my_requests(self, customer) -> None:
        self.__io.section("My requests and deliveries")
        rows = []
        for request in self.__system.requests_of(customer):
            delivery = request.delivery
            rows.append([
                request.request_id, f"{request.created_at:%d/%m %H:%M}",
                request.dropoff.suburb, request.status.value,
                delivery.tracking_ref if delivery else "-",
                delivery.status.value if delivery else "-"])
        self.__io.table(["Request", "Logged", "To", "Request status",
                         "Tracking", "Delivery status"], rows)
        self.__io.pause()
