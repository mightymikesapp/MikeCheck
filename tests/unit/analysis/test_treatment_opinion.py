from app.analysis.treatment_classifier import TreatmentClassifier, TreatmentType
from app.types import CourtListenerCase


def test_classify_treatment_majority_negative():
    classifier = TreatmentClassifier()
    case = CourtListenerCase(
        caseName="Citing Case",
        opinions=[{"type": "010combined", "snippet": "We overruled [123 U.S. 456]."}],
    )
    result = classifier.classify_treatment(case, "123 U.S. 456")
    assert result.treatment_type == TreatmentType.NEGATIVE
    assert result.treatment_context == "majority_negative"


def test_classify_treatment_dissent_negative_only():
    classifier = TreatmentClassifier()
    # Majority follows, Dissent overrules
    case = CourtListenerCase(
        caseName="Citing Case",
        opinions=[
            {"type": "010combined", "snippet": "We followed [123 U.S. 456]."},
            {"type": "040dissent", "snippet": "I would have overruled [123 U.S. 456]."},
        ],
    )
    result = classifier.classify_treatment(case, "123 U.S. 456")

    # Check context
    assert result.treatment_context == "majority_positive_dissent_negative"
    assert result.treatment_type == TreatmentType.POSITIVE
    assert result.opinion_breakdown["majority"] == TreatmentType.POSITIVE
    assert result.opinion_breakdown["dissent"] == TreatmentType.NEGATIVE


def test_classify_treatment_dissent_negative_neutral_majority():
    classifier = TreatmentClassifier()
    # Majority neutral (no signal), Dissent overrules
    case = CourtListenerCase(
        caseName="Citing Case",
        opinions=[
            {"type": "010combined", "snippet": "We discuss [123 U.S. 456]."},
            {"type": "040dissent", "snippet": "I would have overruled [123 U.S. 456]."},
        ],
    )
    result = classifier.classify_treatment(case, "123 U.S. 456")

    # Logic: Dissent negative -> final treatment negative (reduced confidence)
    assert result.treatment_context == "dissent_negative_only"
    assert result.treatment_type == TreatmentType.NEGATIVE
    assert result.confidence < 0.6  # reduced
