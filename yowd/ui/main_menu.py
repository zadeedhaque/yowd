"""Home screen: chooses the portal for each kind of user."""

from yowd.ui.console import Console, EndOfInput
from yowd.ui.customer_screens import CustomerPortal
from yowd.ui.driver_screens import DriverPortal
from yowd.ui.office_screens import OfficePortal
from yowd.ui.tracking_screen import TrackingScreen


class MainMenu:
    """First screen shown after the system has started."""

    def __init__(self, console: Console, system) -> None:
        self.__io = console
        self.__system = system

    def run(self) -> None:
        """Loop until the user chooses Exit (or input ends)."""
        try:
            while True:
                now = self.__system.now()
                self.__io.header("YOWD Delivery Management System",
                                 f"{now:%a %d %b %Y %H:%M}")
                self.__io.info(self.__system.heading())
                self.__io.say()
                choice = self.__io.menu([
                    ("1", "Customer portal (requests, quotes, deliveries)"),
                    ("2", "Office staff portal (review, allocate, owner)"),
                    ("3", "Delivery staff portal (availability, jobs)"),
                    ("4", "Track a delivery (recipients and customers)"),
                    ("0", "Exit")])
                if choice == "0":
                    break
                screen = {"1": CustomerPortal, "2": OfficePortal,
                          "3": DriverPortal, "4": TrackingScreen}[choice]
                screen(self.__io, self.__system).run()
        except (EndOfInput, KeyboardInterrupt):
            self.__io.say()
        self.__system.save()
        self.__io.say("  All records saved. Goodbye.")
