"""Unit tests for TreatmentClassifier enhancements."""

import pytest
from app.analysis.treatment_classifier import TreatmentClassifier, TreatmentType

@pytest.fixture
def classifier():
    return TreatmentClassifier()

def test_expanded_negative_signals(classifier):
    """Test new negative signal patterns."""
    text = "The court declined to follow the reasoning in Roe."
    signals = classifier.extract_signals(text, "Roe")
    assert len(signals) > 0
    assert signals[0].signal == "declined to follow"
    assert signals[0].treatment_type == TreatmentType.NEGATIVE

    text = "We disagreed with the holding in Roe."
    signals = classifier.extract_signals(text, "Roe")
    assert len(signals) > 0
    assert signals[0].signal == "disagreed with"

def test_expanded_positive_signals(classifier):
    """Test new positive signal patterns."""
    text = "This court cited with approval the decision in Roe."
    signals = classifier.extract_signals(text, "Roe")
    assert len(signals) > 0
    assert signals[0].signal == "cited with approval"
    assert signals[0].treatment_type == TreatmentType.POSITIVE

    text = "We harmonized our decision with Roe."
    signals = classifier.extract_signals(text, "Roe")
    assert len(signals) > 0
    assert signals[0].signal == "harmonized"

def test_negation_handling(classifier):
    """Test generic negation handling."""
    # "did not overrule" should NOT be a negative signal
    text = "We did not overrule Roe v. Wade."
    signals = classifier.extract_signals(text, "Roe")
    # Should find NO signals (as "overrule" is negated)
    assert len(signals) == 0

    # "declined to overrule"
    text = "The court declined to overrule the precedent."
    signals = classifier.extract_signals(text, "precedent")
    assert len(signals) == 0

    # "not overruled"
    text = "Roe was not overruled by Casey."
    signals = classifier.extract_signals(text, "Roe")
    assert len(signals) == 0

    # Positive check: "overruled" without negation should still work
    text = "Roe was overruled by Dobbs."
    signals = classifier.extract_signals(text, "Roe")
    assert len(signals) == 1
    assert signals[0].signal == "overruled"

def test_court_hierarchy_weighting(classifier):
    """Test court hierarchy weighting."""
    # SCOTUS (weight 1.0)
    scotus_case = {"court": "scotus", "caseName": "Test Case"}
    signals = [
        # Create a dummy signal
        type("Signal", (), {"signal": "overruled", "treatment_type": TreatmentType.NEGATIVE})()
    ]
    # Mock extract_signals to return our dummy signal
    # But wait, classify_treatment calls extract_signals internally.
    # We can test _aggregate_signals directly or mock extract_signals.
    # Let's test _aggregate_signals directly as we modified it.
    
    # We need real TreatmentSignal objects
    from app.analysis.treatment_classifier import TreatmentSignal
    
    signal = TreatmentSignal(
        signal="overruled",
        treatment_type=TreatmentType.NEGATIVE,
        position=0,
        context=""
    )
    
    # SCOTUS: 1.0 * 1.0 = 1.0
    type_, conf = classifier._aggregate_signals([signal], court_weight=1.0)
    assert conf == 1.0

    # Circuit Court: 1.0 * 0.8 = 0.8
    type_, conf = classifier._aggregate_signals([signal], court_weight=0.8)
    assert conf == 0.8

    # District Court: 1.0 * 0.6 = 0.6
    type_, conf = classifier._aggregate_signals([signal], court_weight=0.6)
    assert conf == 0.6

def test_distinguished_weight(classifier):
    """Test refined weight for 'distinguished'."""
    text = "The case is distinguished from the present one."
    signals = classifier.extract_signals(text, "case")
    assert len(signals) > 0
    assert signals[0].signal == "distinguished"
    
    # Check weight in _aggregate_signals
    type_, conf = classifier._aggregate_signals(signals)
    assert conf == 0.4  # Should be 0.4 now
