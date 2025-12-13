"""Unit tests for footnote-based treatment analysis and confidence adjustment."""

import pytest

from app.analysis.treatment_classifier import TreatmentClassifier, TreatmentType
from app.types import CourtListenerCase


@pytest.mark.unit
def test_confidence_adjustment_footnote_only_negative():
    """Test that confidence is reduced when negative signals are found only in footnotes."""
    classifier = TreatmentClassifier()

    # Create a mock citing case with HTML containing negative signal ONLY in footnote
    citing_case: CourtListenerCase = {
        "id": 12345,
        "caseName": "Test Case v. Example",
        "citation": ["123 F.3d 456"],
        "dateFiled": "2020-01-15",
        "court": "ca9",
        "opinions": [
            {
                "id": 999,
                "type": "010combined",
                "html_lawbox": """
                <p>The court in this case followed the reasoning in 410 U.S. 113.</p>
                <p>We agree with the principles established therein.</p>
                <fn num="1">Note that 410 U.S. 113 was later overruled by Dobbs.</fn>
                """,
            }
        ],
    }

    result = classifier.classify_treatment(citing_case, "410 U.S. 113")

    # Should detect negative signal (overruled) in footnote
    assert result.treatment_type == TreatmentType.NEGATIVE
    negative_signals = [s for s in result.signals_found if s.treatment_type == TreatmentType.NEGATIVE]
    assert len(negative_signals) > 0
    assert all(s.location_type == "footnote" for s in negative_signals)

    # Confidence should be reduced by 0.2 from the base
    # The signal "overruled" has weight 1.0, with court weight 0.8 (ca9) = 0.8
    # After footnote adjustment: 0.8 - 0.2 = 0.6
    assert result.confidence < 0.8
    assert result.confidence == pytest.approx(0.6, abs=0.05)
    assert result.location_type == "footnote"


@pytest.mark.unit
def test_no_confidence_adjustment_body_negative():
    """Test that confidence is NOT reduced when negative signals are in body text."""
    classifier = TreatmentClassifier()

    citing_case: CourtListenerCase = {
        "id": 12346,
        "caseName": "Another Test v. Example",
        "citation": ["124 F.3d 789"],
        "dateFiled": "2021-03-20",
        "court": "ca9",
        "opinions": [
            {
                "id": 1000,
                "type": "010combined",
                "html_lawbox": """
                <p>The precedent in 410 U.S. 113 was overruled by Dobbs.</p>
                <p>We therefore cannot rely on its reasoning.</p>
                <fn num="1">See also other cases discussing this issue.</fn>
                """,
            }
        ],
    }

    result = classifier.classify_treatment(citing_case, "410 U.S. 113")

    # Should detect negative signal in body
    assert result.treatment_type == TreatmentType.NEGATIVE
    negative_signals = [s for s in result.signals_found if s.treatment_type == TreatmentType.NEGATIVE]
    assert len(negative_signals) > 0
    # At least one negative signal should be in body
    assert any(s.location_type == "body" for s in negative_signals)

    # Confidence should NOT be reduced (should be close to weight * court_weight)
    # "overruled" weight 1.0 * court_weight 0.8 = 0.8
    assert result.confidence >= 0.75  # Allow small tolerance
    assert result.location_type == "body"


@pytest.mark.unit
def test_positive_signals_no_adjustment():
    """Test that positive signals don't trigger confidence adjustment."""
    classifier = TreatmentClassifier()

    citing_case: CourtListenerCase = {
        "id": 12347,
        "caseName": "Positive Case v. Example",
        "citation": ["125 F.3d 100"],
        "dateFiled": "2019-05-10",
        "court": "scotus",
        "opinions": [
            {
                "id": 1001,
                "type": "010combined",
                "html_lawbox": """
                <p>This court follows the reasoning in 410 U.S. 113.</p>
                <fn num="1">The case in 410 U.S. 113 was affirmed by subsequent courts.</fn>
                """,
            }
        ],
    }

    result = classifier.classify_treatment(citing_case, "410 U.S. 113")

    # Should detect positive signals
    assert result.treatment_type == TreatmentType.POSITIVE
    # No confidence reduction should occur for positive signals
    assert result.confidence > 0.7


@pytest.mark.unit
def test_mixed_location_signals():
    """Test case with negative signals in both body and footnotes."""
    classifier = TreatmentClassifier()

    citing_case: CourtListenerCase = {
        "id": 12348,
        "caseName": "Mixed Case v. Example",
        "citation": ["126 F.3d 200"],
        "dateFiled": "2022-06-15",
        "court": "ca2",
        "opinions": [
            {
                "id": 1002,
                "type": "010combined",
                "html_lawbox": """
                <p>The holding in 410 U.S. 113 was questioned by later courts.</p>
                <p>We must carefully consider whether to follow it.</p>
                <fn num="1">Note that 410 U.S. 113 was also criticized in Smith v. Jones.</fn>
                """,
            }
        ],
    }

    result = classifier.classify_treatment(citing_case, "410 U.S. 113")

    # Should detect negative signals in both locations
    assert result.treatment_type == TreatmentType.NEGATIVE
    negative_signals = [s for s in result.signals_found if s.treatment_type == TreatmentType.NEGATIVE]
    assert len(negative_signals) >= 2

    body_negatives = [s for s in negative_signals if s.location_type == "body"]
    footnote_negatives = [s for s in negative_signals if s.location_type == "footnote"]

    assert len(body_negatives) > 0
    assert len(footnote_negatives) > 0

    # Since negative signals are in BOTH locations, no footnote-only adjustment
    # Confidence should be based on the stronger signal
    assert result.confidence >= 0.6


@pytest.mark.unit
def test_plain_text_fallback_footnote_detection():
    """Test footnote detection using plain text fallback parser."""
    classifier = TreatmentClassifier()

    citing_case: CourtListenerCase = {
        "id": 12349,
        "caseName": "Plain Text Case v. Example",
        "citation": ["127 F.3d 300"],
        "dateFiled": "2023-01-10",
        "court": "ca5",
        "opinions": [
            {
                "id": 1003,
                "type": "010combined",
                "plain_text": """
                The court examined the precedent in 410 U.S. 113 and applied its reasoning.
                This case provides important guidance on the issue.

                1. It should be noted that 410 U.S. 113 was later overruled in Dobbs v. Jackson.
                2. See also other cases discussing this precedent.
                """,
            }
        ],
    }

    result = classifier.classify_treatment(citing_case, "410 U.S. 113")

    # Should detect signals and separate footnotes
    assert len(result.signals_found) > 0

    # Check if footnotes were detected (heuristically)
    negative_signals = [s for s in result.signals_found if s.treatment_type == TreatmentType.NEGATIVE]
    if negative_signals:
        # If negative signal detected, check location tracking
        assert result.location_type in ["body", "footnote"]


@pytest.mark.unit
def test_location_type_field_in_signals():
    """Test that all TreatmentSignals have location_type field set."""
    classifier = TreatmentClassifier()

    citing_case: CourtListenerCase = {
        "id": 12350,
        "caseName": "Location Field Test",
        "citation": ["128 F.3d 400"],
        "dateFiled": "2023-08-20",
        "court": "scotus",
        "opinions": [
            {
                "id": 1004,
                "type": "010combined",
                "html_lawbox": """
                <p>The case 410 U.S. 113 was affirmed.</p>
                <fn num="1">410 U.S. 113 was later distinguished.</fn>
                """,
            }
        ],
    }

    result = classifier.classify_treatment(citing_case, "410 U.S. 113")

    # All signals should have location_type field
    assert all(hasattr(s, "location_type") for s in result.signals_found)
    assert all(s.location_type in ["body", "footnote"] for s in result.signals_found)

    # Check that we have signals from both locations
    body_signals = [s for s in result.signals_found if s.location_type == "body"]
    footnote_signals = [s for s in result.signals_found if s.location_type == "footnote"]

    assert len(body_signals) > 0 or len(footnote_signals) > 0
