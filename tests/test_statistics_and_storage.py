"""Business area 5 (statistics, T9) and persistence."""

import unittest

from tests.support import SystemTestCase
from yowd.app.system import DeliveryManagementSystem
from yowd.domain.errors import AuthorisationError, ValidationError


class StatisticsTest(SystemTestCase):
    """StatisticsCalculator over the seeded history."""

    def test_month_report_counts_seeded_deliveries(self) -> None:
        report = self.system.statistics(self.owner, "month", "")
        self.assertGreaterEqual(report.total_deliveries, 8)
        self.assertGreaterEqual(report.delivered, 6)
        self.assertNotEqual(report.on_time_rate, "n/a")

    def test_per_driver_scope(self) -> None:
        overall = self.system.statistics(self.owner, "year", "")
        driver = self.system.statistics(self.owner, "year", "", "D001")
        self.assertLess(driver.total_deliveries, overall.total_deliveries)
        self.assertIn("D001", driver.scope)

    def test_office_staff_cannot_see_statistics(self) -> None:
        with self.assertRaises(AuthorisationError):
            self.system.statistics(self.officer, "week", "")

    def test_bad_period_refused(self) -> None:
        with self.assertRaises(ValidationError):
            self.system.statistics(self.owner, "fortnight", "")

    def test_csv_export(self) -> None:
        report = self.system.statistics(self.owner, "ytd", "")
        name = self.system.export_statistics(report)
        exported = self.workspace.export(name)
        self.assertTrue(exported.exists())
        self.assertIn("Measure,Value", exported.read())


class PersistenceTest(SystemTestCase):
    """Everything survives a restart (JsonDataStore round trip)."""

    def test_restart_keeps_records(self) -> None:
        delivery = self.accepted_delivery()
        ref, pin = (delivery.tracking_ref,
                    delivery.request.recipient.handover_pin)
        again = DeliveryManagementSystem(self.workspace, self.clock)
        restored = again.track(ref)
        self.assertEqual(restored.status, delivery.status)
        self.assertEqual(restored.request.recipient.handover_pin, pin)
        self.assertEqual(len(restored.events), len(delivery.events))
        self.assertEqual(again.track(ref).quote.amount,
                         delivery.quote.amount)


if __name__ == "__main__":
    unittest.main()
