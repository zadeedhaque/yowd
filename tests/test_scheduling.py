"""Business area 2: availability and allocation (T4, T5, T10)."""

import unittest

from tests.support import SystemTestCase
from yowd.domain.errors import BusinessRuleError, ValidationError
from yowd.domain.statuses import AllocationStatus, DeliveryStatus


class SchedulingTest(SystemTestCase):
    """Dispatcher, Allocation and DeliveryStaff availability."""

    def _allocate(self):
        delivery = self.accepted_delivery()
        staff = self.system.candidates_for(self.officer,
                                           delivery.tracking_ref)[0]
        allocation = self.system.allocate(self.officer,
                                          delivery.tracking_ref,
                                          staff.staff_id)
        return delivery, staff, allocation

    def test_unallocated_listed_in_pickup_order(self) -> None:
        self.accepted_delivery()
        waiting = self.system.unallocated(self.officer)
        starts = [d.quote.pickup_window.start for d, _ in waiting]
        self.assertEqual(starts, sorted(starts))

    def test_allocate_moves_to_scheduled(self) -> None:
        delivery, staff, allocation = self._allocate()
        self.assertIs(delivery.status, DeliveryStatus.SCHEDULED)
        self.assertIs(allocation.status, AllocationStatus.OFFERED)
        self.assertTrue(delivery.is_allocated_to(staff.staff_id))

    def test_unavailable_driver_refused(self) -> None:
        delivery = self.accepted_delivery()
        free = {s.staff_id for s in self.system.candidates_for(
            self.officer, delivery.tracking_ref)}
        busy = next(s.staff_id for s, _ in
                    self.system.staff_overview(self.owner)
                    if s.staff_id not in free and s.active)
        with self.assertRaises(BusinessRuleError):
            self.system.allocate(self.officer, delivery.tracking_ref, busy)

    def test_unacknowledged_allocation_is_revoked(self) -> None:
        delivery, _, allocation = self._allocate()
        self.clock.advance(minutes=16)
        self.system.unallocated(self.officer)
        self.assertIs(allocation.status, AllocationStatus.REVOKED)
        self.assertIs(delivery.status, DeliveryStatus.ACCEPTED)
        self.assertEqual(len(delivery.allocations), 1)  # history kept

    def test_withdrawal_returns_job_for_reallocation(self) -> None:
        delivery, staff, allocation = self._allocate()
        self.system.acknowledge(staff, delivery.tracking_ref)
        period = next(p for p in staff.availability
                      if p.covers(allocation.window))
        self.system.withdraw_availability(staff, period.period_id)
        self.assertIs(allocation.status, AllocationStatus.REVOKED)
        self.assertIs(delivery.status, DeliveryStatus.ACCEPTED)
        alerts = self.system.recent_notifications()
        self.assertTrue(any("needs a new driver" in a for a in alerts))

    def test_declare_and_overlap(self) -> None:
        staff = self.system.login_driver("D002")
        period = self.system.declare_availability(staff, "02/11/2026",
                                                  "08:00", "12:00", False)
        self.assertIn(period, staff.availability)
        with self.assertRaisesRegex(BusinessRuleError, "overlaps"):
            self.system.declare_availability(staff, "02/11/2026", "11:00",
                                             "13:00", False)
        with self.assertRaises(ValidationError):
            self.system.declare_availability(staff, "02/11/2026", "13:00",
                                             "12:00", False)

    def test_deactivated_driver_releases_jobs(self) -> None:
        delivery, staff, _ = self._allocate()
        released = self.system.deactivate_driver(self.owner,
                                                 staff.staff_id)
        self.assertEqual(len(released), 1)
        self.assertIs(delivery.status, DeliveryStatus.ACCEPTED)
        self.assertFalse(staff.active)

    def test_only_owner_manages_staff(self) -> None:
        with self.assertRaises(Exception):
            self.system.add_driver(self.officer, "New Person",
                                   "0499888777", "")


if __name__ == "__main__":
    unittest.main()
