"""GazetteerAddressService: the AddressService adapter used by the prototype.

AddressService (yowd.domain.ports) is the *target* interface of the
Adapter pattern (A2 Section 6.2).  The prototype cannot call a real
mapping provider, so this adapter answers from a small local suburb
gazetteer instead.  Replacing it with a real provider needs only a new
subclass of AddressService and one line in the bootstrap (QM7, D6).
"""

import math

from yowd.domain.ports import AddressService, VerificationResult


class GazetteerAddressService(AddressService):
    """Adapter over a local suburb gazetteer (stands in for a provider)."""

    # Suburb -> (postcode, latitude, longitude): a sample of Greater
    # Melbourne plus regional suburbs used to test the area check.
    __GAZETTEER: dict[str, tuple[str, float, float]] = {
        "MELBOURNE": ("3000", -37.8136, 144.9631),
        "SOUTHBANK": ("3006", -37.8230, 144.9650),
        "DOCKLANDS": ("3008", -37.8150, 144.9460),
        "CARLTON": ("3053", -37.8001, 144.9671),
        "FITZROY": ("3065", -37.7984, 144.9780),
        "COLLINGWOOD": ("3066", -37.8020, 144.9880),
        "RICHMOND": ("3121", -37.8230, 144.9980),
        "HAWTHORN": ("3122", -37.8221, 145.0350),
        "HAWTHORN EAST": ("3123", -37.8250, 145.0480),
        "CAMBERWELL": ("3124", -37.8420, 145.0580),
        "BOX HILL": ("3128", -37.8190, 145.1220),
        "KEW": ("3101", -37.8060, 145.0310),
        "SOUTH YARRA": ("3141", -37.8380, 144.9920),
        "PRAHRAN": ("3181", -37.8510, 144.9930),
        "ST KILDA": ("3182", -37.8676, 144.9809),
        "BRIGHTON": ("3186", -37.9056, 144.9860),
        "CAULFIELD": ("3162", -37.8800, 145.0230),
        "CLAYTON": ("3168", -37.9150, 145.1290),
        "DANDENONG": ("3175", -37.9870, 145.2150),
        "FRANKSTON": ("3199", -38.1440, 145.1260),
        "FOOTSCRAY": ("3011", -37.8000, 144.9000),
        "YARRAVILLE": ("3013", -37.8160, 144.8890),
        "WILLIAMSTOWN": ("3016", -37.8640, 144.8980),
        "SUNSHINE": ("3020", -37.7880, 144.8320),
        "WERRIBEE": ("3030", -37.9000, 144.6630),
        "ESSENDON": ("3040", -37.7550, 144.9190),
        "BRUNSWICK": ("3056", -37.7670, 144.9620),
        "COBURG": ("3058", -37.7440, 144.9660),
        "PRESTON": ("3072", -37.7430, 145.0110),
        "HEIDELBERG": ("3084", -37.7550, 145.0670),
        "DONCASTER": ("3108", -37.7880, 145.1250),
        "RINGWOOD": ("3134", -37.8150, 145.2290),
        "GLEN WAVERLEY": ("3150", -37.8780, 145.1650),
        "BURWOOD": ("3125", -37.8500, 145.1150),
        "GEELONG": ("3220", -38.1499, 144.3617),
        "BALLARAT": ("3350", -37.5622, 143.8503),
        "BENDIGO": ("3550", -36.7570, 144.2794),
    }

    __ROAD_FACTOR = 1.3          # straight line -> typical road distance
    __EARTH_RADIUS_KM = 6371.0

    def verify(self, suburb: str, postcode: str) -> VerificationResult:
        """Verify the suburb/postcode pair against the gazetteer."""
        key = (suburb or "").strip().upper()
        entry = self.__GAZETTEER.get(key)
        if entry is None:
            return VerificationResult(
                False, key.title(), postcode,
                message=f"Suburb '{suburb}' was not found by the address "
                        "service.")
        code, lat, lon = entry
        if code != (postcode or "").strip():
            return VerificationResult(
                False, key.title(), postcode,
                message=f"Postcode {postcode} does not match {key.title()} "
                        f"(expected {code}).")
        return VerificationResult(True, key.title(), code, lat, lon)

    def distance_km(self, origin: VerificationResult,
                    destination: VerificationResult) -> float:
        """Haversine distance multiplied by a road factor, 1 dp."""
        lat1 = math.radians(origin.latitude)
        lon1 = math.radians(origin.longitude)
        lat2 = math.radians(destination.latitude)
        lon2 = math.radians(destination.longitude)
        hav = (math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1)
               * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
        straight = 2 * self.__EARTH_RADIUS_KM * math.asin(math.sqrt(hav))
        return round(max(straight * self.__ROAD_FACTOR, 1.0), 1)

    def suburbs(self) -> list[tuple[str, str]]:
        """Known (suburb, postcode) pairs, for pick lists in the UI."""
        return sorted((name.title(), entry[0])
                      for name, entry in self.__GAZETTEER.items())
