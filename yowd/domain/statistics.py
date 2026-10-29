"""StatisticsCalculator and StatisticsReport (Task 9)."""

import csv
import io
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from yowd.domain.statuses import (DeliveryStatus, PaymentMethod,
                                  PaymentStatus, RequestStatus)
from yowd.domain.values import ReportPeriod


@dataclass(frozen=True)
class StatisticsReport:
    """The figures for one period and scope (immutable result)."""

    period: ReportPeriod
    scope: str
    by_status: Mapping[str, int]
    total_deliveries: int
    delivered: int
    on_time: int
    failed_attempts: int
    quotes_answered: int
    quotes_accepted: int
    revenue: Decimal
    cash_unreconciled: Decimal

    @property
    def on_time_rate(self) -> str:
        """Percentage of delivered parcels inside the quoted window."""
        if not self.delivered:
            return "n/a"
        return f"{100 * self.on_time / self.delivered:.0f}%"

    @property
    def acceptance_rate(self) -> str:
        """Accepted quotes as a share of answered or expired quotes."""
        if not self.quotes_answered:
            return "n/a"
        return f"{100 * self.quotes_accepted / self.quotes_answered:.0f}%"

    def rows(self) -> list[tuple[str, str]]:
        """Label/value rows used by the screens and the CSV export."""
        rows = [("Period", self.period.label()), ("Scope", self.scope),
                ("Deliveries (accepted in period)",
                 str(self.total_deliveries))]
        rows += [(f"  - {status}", str(count))
                 for status, count in self.by_status.items()]
        rows += [("Delivered", str(self.delivered)),
                 ("On-time rate", self.on_time_rate),
                 ("Failed attempts", str(self.failed_attempts)),
                 ("Quote acceptance rate", self.acceptance_rate),
                 ("Revenue collected", f"${self.revenue:.2f}"),
                 ("Cash not yet reconciled",
                  f"${self.cash_unreconciled:.2f}")]
        return rows

    def to_csv(self) -> str:
        """Spreadsheet-compatible text (P5)."""
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Measure", "Value"])
        writer.writerows(self.rows())
        return buffer.getvalue()

    def file_name(self) -> str:
        """Suggested CSV file name."""
        return (f"statistics_{self.period.kind}_"
                f"{self.period.first_day:%Y%m%d}.csv")


class _Tally:
    """Running totals used only while one report is computed."""

    __slots__ = ("__by_status", "__total", "__delivered", "__on_time",
                 "__failed", "__answered", "__accepted", "__revenue",
                 "__cash")

    def __init__(self) -> None:
        self.__by_status = {s.value: 0 for s in DeliveryStatus}
        self.__total = self.__delivered = self.__on_time = 0
        self.__failed = self.__answered = self.__accepted = 0
        self.__revenue = Decimal("0.00")
        self.__cash = Decimal("0.00")

    def add_delivery(self, delivery) -> None:
        """Count one delivery, its attempts and its payments."""
        self.__total += 1
        self.__by_status[delivery.status.value] += 1
        self.__failed += sum(1 for e in delivery.events
                             if e.note.startswith("Failed attempt"))
        delivered_at = delivery.delivered_at()
        if delivered_at is not None:
            self.__delivered += 1
            if delivered_at <= delivery.quote.delivery_window.end:
                self.__on_time += 1
        for payment in delivery.payments:
            self.__revenue += payment.amount
            if payment.status is PaymentStatus.COMPLETED and \
                    payment.method is PaymentMethod.CASH:
                self.__cash += payment.amount

    def add_request(self, request) -> None:
        """Count an answered (accepted or rejected) request."""
        if request.status in (RequestStatus.ACCEPTED,
                              RequestStatus.REJECTED):
            self.__answered += 1
            if request.status is RequestStatus.ACCEPTED:
                self.__accepted += 1

    def report(self, period: ReportPeriod, scope: str) -> StatisticsReport:
        """Freeze the totals into a StatisticsReport."""
        return StatisticsReport(
            period, scope,
            MappingProxyType({k: v for k, v in self.__by_status.items()
                              if v}),
            self.__total, self.__delivered, self.__on_time, self.__failed,
            self.__answered, self.__accepted, self.__revenue, self.__cash)


class StatisticsCalculator:
    """Computes reports from stored records (DA14, no warehouse)."""

    __slots__ = ("__registry",)

    def __init__(self, registry) -> None:
        self.__registry = registry

    def report(self, period: ReportPeriod, staff=None) -> StatisticsReport:
        """Overall figures, or only one driver's when ``staff`` given."""
        scope = ("All deliveries" if staff is None else
                 f"Delivery staff {staff.staff_id} {staff.contact.name}")
        tally = _Tally()
        for delivery in self.__registry.deliveries():
            if self.__in_scope(delivery, period, staff):
                tally.add_delivery(delivery)
        if staff is None:
            for request in self.__registry.requests():
                if period.contains(request.created_at):
                    tally.add_request(request)
        return tally.report(period, scope)

    @staticmethod
    def __in_scope(delivery, period: ReportPeriod, staff) -> bool:
        if not delivery.events or \
                not period.contains(delivery.events[0].occurred_at):
            return False
        return staff is None or any(a.staff.staff_id == staff.staff_id
                                    for a in delivery.allocations)
