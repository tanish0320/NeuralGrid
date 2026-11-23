from __future__ import annotations

import math
import re
from typing import TypedDict


class VenueIdentity(TypedDict):
    canonical_name: str
    latitude: float
    longitude: float
    aliases: list[str]


# Bengaluru major venue registry with canonical names, precise coordinates, and common alias strings
BENGALURU_VENUES: dict[str, VenueIdentity] = {
    "palace_grounds": {
        "canonical_name": "Palace Grounds",
        "latitude": 12.9988,
        "longitude": 77.5921,
        "aliases": [
            "palace grounds",
            "bangalore palace",
            "bengaluru palace",
            "tripuravasini",
            "gayathri vihar",
            "princess shrine",
            "sheesh mahal",
            "manpho convention",
            "jayamahal",
        ],
    },
    "chinnaswamy": {
        "canonical_name": "M. Chinnaswamy Stadium",
        "latitude": 12.9788,
        "longitude": 77.5996,
        "aliases": [
            "chinnaswamy",
            "m chinnaswamy stadium",
            "m. chinnaswamy",
            "chinnaswamy stadium",
            "ksca",
            "queens road stadium",
        ],
    },
    "kanteerava": {
        "canonical_name": "Sree Kanteerava Stadium",
        "latitude": 12.9698,
        "longitude": 77.5926,
        "aliases": [
            "kanteerava",
            "sree kanteerava",
            "kanteerava stadium",
            "kanteerava indoor stadium",
            "sampangi rama nagara stadium",
        ],
    },
    "ktpo": {
        "canonical_name": "KTPO Trade Centre Whitefield",
        "latitude": 12.9796,
        "longitude": 77.7281,
        "aliases": [
            "ktpo",
            "ktpo whitefield",
            "karnataka trade promotion",
            "ktpo convention",
            "epip zone whitefield",
        ],
    },
    "koramangala_indoor": {
        "canonical_name": "Koramangala Indoor Stadium",
        "latitude": 12.9352,
        "longitude": 77.6245,
        "aliases": [
            "koramangala indoor",
            "koramangala stadium",
            "80 feet road koramangala",
            "koramangala club",
        ],
    },
    "indiranagar_club": {
        "canonical_name": "Indiranagar Club Grounds",
        "latitude": 12.9719,
        "longitude": 77.6412,
        "aliases": [
            "indiranagar club",
            "indiranagar 100ft road",
            "defense colony indiranagar",
            "hal 2nd stage",
        ],
    },
    "electronic_city_phase1": {
        "canonical_name": "Electronic City Phase 1 Convention Grounds",
        "latitude": 12.8452,
        "longitude": 77.6602,
        "aliases": [
            "electronic city",
            "electronic city phase 1",
            "infosys convention",
            "wipro park electronic city",
            "ecity",
        ],
    },
    "manpho_bellary": {
        "canonical_name": "Manpho Convention Centre",
        "latitude": 13.0458,
        "longitude": 77.6083,
        "aliases": [
            "manpho",
            "manpho convention",
            "manyata tech park convention",
            "nagavara ground",
        ],
    },
    "jayanthi_grama": {
        "canonical_name": "National College Grounds Basavanagudi",
        "latitude": 12.9421,
        "longitude": 77.5732,
        "aliases": [
            "national college ground",
            "national college basavanagudi",
            "basavanagudi grounds",
        ],
    },
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in kilometres."""
    r = 6371.0  # Earth's radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def normalize_venue_name(raw_name: str | None) -> tuple[str | None, float | None, float | None]:
    """Resolve venue name to canonical name and coordinates if matched against Bengaluru registry."""
    if not raw_name or not raw_name.strip():
        return None, None, None

    cleaned = re.sub(r"[^\w\s]", " ", raw_name.lower()).strip()

    for venue_id, info in BENGALURU_VENUES.items():
        for alias in info["aliases"]:
            if alias in cleaned or cleaned in alias:
                return info["canonical_name"], info["latitude"], info["longitude"]

    # Fallback to cleaned title case
    title_cased = " ".join(word.capitalize() for word in cleaned.split())
    return title_cased, None, None


def are_venues_compatible(
    venue_a: str | None,
    venue_b: str | None,
    lat_a: float | None = None,
    lon_a: float | None = None,
    lat_b: float | None = None,
    lon_b: float | None = None,
) -> tuple[bool, float]:
    """Check if two venues refer to the same location, returning (compatible, score)."""
    if not venue_a or not venue_b:
        # One venue is unknown; neutral compatibility
        return True, 0.5

    norm_a, canon_lat_a, canon_lon_a = normalize_venue_name(venue_a)
    norm_b, canon_lat_b, canon_lon_b = normalize_venue_name(venue_b)

    lat_a = lat_a or canon_lat_a
    lon_a = lon_a or canon_lon_a
    lat_b = lat_b or canon_lat_b
    lon_b = lon_b or canon_lon_b

    # Exact canonical match
    if norm_a and norm_b and norm_a.lower() == norm_b.lower():
        return True, 1.0

    # Coordinate distance match
    if lat_a is not None and lon_a is not None and lat_b is not None and lon_b is not None:
        dist = haversine_km(lat_a, lon_a, lat_b, lon_b)
        if dist <= 1.2:
            return True, 0.95
        if dist <= 3.5:
            return True, 0.70
        if dist > 8.0:
            # Different geographical areas of Bengaluru
            return False, 0.0

    # Substring / token overlap match
    tokens_a = set(norm_a.lower().split()) if norm_a else set()
    tokens_b = set(norm_b.lower().split()) if norm_b else set()
    stop = {"ground", "grounds", "stadium", "hall", "centre", "center", "convention", "bengaluru", "bangalore"}
    clean_a = tokens_a - stop
    clean_b = tokens_b - stop

    if clean_a and clean_b:
        jaccard = len(clean_a & clean_b) / len(clean_a | clean_b)
        if jaccard >= 0.5:
            return True, 0.85

    return False, 0.2
