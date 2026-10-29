"""The delivery request form (Task 1) and quote screen (Tasks 2-3).

Used by the customer portal and by office staff logging a walk-in or
phone request, so both create the same kind of record (SRS P1).
"""

from yowd.domain.errors import DmsError
from yowd.ui.console import Console


class RequestForm:
    """Collects, reviews and submits one delivery request."""

    def __init__(self, console: Console, system, customer,
                 actor_id: str) -> None:
        self.__io = console
        self.__system = system
        self.__customer = customer
        self.__actor_id = actor_id
        self.__pickup = None
        self.__dropoff = None
        self.__recipient = None
        self.__parcels: list = []
        self.__preferred = None
        self.__categories_shown = False

    # ============================================================ flow
    def run(self) -> None:
        """Fill in every part, then review until submit or discard."""
        self.__io.header("New delivery request",
                         f"Customer {self.__customer.customer_id} "
                         f"{self.__customer.contact.name}")
        self.__io.info("Fields marked * are required. Each value is checked "
                       "as you enter it.")
        self.__pickup = self.__address("Pickup address", saved=True)
        self.__dropoff = self.__address("Drop-off address", saved=False)
        self.__recipient = self.__ask_recipient()
        self.__io.section("Parcels")
        self.__parcels.append(self.__parcel(1))
        while len(self.__parcels) < 10 and \
                self.__io.yes_no("Add another parcel?"):
            self.__parcels.append(self.__parcel(len(self.__parcels) + 1))
        self.__preferred = self.__io.ask(
            "Preferred pickup date", self.__system.parse_preferred_date,
            "DD/MM/YYYY, Enter = today")
        self.__review()

    def __review(self) -> None:
        """Show the summary and apply changes until submit or discard."""
        changes = {"A": self.__add_parcel, "E": self.__edit_parcel,
                   "R": self.__remove_parcel, "P": self.__change_pickup,
                   "D": self.__change_dropoff, "N": self.__change_recipient}
        while True:
            self.__show_summary()
            choice = self.__io.menu([
                ("A", "Add a parcel"), ("E", "Edit a parcel"),
                ("R", "Remove a parcel"), ("P", "Change pickup address"),
                ("D", "Change drop-off address"),
                ("N", "Change recipient"), ("S", "Submit for a quote"),
                ("X", "Discard this request")])
            if choice in changes:
                changes[choice]()
            elif choice == "X":
                if self.__io.yes_no("Discard this request? Nothing will be "
                                    "saved."):
                    self.__io.ok("Request discarded.")
                    return
            elif self.__submit():
                return

    def __add_parcel(self) -> None:
        self.__parcels.append(self.__parcel(len(self.__parcels) + 1))

    def __edit_parcel(self) -> None:
        if not self.__parcels:
            self.__io.error("There are no parcels to edit.")
            return
        number = self.__parcel_number()
        self.__parcels[number - 1] = self.__parcel(number)
        self.__io.ok(f"Parcel {number} updated.")

    def __change_pickup(self) -> None:
        self.__pickup = self.__address("Pickup address", saved=True)

    def __change_dropoff(self) -> None:
        self.__dropoff = self.__address("Drop-off address", saved=False)

    def __change_recipient(self) -> None:
        self.__recipient = self.__ask_recipient()

    def __submit(self) -> bool:
        if not self.__parcels:
            self.__io.error("Add at least one parcel before submitting.")
            return False
        try:
            request = self.__system.submit_request(
                self.__customer, self.__pickup, self.__dropoff,
                self.__recipient, self.__parcels, self.__preferred,
                self.__actor_id)
        except DmsError as error:
            self.__io.error(str(error))
            return False
        self.__io.ok(f"Request {request.request_id} saved with status "
                     f"'{request.status.value}'.")
        if request.flags:
            self.__io.section("Needs office review")
            for flag in request.flags:
                self.__io.error(flag)
            self.__io.info("Office staff will check the address and send a "
                           "quote. No price is shown yet.")
            self.__io.notices(self.__system.recent_notifications())
            return True
        self.__io.notices(self.__system.recent_notifications())
        QuoteScreen(self.__io, self.__system, self.__customer).show(request)
        return True

    # ============================================================ parts
    def __address(self, title: str, saved: bool):
        self.__io.section(title)
        addresses = self.__customer.saved_addresses if saved else []
        if addresses:
            for number, address in enumerate(addresses, start=1):
                self.__io.info(f"S{number}  {address.formatted()}")
            keys = [f"S{n}" for n in range(1, len(addresses) + 1)]
            choice = self.__io.choose("Use a saved address or N for new",
                                      keys + ["N"])
            if choice != "N":
                return addresses[int(choice[1:]) - 1]
        while True:
            street = self.__io.text("* Street (number and name)")
            suburb = self.__io.text("* Suburb")
            postcode = self.__io.text("* Postcode", hint="4 digits")
            notes = self.__io.text("Delivery instructions", required=False,
                                   hint="optional")
            try:
                return self.__system.make_address(street, suburb, postcode,
                                                  notes)
            except DmsError as error:
                self.__io.error(str(error) + " Please re-enter the address.")

    def __ask_recipient(self):
        self.__io.section("Recipient (receives the parcels)")
        saved = self.__customer.saved_recipients
        if saved:
            for number, person in enumerate(saved, start=1):
                self.__io.info(f"S{number}  {person.contact.name} "
                               f"{person.contact.phone}")
            keys = [f"S{n}" for n in range(1, len(saved) + 1)]
            choice = self.__io.choose("Use a saved recipient or N for new",
                                      keys + ["N"])
            if choice != "N":
                original = saved[int(choice[1:]) - 1]
                return self.__system.make_recipient(
                    original.contact.name, original.contact.phone,
                    original.contact.email)
        while True:
            name = self.__io.text("* Recipient name")
            phone = self.__io.text("* Recipient mobile", hint="04xx xxx xxx")
            email = self.__io.text("Recipient email", required=False,
                                   hint="optional")
            try:
                return self.__system.make_recipient(name, phone, email)
            except DmsError as error:
                self.__io.error(str(error))

    def __parcel(self, number: int):
        allowed, refused = self.__system.parcel_categories()
        self.__io.info(f"Parcel {number}")
        if not self.__categories_shown:
            self.__io.info("Categories:")
            for index, name in enumerate(allowed + refused, start=1):
                note = "  (not carried by YOWD)" if name in refused else ""
                self.__io.info(f"  {index}. {name}{note}")
            self.__categories_shown = True
        while True:
            description = self.__io.text("* Description",
                                         hint="e.g. Box of books")
            pick = self.__io.choose("* Category number",
                                    [str(n) for n in
                                     range(1, len(allowed + refused) + 1)])
            category = (allowed + refused)[int(pick) - 1]
            length = self.__io.text("* Length (cm)")
            width = self.__io.text("* Width (cm)")
            height = self.__io.text("* Height (cm)")
            weight = self.__io.text("* Weight (kg)")
            try:
                parcel = self.__system.make_parcel(description, category,
                                                   length, width, height,
                                                   weight)
                self.__io.ok(f"Parcel {number} accepted: {parcel.summary()}")
                return parcel
            except DmsError as error:
                self.__io.error(str(error))
                self.__io.info(f"Please re-enter parcel {number}.")

    def __parcel_number(self) -> int:
        def check(raw: str) -> int:
            number = int(raw) if raw.strip().isdigit() else 0
            if 1 <= number <= len(self.__parcels):
                return number
            raise _Choice(f"Enter a parcel number from 1 to "
                          f"{len(self.__parcels)}.")
        return self.__io.ask("Parcel number", check)

    def __remove_parcel(self) -> None:
        if not self.__parcels:
            self.__io.error("There are no parcels to remove.")
            return
        number = self.__parcel_number()
        removed = self.__parcels.pop(number - 1)
        self.__io.ok(f"Removed parcel {number}: {removed.description}.")

    def __show_summary(self) -> None:
        self.__io.section("Review your request")
        self.__io.info(f"Pickup:     {self.__pickup.formatted()}")
        self.__io.info(f"Drop-off:   {self.__dropoff.formatted()}")
        self.__io.info(f"Recipient:  {self.__recipient.contact.name} "
                       f"{self.__recipient.contact.phone}")
        self.__io.info(f"Pickup day: {self.__preferred:%a %d %b %Y}")
        rows = [[str(n), p.description, p.category,
                 f"{p.length_cm:g}x{p.width_cm:g}x{p.height_cm:g}",
                 f"{p.weight_kg:g}", p.size_category]
                for n, p in enumerate(self.__parcels, start=1)]
        self.__io.table(["#", "Description", "Category", "Size cm", "kg",
                         "Band"], rows)
        self.__io.say()


class QuoteScreen:
    """Shows a quote and records the customer's answer (Task 3)."""

    def __init__(self, console: Console, system, customer) -> None:
        self.__io = console
        self.__system = system
        self.__customer = customer

    def show(self, request) -> None:
        """Display the quote, terms, and ask accept / decline / later."""
        quote = request.current_quote
        self.__io.section(f"Quote {quote.quote_id} for request "
                          f"{request.request_id}")
        for label, amount in quote.breakdown:
            self.__io.info(f"{label:<46}${amount:>8.2f}")
        if quote.overridden_by:
            self.__io.info(f"Price set by office staff: "
                           f"{quote.override_reason}")
        self.__io.info("-" * 56)
        self.__io.info(f"{'TOTAL (incl. GST)':<46}${quote.amount:>8.2f}")
        self.__io.info(f"Estimated pickup:   {quote.pickup_window.label()}")
        self.__io.info(f"Estimated delivery: {quote.delivery_window.label()}")
        self.__io.info(f"Quote valid until:  "
                       f"{quote.expires_at:%a %d %b %Y %H:%M}")
        self.__io.info("Terms: payment is taken at pickup by card or cash. "
                       "Your details are")
        self.__io.info("used only to deliver this order (Privacy Act 1988).")
        choice = self.__io.choose("Accept (A), Decline (D) or decide Later "
                                  "(L)", ["A", "D", "L"])
        if choice == "L":
            self.__io.ok("The quote is saved under 'Quotes awaiting my "
                         "response'.")
            return
        try:
            delivery = self.__system.respond_to_quote(
                self.__customer, request.request_id, choice == "A")
        except DmsError as error:
            self.__io.error(str(error))
            return
        if delivery is None:
            self.__io.ok(f"Quote declined. Request {request.request_id} is "
                         "now Rejected.")
            return
        self.__io.ok(f"Quote accepted. Tracking reference: "
                     f"{delivery.tracking_ref}")
        self.__io.info(f"Handover PIN for your recipient: "
                       f"{request.recipient.handover_pin}  (share it with "
                       f"{request.recipient.contact.name})")
        self.__io.info(f"Status: {delivery.status.value} - waiting for a "
                       "driver to be allocated.")
        self.__io.notices(self.__system.recent_notifications())


class _Choice(DmsError):
    """Internal: invalid parcel number."""
