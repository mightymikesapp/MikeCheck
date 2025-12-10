"""Court hierarchy mapping for visualization.

This module provides heuristics to map CourtListener court IDs
to simplified hierarchical levels (SCOTUS, Circuit, District, State).
"""

# Standard library imports
import re
from enum import Enum


class CourtLevel(str, Enum):
    """Hierarchical levels of US courts."""
    SCOTUS = "scotus"
    CIRCUIT = "circuit"
    DISTRICT = "district"
    STATE = "state"
    UNKNOWN = "unknown"

def get_court_level(court_id: str | None) -> CourtLevel:
    """Map a court ID string to a simplified hierarchy level.

    Args:
        court_id: The CourtListener court identifier (e.g., "scotus", "ca9", "dcd")

    Returns:
        CourtLevel enum value
    """
    if not court_id:
        return CourtLevel.UNKNOWN

    court = court_id.lower().strip()

    # Supreme Court
    if court == "scotus":
        return CourtLevel.SCOTUS

    # Federal Circuit Courts
    # Matches: ca1-ca11, cadc, cafc
    if re.match(r"^ca(\d+|dc|fc)$", court):
        return CourtLevel.CIRCUIT

    # Federal District Courts
    # Matches: dcd, cdca, sdny, etc. (often ends in 'd' or matches specific patterns)
    # Common pattern: ?d?? (e.g. ndca) or d?? (e.g. dcd)
    # Also includes territorial district courts
    if (
        re.match(r"^[nswem]?d[a-z]{2}$", court) or  # ndca, sdny, edva, wdwa, mdfl
        re.match(r"^d[a-z]{2}$", court) or          # dcd, dma, dnv
        court in {"dct", "jpml", "cit", "uscfc"}    # Special federal courts often grouped with district level
    ):
        return CourtLevel.DISTRICT

    # State Courts
    # Usually just 2 letter state code, or state code + suffix
    # This is a broad catch-all for remaining valid-looking codes
    if len(court) == 2 and court.isalpha():
        return CourtLevel.STATE
    if len(court) > 2 and court[:2].isalpha() and (court.endswith("sup") or court.endswith("app")):
        return CourtLevel.STATE

    # Fallback
    return CourtLevel.UNKNOWN
