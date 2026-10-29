"""Business area 1: logging requests, quoting and answering (T1-T3)."""

import unittest
from decimal import Decimal

from tests.support import SystemTestCase
from yowd.domain.errors import AuthorisationError, BusinessRuleError
from yowd.domain.statuses import (DeliveryStatus, QuoteStatus,
                                  RequestStatus)


class RequestAndQuoteTest(SystemTestCase):
    """Request -> quote -> accept / decline / expire."""

    def test_valid_request_is_quoted(self) -> None:
        request = self.new_request()
        self.assertIs(request.status, RequestStatus.QUOTED)
        quote = request.current_quote
        total = sum(amount for _, amount in quote.breakdown)
        self.assertEqual(total, quote.amount)
        self.assertGreaterEqual(quote.amount, Decimal("20.00"))
        self.assertLess(quote.pickup_window.end,
                        quote.delivery_window.end)

    def test_weight_surcharge_applies(self) -> None:
        light = self.new_request(kg="4").current_quote.amount
        heavy = self.new_request(kg="15").current_quote.amount
        self.assertEqual(heavy - light, Decimal("8.00"))   # 10 kg x 0.80

    def test_out_of_area_is_flagged_not_quoted(self) -> None:
        request = self.new_request(drop=("10 Moorabool Street", "Geelong",
                                         "3220"))
        self.assertIs(request.status, RequestStatus.REQUESTED)
        self.assertTrue(request.needs_office_review)
        self.assertIn("outside", request.flags[0])
        self.assertIn(request,
                      self.system.requests_for_review(self.officer))

    def test_office_manual_quote_for_flagged_request(self) -> None:
        request = self.new_request(drop=("10 Moorabool Street", "Geelong",
                                         "3220"))
        self.system.manual_quote(self.officer, request.request_id, "95",
                                 "Approved regional run")
        self.assertEqual(request.current_quote.amount, Decimal("95.00"))
        self.assertEqual(request.current_quote.overridden_by, "S002")

    def test_accept_creates_delivery_with_pin(self) -> None:
        delivery = self.accepted_delivery()
        self.assertIs(delivery.status, DeliveryStatus.ACCEPTED)
        self.assertEqual(len(delivery.request.recipient.handover_pin), 4)
        self.assertIs(delivery.quote.status, QuoteStatus.ACCEPTED)

    def test_decline_makes_request_rejected(self) -> None:
        request = self.new_request()
        self.system.respond_to_quote(self.customer, request.request_id,
                                     False)
        self.assertIs(request.status, RequestStatus.REJECTED)

    def test_expired_quote_cannot_be_accepted(self) -> None:
        request = self.new_request()
        self.clock.advance(hours=25)
        with self.assertRaisesRegex(BusinessRuleError, "expired"):
            self.system.respond_to_quote(self.customer, request.request_id,
                                         True)
        self.assertIs(request.status, RequestStatus.REJECTED)

    def test_other_customer_cannot_answer(self) -> None:
        request = self.new_request()
        other = self.system.find_customer("d.okafor@example.com")
        with self.assertRaises(AuthorisationError):
            self.system.respond_to_quote(other, request.request_id, True)

    def test_price_override_needs_reason(self) -> None:
        request = self.new_request()
        with self.assertRaises(Exception):
            self.system.override_quote(self.officer, request.request_id,
                                       "30", "  ")
        self.system.override_quote(self.officer, request.request_id, "30",
                                   "Regular customer")
        self.assertEqual(request.current_quote.amount, Decimal("30.00"))

    def test_duplicate_customer_refused(self) -> None:
        with self.assertRaises(BusinessRuleError):
            self.system.register_customer("Sarah C", "0400000000",
                                          "sarah.chen@example.com")


if __name__ == "__main__":
    unittest.main()
