"""Driver portal (Tasks 4, 5.4, 6 and 7), usable without signal (QR3).

Online, a FieldAction is executed straight away so the driver gets an
immediate answer (QP3).  Offline, it is stored in the OfflineSyncQueue
on the device and uploaded later in the order it happened.
"""

from yowd.domain.errors import DmsError
from yowd.domain.field_action import FieldAction
from yowd.domain.statuses import (AllocationStatus, DeliveryStatus,
                                  FieldActionKind, PaymentMethod)
from yowd.ui.console import Console

_FAIL_REASONS = ["Nobody at the address", "Address could not be found",
                 "Recipient refused the parcels", "Access blocked"]


class DriverPortal:
    """Mobile-style menu for delivery staff."""

    def __init__(self, console: Console, system) -> None:
        self.__io = console
        self.__system = system
        self.__staff = None
        self.__queue = None

    def run(self) -> None:
        """Sign in, then show the driver home screen."""
        self.__io.header("Delivery staff portal", "Sign in")
        staff_id = self.__io.text("* Staff ID", hint="e.g. D001")
        try:
            self.__staff = self.__system.login_driver(staff_id)
        except DmsError as error:
            self.__io.error(str(error))
            return
        self.__queue = self.__system.device_queue(self.__staff)
        self.__io.ok(f"Signed in as {self.__staff.contact.name}.")
        self.__home()

    def __status_line(self) -> str:
        state = "ONLINE" if self.__queue.online else "OFFLINE (no signal)"
        return f"{state} | waiting to upload: {len(self.__queue.pending)}"

    def __home(self) -> None:
        while True:
            jobs = self.__system.jobs_of(self.__staff)
            self.__io.header(f"Driver {self.__staff.staff_id} "
                             f"{self.__staff.contact.name}",
                             self.__status_line())
            toggle = "Go offline (simulate no signal)" if \
                self.__queue.online else "Go online (signal is back)"
            choice = self.__io.menu([
                ("1", "My availability"),
                ("2", f"My jobs ({len(jobs)})"),
                ("3", "Record work on a job"),
                ("4", toggle),
                ("5", f"Upload waiting actions ({len(self.__queue.pending)})"),
                ("0", "Log out")])
            if choice == "0":
                self.__io.ok("Logged out.")
                return
            {"1": self.__availability, "2": self.__jobs, "3": self.__work,
             "4": self.__toggle, "5": self.__sync}[choice]()

    # ------------------------------------------------------ availability
    def __availability(self) -> None:
        while True:
            self.__io.section("My availability")
            now = self.__system.now()
            self.__io.table(["Id", "Period"],
                            [[p.period_id, p.label()]
                             for p in self.__staff.availability
                             if p.is_current(now)])
            choice = self.__io.choose(
                "Declare (D), Change (C), Withdraw (W) or back (0)",
                ["D", "C", "W", "0"])
            if choice == "0":
                return
            try:
                if choice == "D":
                    day, start, end = self.__window_fields()
                    weekly = self.__io.yes_no("Repeat every week?")
                    period = self.__system.declare_availability(
                        self.__staff, day, start, end, weekly)
                    self.__io.ok(f"Saved {period.period_id}: "
                                 f"{period.label()}. Visible to the office "
                                 "now.")
                elif choice == "C":
                    period_id = self.__io.text("* Period id to change")
                    day, start, end = self.__window_fields()
                    period = self.__system.change_availability(
                        self.__staff, period_id, day, start, end)
                    self.__io.ok(f"Changed to {period.label()}.")
                else:
                    period_id = self.__io.text("* Period id to withdraw")
                    if self.__io.yes_no("Withdraw this period? Jobs inside "
                                        "it go back to the office"):
                        period = self.__system.withdraw_availability(
                            self.__staff, period_id)
                        self.__io.ok(f"Withdrawn {period.label()}.")
            except DmsError as error:
                self.__io.error(str(error))
            self.__io.notices(self.__system.recent_notifications())

    def __window_fields(self) -> tuple[str, str, str]:
        """Ask for a day and times until they form a valid window."""
        while True:
            day = self.__io.text("* Day", hint="DD/MM/YYYY")
            start = self.__io.text("* From", hint="HH:MM")
            end = self.__io.text("* Until", hint="HH:MM")
            try:
                self.__system.parse_window(day, start, end)
                return day, start, end
            except DmsError as error:
                self.__io.error(str(error) + " Please re-enter.")

    # -------------------------------------------------------------- jobs
    def __jobs(self) -> None:
        jobs = self.__system.jobs_of(self.__staff)
        self.__io.section("My jobs")
        self.__io.table(["Tracking", "Pickup window", "From", "To", "Status",
                         "Job"],
                        [[a.delivery.tracking_ref, a.window.label(),
                          a.delivery.request.pickup.suburb,
                          a.delivery.request.dropoff.suburb,
                          a.delivery.status.value, a.status.value]
                         for a in jobs])
        offered = [a.delivery.tracking_ref for a in jobs
                   if a.status is AllocationStatus.OFFERED]
        if not offered:
            self.__io.pause()
            return
        ref = self.__io.choose("Acknowledge which job (or 0 for none)",
                               offered + ["0"])
        if ref != "0":
            try:
                self.__system.acknowledge(self.__staff, ref)
                self.__io.ok(f"{ref} acknowledged. The office can see you "
                             "accepted it.")
            except DmsError as error:
                self.__io.error(str(error))

    # ------------------------------------------------------- field work
    def __work(self) -> None:
        jobs = [a for a in self.__system.jobs_of(self.__staff)
                if a.status is AllocationStatus.ACKNOWLEDGED]
        if not jobs:
            self.__io.error("You have no acknowledged jobs. Acknowledge a job "
                            "under 'My jobs' first.")
            return
        refs = [a.delivery.tracking_ref for a in jobs]
        ref = self.__io.choose("Job tracking reference", refs)
        delivery = next(a.delivery for a in jobs
                        if a.delivery.tracking_ref == ref)
        self.__job_card(delivery)
        choice = self.__io.menu([
            ("1", "Arrived at pickup"),
            ("2", "Collect parcels and payment"),
            ("3", "Leave for drop-off (In Transit)"),
            ("4", "Complete delivery (proof of delivery)"),
            ("5", "Record a failed attempt"),
            ("0", "Back")])
        if choice == "0":
            return
        builder = {"1": self.__arrived, "2": self.__collect,
                   "3": self.__depart, "4": self.__deliver,
                   "5": self.__failed}[choice]
        action = builder(delivery)
        if action is not None:
            self.__submit(action)

    def __job_card(self, delivery) -> None:
        request = delivery.request
        self.__io.section(f"Job {delivery.tracking_ref} - "
                          f"{delivery.status.value}")
        self.__io.info(f"Pickup:   {request.pickup.formatted()}")
        if request.pickup.instructions:
            self.__io.info(f"          ({request.pickup.instructions})")
        self.__io.info(f"Customer: {request.customer.contact.name} "
                       f"{request.customer.contact.phone}")
        self.__io.info(f"Drop-off: {request.dropoff.formatted()}")
        self.__io.info(f"Recipient: {request.recipient.contact.name} "
                       f"{request.recipient.contact.phone}")
        for number, parcel in enumerate(request.parcels, start=1):
            self.__io.info(f"Parcel {number}: {parcel.summary()}")
        self.__io.info(f"Amount to collect: ${delivery.amount_owing:.2f}")

    def __new_action(self, kind, delivery, data=None) -> FieldAction:
        return self.__system.new_field_action(
            self.__staff, kind, delivery.tracking_ref, data,
            self.__queue.online)

    def __arrived(self, delivery):
        return self.__new_action(FieldActionKind.ARRIVED_PICKUP, delivery)

    def __collect(self, delivery):
        if delivery.status is not DeliveryStatus.SCHEDULED:
            self.__io.error(f"Pickup is already recorded "
                            f"({delivery.status.value}).")
            return None
        collected = 0
        for number, parcel in enumerate(delivery.request.parcels, start=1):
            if self.__io.yes_no(f"Parcel {number} '{parcel.description}' "
                                "collected?"):
                collected += 1
        expected = len(delivery.request.parcels)
        if collected != expected:
            self.__io.error(f"{collected} of {expected} parcels checked off. "
                            "Collect every parcel, or record a failed "
                            "attempt and call the office.")
            return None
        data = {"collected": collected}
        if delivery.amount_owing > 0:
            payment = self.__ask_payment(delivery.amount_owing)
            if payment is None:
                self.__io.info("Nothing recorded.")
                return None
            data.update(payment)
        return self.__new_action(FieldActionKind.PICKUP_AND_PAYMENT,
                                 delivery, data)

    def __ask_payment(self, amount) -> dict | None:
        """Choose card or cash; the driver can change their mind."""
        while True:
            method = self.__io.choose(f"Payment of ${amount:.2f}: Card (C) or "
                                      "Cash (H)", ["C", "H"])
            if method == "C" and not self.__queue.online:
                self.__io.error("Card payments need a connection. Take "
                                "cash, or wait until signal returns.")
                continue
            data = {"method": (PaymentMethod.CARD if method == "C"
                               else PaymentMethod.CASH).value}
            if method == "C":
                data["card_last_four"] = self.__io.text(
                    "* Last 4 digits shown on the card terminal")
            choice = self.__io.choose(
                f"Confirm {data['method']} ${amount:.2f} (Y), change "
                "payment method (M) or cancel (X)", ["Y", "M", "X"])
            if choice == "Y":
                return data
            if choice == "X":
                return None
            self.__io.info("Payment method cleared - choose again.")

    def __depart(self, delivery):
        return self.__new_action(FieldActionKind.DEPART, delivery)

    def __deliver(self, delivery):
        receiver = self.__io.text("* Name of the person taking the parcels")
        pin = self.__io.text("* Handover PIN given by the recipient")
        photo = self.__io.text("Photo file name", required=False,
                               hint="e.g. pod_1234.jpg")
        return self.__new_action(FieldActionKind.DELIVER, delivery,
                                 {"receiver_name": receiver, "pin": pin,
                                  "photo": photo})

    def __failed(self, delivery):
        for number, reason in enumerate(_FAIL_REASONS, start=1):
            self.__io.info(f"{number}. {reason}")
        pick = self.__io.choose("* Reason", [str(n) for n in
                                             range(1, len(_FAIL_REASONS) + 1)])
        return self.__new_action(FieldActionKind.FAILED_ATTEMPT, delivery,
                                 {"reason": _FAIL_REASONS[int(pick) - 1]})

    def __submit(self, action: FieldAction) -> None:
        if not self.__queue.online:
            self.__queue.enqueue(action)
            self.__io.ok(f"No signal: saved on this phone at "
                         f"{action.device_time:%H:%M:%S}. "
                         f"{len(self.__queue.pending)} action(s) waiting to "
                         "upload.")
            return
        try:
            self.__io.ok(self.__system.perform_field_action(action))
        except DmsError as error:
            self.__io.error(str(error))
        self.__io.notices(self.__system.recent_notifications())

    # ---------------------------------------------------- connectivity
    def __toggle(self) -> None:
        if self.__queue.online:
            self.__queue.go_offline()
        else:
            self.__queue.go_online()
        if self.__queue.online:
            self.__io.ok("Signal is back.")
            if self.__queue.pending:
                self.__sync()
        else:
            self.__io.ok("Offline mode: work is saved on the phone until "
                         "signal returns.")

    def __sync(self) -> None:
        if not self.__queue.online:
            self.__io.error("Still offline. Go online first.")
            return
        if not self.__queue.pending:
            self.__io.info("Nothing waiting to upload.")
            return
        self.__io.section("Uploading in the order the work happened")
        for action, message, ok in self.__queue.flush(
                self.__system.perform_field_action):
            line = f"{action.label()}: {message}"
            if ok:
                self.__io.ok(line)
            else:
                self.__io.error(line)
        self.__io.notices(self.__system.recent_notifications())
