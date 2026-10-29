"""Shared fixtures: a whole system in memory with a fixed clock.

Because every collaborator is injected, a test builds the real system
on a MemoryWorkspace (no files) with a FixedClock (no real time), so
tests are fast, isolated and repeatable.
"""

import unittest
from datetime import datetime
from pathlib import Path

from yowd.app.system import DeliveryManagementSystem
from yowd.app.workspace import MemoryWorkspace
from yowd.domain.clock import MELBOURNE, FixedClock

ROOT = Path(__file__).resolve().parent.parent
# Thursday 29 October 2026, 09:00 Melbourne time.
START = datetime(2026, 10, 29, 9, 0, tzinfo=MELBOURNE)


class SystemTestCase(unittest.TestCase):
    """Creates a fresh, seeded system for every test."""

    def setUp(self) -> None:
        config = (ROOT / "data" / "config.json").read_text(encoding="utf-8")
        self.workspace = MemoryWorkspace(config)
        self.clock = FixedClock(START)
        self.system = DeliveryManagementSystem(self.workspace, self.clock)
        self.owner = self.system.login_office("S001")
        self.officer = self.system.login_office("S002")
        self.customer = self.system.find_customer("sarah.chen@example.com")

    def new_request(self, kg: str = "4", category: str = "General goods",
                    drop=("15 Nicholson Street", "Footscray", "3011")):
        """Submit a Richmond -> (drop) request with one parcel."""
        system = self.system
        pickup = system.make_address("88 Swan Street", "Richmond", "3121")
        dropoff = system.make_address(*drop)
        recipient = system.make_recipient("Jo Lee", "0412345678")
        parcel = system.make_parcel("Books", category, "40", "30", "20", kg)
        return system.submit_request(self.customer, pickup, dropoff,
                                     recipient, [parcel], START.date(),
                                     self.customer.customer_id)

    def accepted_delivery(self):
        """A request that has been quoted and accepted."""
        request = self.new_request()
        return self.system.respond_to_quote(self.customer,
                                            request.request_id, True)
