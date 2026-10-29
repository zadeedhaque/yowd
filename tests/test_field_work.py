"""Business areas 3 and 4: pickup, payment, delivery and tracking."""

import unittest
from decimal import Decimal

from tests.support import SystemTestCase
from yowd.domain.errors import BusinessRuleError, ValidationError
from yowd.domain.field_action import FieldAction
from yowd.domain.statuses import (DeliveryStatus, FieldActionKind,
                                  PaymentStatus)


class FieldWorkTest(SystemTestCase):
    """FieldAction (Command), OfflineSyncQueue and Payment."""

    def setUp(self) -> None:
        super().setUp()
        delivery = self.accepted_delivery()
        staff = self.system.candidates_for(self.officer,
                                           delivery.tracking_ref)[0]
        self.system.allocate(self.officer, delivery.tracking_ref,
                             staff.staff_id)
        self.system.acknowledge(staff, delivery.tracking_ref)
        self.delivery, self.staff = delivery, staff

    def act(self, kind, data=None, online=True) -> FieldAction:
        """Build an action at the current clock time."""
        return self.system.new_field_action(
            self.staff, kind, self.delivery.tracking_ref, data, online)

    def test_cash_pickup_creates_payment_and_receipt(self) -> None:
        self.system.perform_field_action(self.act(
            FieldActionKind.PICKUP_AND_PAYMENT,
            {"collected": 1, "method": "Cash"}))
        self.assertIs(self.delivery.status, DeliveryStatus.PICKED_UP)
        payment = self.delivery.payments[0]
        self.assertEqual(self.delivery.amount_owing, Decimal("0.00"))
        gst = (payment.amount / 11).quantize(Decimal("0.01"))
        self.assertEqual(payment.receipt.gst, gst)

    def test_missing_parcel_is_refused(self) -> None:
        with self.assertRaisesRegex(ValidationError, "0 of 1"):
            self.system.perform_field_action(self.act(
                FieldActionKind.PICKUP_AND_PAYMENT,
                {"collected": 0, "method": "Cash"}))

    def test_card_needs_last_four_digits(self) -> None:
        with self.assertRaises(ValidationError):
            self.system.perform_field_action(self.act(
                FieldActionKind.PICKUP_AND_PAYMENT,
                {"collected": 1, "method": "Card", "card_last_four": "12"}))

    def test_full_journey_with_wrong_then_right_pin(self) -> None:
        self.system.perform_field_action(self.act(
            FieldActionKind.PICKUP_AND_PAYMENT,
            {"collected": 1, "method": "Card", "card_last_four": "4242"}))
        self.system.perform_field_action(self.act(FieldActionKind.DEPART))
        with self.assertRaisesRegex(ValidationError, "PIN"):
            self.system.perform_field_action(self.act(
                FieldActionKind.DELIVER,
                {"receiver_name": "Jo Lee", "pin": "x"}))
        pin = self.delivery.request.recipient.handover_pin
        self.system.perform_field_action(self.act(
            FieldActionKind.DELIVER, {"receiver_name": "Jo Lee",
                                      "pin": pin, "photo": "p.jpg"}))
        self.assertIs(self.delivery.status, DeliveryStatus.DELIVERED)
        self.assertEqual(self.delivery.proof_of_delivery["receiver_name"],
                         "Jo Lee")
        with self.assertRaises(BusinessRuleError):
            self.delivery.change_status(DeliveryStatus.IN_TRANSIT, "X",
                                        self.clock.now(), self.clock.now())

    def test_offline_queue_keeps_device_time_order(self) -> None:
        queue = self.system.device_queue(self.staff)
        queue.go_offline()
        first = self.act(FieldActionKind.PICKUP_AND_PAYMENT,
                         {"collected": 1, "method": "Cash"}, online=False)
        self.clock.advance(minutes=3)
        second = self.act(FieldActionKind.DEPART, online=False)
        queue.enqueue(second)
        queue.enqueue(first)
        reloaded = self.system.device_queue(self.staff)   # after restart
        self.assertEqual(len(reloaded.pending), 2)
        self.clock.advance(minutes=10)
        reloaded.go_online()
        results = reloaded.flush(self.system.perform_field_action)
        self.assertTrue(all(ok for _, _, ok in results))
        picked = self.delivery.events[-2]
        self.assertEqual(picked.occurred_at, first.device_time)
        self.assertGreater(picked.recorded_at, picked.occurred_at)

    def test_offline_card_payment_is_refused(self) -> None:
        with self.assertRaisesRegex(BusinessRuleError, "connection"):
            self.system.perform_field_action(self.act(
                FieldActionKind.PICKUP_AND_PAYMENT,
                {"collected": 1, "method": "Card",
                 "card_last_four": "4242"}, online=False))

    def test_conflict_when_reallocated_while_offline(self) -> None:
        action = self.act(FieldActionKind.ARRIVED_PICKUP, online=False)
        self.system.deactivate_driver(self.owner, self.staff.staff_id)
        with self.assertRaisesRegex(BusinessRuleError, "no longer"):
            self.system.perform_field_action(action)

    def test_cash_reconciliation(self) -> None:
        self.system.perform_field_action(self.act(
            FieldActionKind.PICKUP_AND_PAYMENT,
            {"collected": 1, "method": "Cash"}))
        payments = self.system.reconcile_cash(self.officer,
                                              self.staff.staff_id)
        self.assertTrue(all(p.status is PaymentStatus.RECONCILED
                            for p in payments))

    def test_tracking_history_is_append_only(self) -> None:
        self.system.perform_field_action(self.act(
            FieldActionKind.FAILED_ATTEMPT, {"reason": "Nobody home"}))
        delivery = self.system.track(self.delivery.tracking_ref.lower())
        notes = [e.note for e in delivery.events]
        self.assertIn("Failed attempt: Nobody home", notes)
        self.assertIs(delivery.status, DeliveryStatus.SCHEDULED)


if __name__ == "__main__":
    unittest.main()
