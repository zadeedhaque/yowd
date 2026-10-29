"""Input validation of the data holders and domain objects (P2, QU7)."""

import unittest
from decimal import Decimal

from tests.support import SystemTestCase
from yowd.domain.errors import ValidationError
from yowd.domain.values import ContactDetails


class ContactDetailsTest(unittest.TestCase):
    """ContactDetails checks name, phone and email."""

    def test_blank_name_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            ContactDetails("  ", "0412345678")

    def test_bad_phone_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            ContactDetails("Jo", "12345")

    def test_phone_is_normalised(self) -> None:
        self.assertEqual(ContactDetails("Jo", "0412 345 678").phone,
                         "0412345678")

    def test_bad_email_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            ContactDetails("Jo", "0412345678", "jo@nowhere")


class ParcelAndAddressTest(SystemTestCase):
    """Parcels and addresses validate themselves."""

    def test_parcel_over_weight_limit(self) -> None:
        with self.assertRaisesRegex(ValidationError, "30 kg limit"):
            self.system.make_parcel("Bricks", "General goods", "30", "30",
                                    "30", "31")

    def test_prohibited_category(self) -> None:
        with self.assertRaisesRegex(ValidationError, "cannot carry"):
            self.system.make_parcel("Puppy", "Live animals", "40", "40",
                                    "40", "5")

    def test_non_numeric_dimension(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a number"):
            self.system.make_parcel("Box", "General goods", "abc", "1",
                                    "1", "1")

    def test_size_band(self) -> None:
        parcel = self.system.make_parcel("Box", "General goods", "50", "40",
                                         "30", "2")
        self.assertEqual(parcel.size_category, "Medium")
        self.assertEqual(parcel.volume_litres, Decimal(60))

    def test_postcode_format(self) -> None:
        with self.assertRaisesRegex(ValidationError, "4 digits"):
            self.system.make_address("1 Main Street", "Kew", "31O1")

    def test_street_needs_number(self) -> None:
        with self.assertRaisesRegex(ValidationError, "street number"):
            self.system.make_address("Main Street", "Kew", "3101")

    def test_preferred_date_range(self) -> None:
        with self.assertRaises(ValidationError):
            self.system.parse_preferred_date("01/01/2020")
        with self.assertRaises(ValidationError):
            self.system.parse_preferred_date("30-10-2026")
        self.assertEqual(self.system.parse_preferred_date("2026-10-30"),
                         self.system.parse_preferred_date("30/10/2026"))
        self.assertEqual(self.system.parse_preferred_date("").isoformat(),
                         "2026-10-29")


if __name__ == "__main__":
    unittest.main()
