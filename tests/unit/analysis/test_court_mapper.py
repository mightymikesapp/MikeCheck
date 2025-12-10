"""Tests for the court level mapper."""

import pytest

from app.analysis.court_mapper import CourtLevel, get_court_level


@pytest.mark.parametrize(
    "court_id,expected",
    [
        ("scotus", CourtLevel.SCOTUS),
        ("SCOTUS", CourtLevel.SCOTUS),
        ("ca1", CourtLevel.CIRCUIT),
        ("ca9", CourtLevel.CIRCUIT),
        ("ca11", CourtLevel.CIRCUIT),
        ("cadc", CourtLevel.CIRCUIT),
        ("cafc", CourtLevel.CIRCUIT),
        ("dcd", CourtLevel.DISTRICT),
        ("sdny", CourtLevel.DISTRICT),
        ("ndca", CourtLevel.DISTRICT),
        ("dma", CourtLevel.DISTRICT),
        ("ny", CourtLevel.STATE),
        ("tx", CourtLevel.STATE),
        ("casup", CourtLevel.STATE),
        ("unknown_court_id", CourtLevel.UNKNOWN),
        ("", CourtLevel.UNKNOWN),
        (None, CourtLevel.UNKNOWN),
    ],
)
def test_get_court_level(court_id, expected):
    """Test court ID mapping to hierarchy levels."""
    assert get_court_level(court_id) == expected
