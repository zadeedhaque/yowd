"""Office staff and owner screens (Tasks 1b/1c, 2.3, 5, 9, 10)."""

from yowd.domain.errors import DmsError
from yowd.ui.console import Console
from yowd.ui.request_form import RequestForm
from yowd.ui.tracking_screen import TrackingScreen

_PERIODS = {"1": "day", "2": "week", "3": "month", "4": "year", "5": "ytd"}


class OfficePortal:
    """Dispatch view for office staff; owner tools for owners."""

    def __init__(self, console: Console, system) -> None:
        self.__io = console
        self.__system = system
        self.__officer = None

    def run(self) -> None:
        """Sign in with a staff id, then show the dispatch menu."""
        self.__io.header("Office staff portal", "Sign in")
        staff_id = self.__io.text("* Staff ID", hint="e.g. S002")
        try:
            self.__officer = self.__system.login_office(staff_id)
        except DmsError as error:
            self.__io.error(str(error))
            return
        self.__io.ok(f"Signed in as {self.__officer.contact.name} "
                     f"({self.__officer.role.value}).")
        self.__home()

    def __home(self) -> None:
        actions = {"1": self.__review, "2": self.__walk_in,
                   "3": self.__allocate, "4": self.__override,
                   "5": self.__reconcile,
                   "6": lambda: TrackingScreen(self.__io, self.__system).run(
                       staff_view=True),
                   "7": self.__statistics, "8": self.__manage_staff}
        while True:
            review = len(self.__system.requests_for_review(self.__officer))
            waiting = len(self.__system.unallocated(self.__officer))
            self.__io.header("Office staff portal",
                             f"{self.__officer.staff_id} "
                             f"{self.__officer.contact.name}")
            self.__io.notices(self.__system.recent_notifications())
            items = [("1", f"Requests needing review ({review})"),
                     ("2", "Log a request for a walk-in/phone customer"),
                     ("3", f"Allocate deliveries ({waiting} waiting)"),
                     ("4", "Change the price of an open quote"),
                     ("5", "Reconcile a driver's cash"),
                     ("6", "Track a delivery (full history)")]
            if self.__officer.is_owner:
                items += [("7", "Owner: delivery statistics"),
                          ("8", "Owner: manage delivery staff")]
            items.append(("0", "Log out"))
            choice = self.__io.menu(items)
            if choice == "0":
                self.__io.ok("Logged out.")
                return
            actions[choice]()

    # --------------------------------------------------------- requests
    def __review(self) -> None:
        requests = self.__system.requests_for_review(self.__officer)
        self.__io.section("Requests needing review")
        self.__io.table(["Request", "Customer", "Problem"],
                        [[r.request_id, r.customer.contact.name,
                          "; ".join(r.flags)] for r in requests])
        if not requests:
            return
        ids = [r.request_id for r in requests]
        chosen = self.__io.choose("Request (or 0 to go back)", ids + ["0"])
        if chosen == "0":
            return
        action = self.__io.choose("Quote a manual price (Q) or reject (R)",
                                  ["Q", "R"])
        try:
            if action == "Q":
                amount = self.__io.ask("* Price incl. GST",
                                       self.__system.parser.money,
                                       "e.g. 85")
                reason = self.__io.text("* Reason")
                request = self.__system.manual_quote(self.__officer, chosen,
                                                     str(amount), reason)
                self.__io.ok(f"Quote {request.current_quote.quote_id} sent "
                             f"for ${request.current_quote.amount:.2f}.")
            else:
                reason = self.__io.text("* Reason the customer will see")
                self.__system.reject_request(self.__officer, chosen, reason)
                self.__io.ok(f"{chosen} cancelled.")
        except DmsError as error:
            self.__io.error(str(error))
        self.__io.notices(self.__system.recent_notifications())

    def __walk_in(self) -> None:
        self.__io.section("Walk-in or phone customer")
        key = self.__io.text("* Customer mobile or email")
        customer = self.__system.lookup_customer(key)
        if customer is None:
            self.__io.info("Not found - creating a guest customer (no "
                           "login).")
            while True:
                try:
                    name = self.__io.text("* Customer name")
                    phone = self.__io.text("* Mobile number")
                    customer = self.__system.register_customer(
                        name, phone, "", "SMS", has_login=False)
                    break
                except DmsError as error:
                    self.__io.error(str(error))
        RequestForm(self.__io, self.__system, customer,
                    self.__officer.staff_id).run()

    def __override(self) -> None:
        ref = self.__io.text("* Request number", hint="e.g. R0012")
        amount = str(self.__io.ask("* New price incl. GST",
                                   self.__system.parser.money))
        reason = self.__io.text("* Reason for the change")
        try:
            request = self.__system.override_quote(self.__officer, ref, amount,
                                                   reason)
            self.__io.ok(f"Quote now ${request.current_quote.amount:.2f}.")
        except DmsError as error:
            self.__io.error(str(error))
        self.__io.notices(self.__system.recent_notifications())

    # ------------------------------------------------------- allocation
    def __allocate(self) -> None:
        self.__io.section("Deliveries waiting for a driver (pickup order)")
        waiting = self.__system.unallocated(self.__officer)
        self.__io.notices(self.__system.recent_notifications())
        self.__io.table(
            ["Tracking", "Pickup window", "From", "To", "Note"],
            [[d.tracking_ref, d.quote.pickup_window.label(),
              d.request.pickup.suburb, d.request.dropoff.suburb,
              self.__note(d, urgent)] for d, urgent in waiting])
        if not waiting:
            self.__io.pause()
            return
        refs = [d.tracking_ref for d, _ in waiting]
        ref = self.__io.choose("Delivery to allocate (or 0 to go back)",
                               refs + ["0"])
        if ref == "0":
            return
        staff = self.__system.candidates_for(self.__officer, ref)
        self.__io.section(f"Drivers free for {ref}")
        self.__io.table(["Staff", "Name", "Phone"],
                        [[s.staff_id, s.contact.name, s.contact.phone]
                         for s in staff])
        if not staff:
            self.__io.error("No driver is free for this window. Ask a driver "
                            "to extend their availability, or contact the "
                            "customer to move the pickup.")
            self.__io.pause()
            return
        chosen = self.__io.choose("Allocate to staff ID (or 0 to cancel)",
                                  [s.staff_id for s in staff] + ["0"])
        if chosen == "0":
            self.__io.info("Nothing allocated.")
            return
        try:
            allocation = self.__system.allocate(self.__officer, ref, chosen)
            self.__io.ok(f"{ref} allocated to {allocation.staff.contact.name}"
                         f" ({allocation.allocation_id}); waiting for "
                         "acknowledgement.")
        except DmsError as error:
            self.__io.error(str(error))
        self.__io.notices(self.__system.recent_notifications())
        self.__io.pause()

    @staticmethod
    def __note(delivery, urgent: bool) -> str:
        """Urgency flag and why a delivery came back (Task 5a, 5e)."""
        parts = ["URGENT"] if urgent else []
        if delivery.allocations:
            parts.append("Reallocate: " + delivery.allocations[-1].reason)
        return "; ".join(parts)

    def __reconcile(self) -> None:
        staff_id = self.__io.text("* Driver staff ID", hint="e.g. D001")
        try:
            payments = self.__system.reconcile_cash(self.__officer, staff_id)
        except DmsError as error:
            self.__io.error(str(error))
            return
        total = sum(p.amount for p in payments)
        self.__io.ok(f"Reconciled {len(payments)} cash payment(s), total "
                     f"${total:.2f}.")

    # ------------------------------------------------------------ owner
    def __statistics(self) -> None:
        self.__io.section("Delivery statistics")
        self.__io.info("Period: 1 Day  2 Week  3 Month  4 Year  5 Year to "
                       "date")
        kind = _PERIODS[self.__io.choose("* Period", list(_PERIODS))]
        reference = self.__io.ask(
            "Any date inside the period", self.__check_date,
            "DD/MM/YYYY, Enter = today")
        staff_id = self.__io.text("Delivery staff ID", required=False,
                                  hint="Enter = all deliveries")
        try:
            report = self.__system.statistics(self.__officer, kind, reference,
                                              staff_id)
        except DmsError as error:
            self.__io.error(str(error))
            return
        self.__io.section("Report")
        for label, value in report.rows():
            self.__io.info(f"{label:<34}{value}")
        if self.__io.yes_no("Export to a CSV file for a spreadsheet?"):
            name = self.__system.export_statistics(report)
            self.__io.ok(f"Saved {name} in the exports folder.")

    def __check_date(self, raw: str) -> str:
        """Validate the report date as it is typed."""
        self.__system.parse_report_date(raw)
        return raw

    def __add_driver(self) -> None:
        """Ask for a new driver's details until they are valid."""
        while True:
            try:
                staff = self.__system.add_driver(
                    self.__officer, self.__io.text("* Name"),
                    self.__io.text("* Mobile", hint="04xx xxx xxx"),
                    self.__io.text("Email", required=False, hint="optional"))
            except DmsError as error:
                self.__io.error(str(error) + " Please re-enter.")
                continue
            self.__io.ok(f"Added {staff.staff_id} {staff.contact.name}. "
                         "They can now declare availability.")
            return

    def __manage_staff(self) -> None:
        try:
            overview = self.__system.staff_overview(self.__officer)
        except DmsError as error:
            self.__io.error(str(error))
            return
        self.__io.section("Delivery staff")
        self.__io.table(["Staff", "Name", "Phone", "Active", "Open jobs"],
                        [[s.staff_id, s.contact.name, s.contact.phone,
                          "yes" if s.active else "no", str(jobs)]
                         for s, jobs in overview])
        choice = self.__io.choose("Add (A), remove (R) or back (0)",
                                  ["A", "R", "0"])
        try:
            if choice == "A":
                self.__add_driver()
            elif choice == "R":
                staff_id = self.__io.text("* Staff ID to mark inactive")
                released = self.__system.deactivate_driver(self.__officer,
                                                           staff_id)
                self.__io.ok(f"{staff_id.upper()} is inactive; history kept. "
                             f"{len(released)} job(s) returned for "
                             "reallocation.")
        except DmsError as error:
            self.__io.error(str(error))
        self.__io.notices(self.__system.recent_notifications())
