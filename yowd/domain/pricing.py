"""PricingPolicy: works out the price and creates the Quote."""

from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from yowd.domain.errors import BusinessRuleError
from yowd.domain.ports import AddressService
from yowd.domain.quote import Quote
from yowd.domain.values import TimeWindow


class PricingPolicy:
    """Base fee + distance + size/weight surcharges, from configuration.

    Kept as a single concrete class (A2 Section 6.4 rejected Strategy
    until discounts arrive).  ``price_lines`` is the one method a future
    subclass (e.g. a loyalty discount) would extend (QM3).
    """

    CENT = Decimal("0.01")
    __slots__ = ("__config", "__address_service", "__dispatcher")

    def __init__(self, config, address_service: AddressService,
                 dispatcher) -> None:
        self.__config = config
        self.__address_service = address_service
        self.__dispatcher = dispatcher

    def price_lines(self, request,
                    distance_km: float) -> list[tuple[str, Decimal]]:
        """Itemised price lines for a request."""
        cfg = self.__config
        lines = [("Base fee", cfg.rate("base_fee")),
                 (f"Distance {distance_km:.1f} km x "
                  f"${cfg.rate('per_km'):.2f}",
                  (Decimal(str(distance_km)) * cfg.rate("per_km")))]
        free_kg = cfg.rate("weight_free_kg")
        for number, parcel in enumerate(request.parcels, start=1):
            surcharge = cfg.size_surcharge(parcel.size_category)
            if surcharge:
                lines.append((f"Parcel {number} size "
                              f"({parcel.size_category})", surcharge))
            extra_kg = parcel.weight_kg - free_kg
            if extra_kg > 0:
                lines.append((f"Parcel {number} weight over {free_kg} kg",
                              extra_kg * cfg.rate("per_kg_over")))
        return [(label, amount.quantize(self.CENT, ROUND_HALF_UP))
                for label, amount in lines]

    def calculate(self, request) -> tuple[Decimal, list, float]:
        """Return (total incl. GST, price lines, distance km)."""
        if request.pickup.location is None or \
                request.dropoff.location is None:
            raise BusinessRuleError(
                "Both addresses must be verified before a price can be "
                "calculated. Office staff can enter a manual price.")
        distance = self.__address_service.distance_km(
            request.pickup.location, request.dropoff.location)
        lines = self.price_lines(request, distance)
        total = sum((amount for _, amount in lines), Decimal("0.00"))
        minimum = self.__config.rate("minimum_price")
        if total < minimum:
            lines.append(("Minimum charge adjustment", minimum - total))
            total = minimum
        return total.quantize(self.CENT, ROUND_HALF_UP), lines, distance

    def estimate_windows(self, request, distance_km: float,
                         now: datetime) -> tuple[TimeWindow, TimeWindow]:
        """Pickup window from the Dispatcher; delivery window after it."""
        cfg = self.__config
        pickup = self.__dispatcher.estimate_pickup_window(
            request.preferred_date, now)
        travel = timedelta(hours=distance_km
                           / cfg.time_limit("average_speed_kmh"))
        start = pickup.end + travel + timedelta(minutes=14)
        start = start.replace(minute=(start.minute // 15) * 15, second=0)
        delivery = TimeWindow(
            start, start + timedelta(
                hours=cfg.time_limit("delivery_window_hours")))
        return pickup, delivery

    def create_quote(self, quote_id: str, request, now: datetime,
                     manual_amount: Decimal | None = None,
                     staff_id: str = "", reason: str = "") -> Quote:
        """Create the quote (Creator: PricingPolicy has the data)."""
        if manual_amount is None:
            amount, lines, distance = self.calculate(request)
        else:
            amount, distance = manual_amount.quantize(self.CENT), 15.0
            lines = [("Manual price set by office staff", amount)]
        pickup, delivery = self.estimate_windows(request, distance, now)
        expiry = now + timedelta(
            hours=self.__config.time_limit("quote_valid_hours"))
        return Quote(quote_id, amount, pickup, delivery, now, expiry,
                     distance, lines, staff_id if manual_amount else "",
                     reason if manual_amount else "")
