"""Tests for the object-oriented safeguards: interfaces, private state,
immutability, dependency injection and the Melbourne time zone."""

import dataclasses
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from tests.support import ROOT, START, SystemTestCase
from yowd.app.input_parser import InputParser
from yowd.app.system import DeliveryManagementSystem
from yowd.app.workspace import FolderWorkspace, MemoryWorkspace
from yowd.domain.clock import MELBOURNE, FixedClock
from yowd.domain.errors import BusinessRuleError, ValidationError
from yowd.domain.field_action import (DeliverAction, FieldAction,
                                      OfflineSyncQueue, PickupAction)
from yowd.domain.ports import (AddressService, Clock, DeliveryObserver,
                               GatewayResult, PaymentGateway,
                               VerificationResult)
from yowd.domain.statuses import FieldActionKind, RequestStatus
from yowd.domain.values import ContactDetails
from yowd.services.storage import MemoryTextStorage


class InterfaceTest(unittest.TestCase):
    """Abstract base classes behave like interfaces."""

    def test_interface_cannot_be_instantiated(self) -> None:
        for port in (Clock, AddressService, PaymentGateway,
                     DeliveryObserver):
            with self.subTest(port=port.__name__):
                with self.assertRaises(TypeError):
                    port()

    def test_incomplete_implementation_is_refused(self) -> None:
        class HalfGateway(PaymentGateway):
            """Forgets to implement charge()."""

        with self.assertRaises(TypeError):
            HalfGateway()


class EncapsulationTest(SystemTestCase):
    """Private state can only be changed through methods."""

    def test_private_attribute_is_hidden(self) -> None:
        with self.assertRaises(AttributeError):
            _ = self.customer.__contact      # name-mangled, not reachable

    def test_properties_are_read_only(self) -> None:
        with self.assertRaises(AttributeError):
            self.customer.contact = ContactDetails("X", "0400000000")
        request = self.new_request()
        with self.assertRaises(AttributeError):
            request.status = RequestStatus.ACCEPTED

    def test_slots_stop_stray_attributes(self) -> None:
        with self.assertRaises(AttributeError):
            self.customer.nickname = "Sas"

    def test_collections_are_copies(self) -> None:
        request = self.new_request()
        self.assertIsInstance(request.parcels, tuple)
        with self.assertRaises(AttributeError):
            request.parcels.append("extra")

    def test_value_objects_are_frozen(self) -> None:
        contact = ContactDetails("Jo", "0412345678")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            contact.name = "Bo"

    def test_event_proof_is_read_only(self) -> None:
        delivery = self.accepted_delivery()
        with self.assertRaises(TypeError):
            delivery.events[0].proof["photo"] = "fake.jpg"

    def test_observer_must_implement_the_interface(self) -> None:
        delivery = self.accepted_delivery()
        with self.assertRaises(TypeError):
            delivery.add_observer(object())

    def test_state_changes_go_through_rules(self) -> None:
        driver = self.system.login_driver("D003")
        driver.deactivate()
        with self.assertRaises(BusinessRuleError):
            driver.deactivate()


class FakeAddressService(AddressService):
    """Test double: knows no addresses."""

    def verify(self, suburb: str, postcode: str) -> VerificationResult:
        return VerificationResult(False, suburb, postcode,
                                  message="Provider unavailable.")

    def distance_km(self, origin, destination) -> float:
        return 0.0


class DecliningGateway(PaymentGateway):
    """Test double: every card is declined."""

    def charge(self, amount: Decimal, card_last_four: str) -> GatewayResult:
        return GatewayResult(False, "", "Card declined by the bank.")


class DependencyInjectionTest(unittest.TestCase):
    """Collaborators can be replaced by test doubles."""

    def setUp(self) -> None:
        self.config = (ROOT / "data" / "config.json").read_text(
            encoding="utf-8")

    def build(self, **adapters) -> DeliveryManagementSystem:
        return DeliveryManagementSystem(MemoryWorkspace(self.config),
                                        FixedClock(START), **adapters)

    def test_fake_address_service_flags_request(self) -> None:
        system = self.build(address_service=FakeAddressService())
        customer = system.find_customer("sarah.chen@example.com")
        request = system.submit_request(
            customer, system.make_address("1 A Street", "Kew", "3101"),
            system.make_address("2 B Street", "Carlton", "3053"),
            system.make_recipient("Jo", "0412345678"),
            [system.make_parcel("Box", "General goods", "10", "10", "10",
                                "1")], START.date(), customer.customer_id)
        self.assertTrue(request.needs_office_review)
        self.assertIn("Provider unavailable.", request.flags[0])

    def test_declined_card_is_reported(self) -> None:
        system = self.build(payment_gateway=DecliningGateway())
        customer = system.find_customer("sarah.chen@example.com")
        request = system.submit_request(
            customer, system.make_address("1 A Street", "Kew", "3101"),
            system.make_address("2 B Street", "Carlton", "3053"),
            system.make_recipient("Jo", "0412345678"),
            [system.make_parcel("Box", "General goods", "10", "10", "10",
                                "1")], START.date(), customer.customer_id)
        delivery = system.respond_to_quote(customer, request.request_id,
                                           True)
        officer = system.login_office("S002")
        staff = system.candidates_for(officer, delivery.tracking_ref)[0]
        system.allocate(officer, delivery.tracking_ref, staff.staff_id)
        system.acknowledge(staff, delivery.tracking_ref)
        action = system.new_field_action(
            staff, FieldActionKind.PICKUP_AND_PAYMENT, delivery.tracking_ref,
            {"collected": 1, "method": "Card", "card_last_four": "4242"})
        with self.assertRaisesRegex(BusinessRuleError, "declined"):
            system.perform_field_action(action)


class FieldActionFactoryTest(unittest.TestCase):
    """The Command hierarchy and its device queue."""

    def test_factory_builds_the_right_subclass(self) -> None:
        pickup = FieldAction.create(FieldActionKind.PICKUP_AND_PAYMENT,
                                    "YW1", "D001", START)
        deliver = FieldAction.create(FieldActionKind.DELIVER, "YW1",
                                     "D001", START)
        self.assertIsInstance(pickup, PickupAction)
        self.assertIsInstance(deliver, DeliverAction)

    def test_queue_round_trip_through_storage(self) -> None:
        storage = MemoryTextStorage()
        queue = OfflineSyncQueue("D001", storage)
        queue.go_offline()
        queue.enqueue(FieldAction.create(FieldActionKind.DEPART, "YW1",
                                         "D001", START, online=False))
        again = OfflineSyncQueue("D001", storage)
        self.assertEqual(len(again.pending), 1)
        self.assertEqual(again.pending[0].device_time, START)

    def test_flush_refused_while_offline(self) -> None:
        queue = OfflineSyncQueue("D001")
        queue.go_offline()
        with self.assertRaises(BusinessRuleError):
            queue.flush(lambda action: "ok")

    def test_queue_rejects_other_drivers_actions(self) -> None:
        queue = OfflineSyncQueue("D001")
        with self.assertRaises(BusinessRuleError):
            queue.enqueue(FieldAction.create(FieldActionKind.DEPART, "YW1",
                                             "D002", START))


class MelbourneTimeTest(unittest.TestCase):
    """The built-in time zone follows Victoria's daylight saving."""

    def test_offsets(self) -> None:
        winter = datetime(2026, 7, 1, 12, 0, tzinfo=MELBOURNE)
        summer = datetime(2026, 12, 1, 12, 0, tzinfo=MELBOURNE)
        self.assertEqual(winter.utcoffset(), timedelta(hours=10))
        self.assertEqual(summer.utcoffset(), timedelta(hours=11))

    def test_daylight_saving_starts_first_sunday_of_october(self) -> None:
        before = datetime(2026, 10, 3, 15, 59, tzinfo=timezone.utc)
        after = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
        self.assertEqual(before.astimezone(MELBOURNE).hour, 1)
        self.assertEqual(after.astimezone(MELBOURNE).hour, 3)
        self.assertEqual(after.astimezone(MELBOURNE).tzname(), "AEDT")


class InputParserTest(unittest.TestCase):
    """Shared parsing rules."""

    def test_money(self) -> None:
        self.assertEqual(InputParser.money("$45.5"), Decimal("45.50"))
        for bad in ("abc", "0", "-3", "NaN"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    InputParser.money(bad)

    def test_window(self) -> None:
        window = InputParser.window("2026-10-30", "07:00", "13:00")
        self.assertEqual(window.end - window.start, timedelta(hours=6))
        with self.assertRaises(ValidationError):
            InputParser.window("30/10/2026", "05:00", "08:00")


class FolderWorkspaceTest(unittest.TestCase):
    """The console's on-disk workspace saves and resets correctly."""

    def test_records_survive_restart_and_reset(self) -> None:
        folder = Path(tempfile.mkdtemp())
        try:
            shutil.copy(ROOT / "data" / "config.json", folder)
            workspace = FolderWorkspace(folder)
            DeliveryManagementSystem(workspace, FixedClock(START))
            self.assertTrue((folder / "yowd_data.json").exists())
            workspace.reset()
            self.assertFalse((folder / "yowd_data.json").exists())
            self.assertTrue((folder / "config.json").exists())
        finally:
            shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
