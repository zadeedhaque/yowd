"""Address: a pickup, drop-off or saved address that checks itself."""

import re

from yowd.domain.errors import ValidationError
from yowd.domain.ports import AddressService, VerificationResult


class Address:
    """Street, suburb, state, postcode and delivery instructions."""

    STATES = ("VIC", "NSW", "QLD", "SA", "WA", "TAS", "NT", "ACT")
    __POSTCODE = re.compile(r"^\d{4}$")
    __slots__ = ("__street", "__suburb", "__postcode", "__state",
                 "__instructions", "__verified", "__in_area", "__problem",
                 "__location")

    def __init__(self, street: str, suburb: str, postcode: str,
                 state: str = "VIC", instructions: str = "") -> None:
        street, suburb = (street or "").strip(), (suburb or "").strip()
        postcode = (postcode or "").strip()
        state = (state or "").strip().upper()
        instructions = (instructions or "").strip()
        if not street:
            raise ValidationError("Street address cannot be blank, e.g. "
                                  "12 Smith Street.")
        if not any(ch.isdigit() for ch in street):
            raise ValidationError("Street address must include a street "
                                  "number, e.g. 12 Smith Street.")
        if not suburb:
            raise ValidationError("Suburb cannot be blank.")
        if not self.__POSTCODE.match(postcode):
            raise ValidationError("Postcode must be exactly 4 digits, "
                                  "e.g. 3122.")
        if state not in self.STATES:
            raise ValidationError("State must be one of: "
                                  + ", ".join(self.STATES) + ".")
        if len(instructions) > 120:
            raise ValidationError("Instructions must be 120 characters or "
                                  "fewer.")
        self.__street = street
        self.__suburb = suburb.title()
        self.__postcode = postcode
        self.__state = state
        self.__instructions = instructions
        self.__verified = False
        self.__in_area = False
        self.__problem = ""
        self.__location: VerificationResult | None = None

    @classmethod
    def restore(cls, street: str, suburb: str, postcode: str, state: str,
                instructions: str, verified: bool, in_area: bool,
                problem: str,
                location: VerificationResult | None) -> "Address":
        """Rebuild a stored address including its verification result."""
        address = cls(street, suburb, postcode, state, instructions)
        address.__verified = verified
        address.__in_area = in_area
        address.__problem = problem
        address.__location = location
        return address

    # ----------------------------------------------------------- read-only
    @property
    def street(self) -> str:
        """Street number and name."""
        return self.__street

    @property
    def suburb(self) -> str:
        """Suburb in title case."""
        return self.__suburb

    @property
    def postcode(self) -> str:
        """Four-digit postcode."""
        return self.__postcode

    @property
    def state(self) -> str:
        """State abbreviation."""
        return self.__state

    @property
    def instructions(self) -> str:
        """Optional delivery instructions."""
        return self.__instructions

    @property
    def verified(self) -> bool:
        """True once the AddressService recognised it."""
        return self.__verified

    @property
    def in_operating_area(self) -> bool:
        """True if inside the configured operating area."""
        return self.__in_area

    @property
    def problem(self) -> str:
        """Why the address cannot be used ("" if it can)."""
        return self.__problem

    @property
    def location(self) -> VerificationResult | None:
        """Verified location, used for distances."""
        return self.__location

    # --------------------------------------------------------- behaviour
    def verify(self, service: AddressService, config) -> bool:
        """Verify through the AddressService and check the area.

        Returns True when the address is verified and inside the
        operating area.  Otherwise ``problem`` explains why, and the
        caller flags the request for office review (Task 1 variant c).
        """
        result = service.verify(self.__suburb, self.__postcode)
        self.__verified = result.verified and self.__state == "VIC"
        self.__location = result if result.verified else None
        self.__in_area = config.is_in_operating_area(self.__postcode)
        if not result.verified:
            self.__problem = result.message
        elif self.__state != "VIC":
            self.__problem = "YOWD currently only operates in Victoria."
        elif not self.__in_area:
            self.__problem = (f"{self.__suburb} {self.__postcode} is outside "
                              f"the {config.operating_area_name} operating "
                              "area.")
        else:
            self.__problem = ""
        return self.__verified and self.__in_area

    def same_place(self, other: "Address") -> bool:
        """True if the two addresses are the same place."""
        return (self.__street.lower() == other.street.lower()
                and self.__postcode == other.postcode)

    def formatted(self) -> str:
        """One-line form for quotes, receipts and job lists."""
        return (f"{self.__street}, {self.__suburb} {self.__state} "
                f"{self.__postcode}")
