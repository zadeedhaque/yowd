"""Parcel: one physical item in a request; validates itself."""

from decimal import Decimal, InvalidOperation

from yowd.domain.errors import ValidationError


class Parcel:
    """Description, category, dimensions (cm) and weight (kg)."""

    __slots__ = ("__description", "__category", "__length", "__width",
                 "__height", "__weight", "__size", "__collected")

    def __init__(self, description: str, category: str, length_cm: str,
                 width_cm: str, height_cm: str, weight_kg: str,
                 config) -> None:
        if not description or not description.strip():
            raise ValidationError("Parcel description cannot be blank, "
                                  "e.g. 'Box of books'.")
        self.__description = description.strip()[:60]
        self.__category = category
        self.__length = self.__positive(length_cm, "Length")
        self.__width = self.__positive(width_cm, "Width")
        self.__height = self.__positive(height_cm, "Height")
        self.__weight = self.__positive(weight_kg, "Weight")
        self.__collected = False
        self.__check_limits(config)
        self.__size = self.__size_band(config)

    # ----------------------------------------------------------- read-only
    @property
    def description(self) -> str:
        """What the parcel is."""
        return self.__description

    @property
    def category(self) -> str:
        """One of the configured categories."""
        return self.__category

    @property
    def length_cm(self) -> Decimal:
        """Length in centimetres."""
        return self.__length

    @property
    def width_cm(self) -> Decimal:
        """Width in centimetres."""
        return self.__width

    @property
    def height_cm(self) -> Decimal:
        """Height in centimetres."""
        return self.__height

    @property
    def weight_kg(self) -> Decimal:
        """Weight in kilograms."""
        return self.__weight

    @property
    def size_category(self) -> str:
        """Small, Medium or Large (from volume)."""
        return self.__size

    @property
    def collected(self) -> bool:
        """True once picked up by a driver."""
        return self.__collected

    @property
    def volume_litres(self) -> Decimal:
        """Volume in litres (1 litre = 1000 cubic cm)."""
        return self.__length * self.__width * self.__height / Decimal(1000)

    # --------------------------------------------------------- behaviour
    def mark_collected(self) -> None:
        """Record that the driver has this parcel (Task 6)."""
        self.__collected = True

    def summary(self) -> str:
        """One-line description used in lists."""
        return (f"{self.__description} ({self.__category}, "
                f"{self.__length:g}x{self.__width:g}x{self.__height:g} cm,"
                f" {self.__weight:g} kg, {self.__size})")

    # ----------------------------------------------------------- private
    @staticmethod
    def __positive(value: str, label: str) -> Decimal:
        try:
            number = Decimal(str(value).strip())
        except InvalidOperation as exc:
            raise ValidationError(f"{label} must be a number, e.g. 30 or "
                                  "2.5.") from exc
        if not number.is_finite() or number <= 0:
            raise ValidationError(f"{label} must be greater than zero.")
        return number

    def __check_limits(self, config) -> None:
        """Reject prohibited items and anything over the limits (P2)."""
        if self.__category in config.prohibited_categories:
            raise ValidationError(
                f"YOWD cannot carry '{self.__category}'. Please remove this "
                "item from the request.")
        if self.__category not in config.parcel_categories:
            raise ValidationError("Choose a category from the list shown.")
        max_kg = config.parcel_limit("max_weight_kg")
        if self.__weight > max_kg:
            raise ValidationError(
                f"Weight {self.__weight} kg is over the {max_kg} kg limit. "
                "Split it into lighter parcels.")
        max_side = config.parcel_limit("max_side_cm")
        if max(self.__length, self.__width, self.__height) > max_side:
            raise ValidationError(
                f"No side may be longer than {max_side} cm.")
        girth = self.__length + self.__width + self.__height
        max_girth = config.parcel_limit("max_girth_cm")
        if girth > max_girth:
            raise ValidationError(
                f"Length + width + height is {girth} cm; the limit is "
                f"{max_girth} cm.")

    def __size_band(self, config) -> str:
        volume = self.volume_litres
        if volume <= config.parcel_limit("small_max_volume_l"):
            return "Small"
        if volume <= config.parcel_limit("medium_max_volume_l"):
            return "Medium"
        return "Large"
