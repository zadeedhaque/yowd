"""SystemConfiguration: every business setting, loaded from config.json.

Responsibilities (A2 CRC 4.2, unchanged in intent):
* knows the operating area and whether a postcode is inside it;
* knows pricing rates, parcel limits and time limits;
* knows the allowed delivery status transitions and decides whether a
  requested change is allowed (QM1, QM2, QM6);
* accepts changes only from an owner and records who changed what.
"""

import copy
import json
from decimal import Decimal
from typing import Any

from yowd.domain.errors import AuthorisationError, BusinessRuleError
from yowd.domain.ports import TextStorage
from yowd.domain.statuses import DeliveryStatus


class SystemConfiguration:
    """Holds and checks the configurable business rules."""

    __slots__ = ("__settings", "__source", "__log", "__transitions")

    def __init__(self, settings: dict[str, Any],
                 source: TextStorage | None = None) -> None:
        self.__settings = copy.deepcopy(settings)
        self.__source = source
        self.__log: list[str] = []
        self.__transitions = {
            DeliveryStatus.from_label(src): frozenset(
                DeliveryStatus.from_label(dst) for dst in targets)
            for src, targets in settings["status_transitions"].items()}

    @classmethod
    def load(cls, source: TextStorage) -> "SystemConfiguration":
        """Read the configuration document created by the owner."""
        return cls(json.loads(source.read()), source)

    @property
    def change_log(self) -> tuple[str, ...]:
        """Who changed which setting (QS4)."""
        return tuple(self.__log)

    # ----------------------------------------------------- business info
    @property
    def business_name(self) -> str:
        """Trading name printed on receipts and reports (SRS D3)."""
        return self.__settings["business"]["name"]

    @property
    def business_abn(self) -> str:
        """ABN printed on tax invoices."""
        return self.__settings["business"]["abn"]

    @property
    def business_address(self) -> str:
        """Business address printed on tax invoices."""
        return self.__settings["business"]["address"]

    @property
    def gst_rate(self) -> Decimal:
        """GST rate (DA15: 10%)."""
        return Decimal(self.__settings["business"]["gst_rate"])

    # ---------------------------------------------------- operating area
    @property
    def operating_area_name(self) -> str:
        """Name of the area served, e.g. Greater Melbourne."""
        return self.__settings["operating_area"]["name"]

    def is_in_operating_area(self, postcode: str) -> bool:
        """Decide whether a postcode is served (QM2)."""
        if not postcode.isdigit():
            return False
        code = int(postcode)
        return any(low <= code <= high for low, high in
                   self.__settings["operating_area"]["postcode_ranges"])

    # ----------------------------------------------------------- pricing
    def rate(self, name: str) -> Decimal:
        """Return a pricing rate such as ``base_fee`` or ``per_km``."""
        return Decimal(self.__settings["pricing"][name])

    def size_surcharge(self, size_category: str) -> Decimal:
        """Surcharge for a parcel size category."""
        return Decimal(
            self.__settings["pricing"]["size_surcharge"][size_category])

    # ----------------------------------------------------- parcel limits
    def parcel_limit(self, name: str) -> Decimal:
        """Return a parcel limit such as ``max_weight_kg``."""
        return Decimal(self.__settings["parcel_limits"][name])

    @property
    def parcel_categories(self) -> list[str]:
        """Categories YOWD accepts."""
        return list(self.__settings["parcel_limits"]["categories"])

    @property
    def prohibited_categories(self) -> list[str]:
        """Categories YOWD refuses (SRS Task 6 variant c)."""
        return list(self.__settings["parcel_limits"]["prohibited_categories"])

    # ------------------------------------------------------- time limits
    def time_limit(self, name: str) -> int:
        """Return a time limit such as ``quote_valid_hours``."""
        return int(self.__settings["time_limits"][name])

    # ---------------------------------------------- status transitions
    def allowed_next(self, current: DeliveryStatus) -> set[DeliveryStatus]:
        """Statuses that may follow ``current``."""
        return set(self.__transitions.get(current, frozenset()))

    def check_transition(self, current: DeliveryStatus,
                         target: DeliveryStatus) -> None:
        """Raise BusinessRuleError, with a reason, if not allowed."""
        if target not in self.__transitions.get(current, set()):
            allowed = ", ".join(sorted(s.value for s in
                                       self.allowed_next(current)))
            raise BusinessRuleError(
                f"A delivery cannot move from '{current.value}' to "
                f"'{target.value}'. Allowed next steps: "
                f"{allowed or 'none (the delivery is closed)'}.")

    # --------------------------------------------------------- templates
    def template(self, event: str) -> str:
        """Notification template for an event name."""
        return self.__settings["templates"].get(event, "{ref}: " + event)

    # ------------------------------------------------------------ change
    def update_rate(self, actor: Any, name: str, value: Decimal) -> None:
        """Change a pricing rate.  Only an owner may do this (QM1)."""
        if not getattr(actor, "is_owner", False):
            raise AuthorisationError("Only an owner can change pricing "
                                     "rates.")
        if name not in self.__settings["pricing"] or name == "size_surcharge":
            raise BusinessRuleError(f"'{name}' is not a pricing rate.")
        if value < 0:
            raise BusinessRuleError("A rate cannot be negative.")
        old = self.__settings["pricing"][name]
        self.__settings["pricing"][name] = f"{value:.2f}"
        self.__log.append(
            f"{actor.staff_id} changed {name} from {old} to {value:.2f}")
        self.save()

    def save(self) -> None:
        """Write the settings back to the configuration file."""
        if self.__source is not None:
            self.__source.write(json.dumps(self.__settings, indent=2))
