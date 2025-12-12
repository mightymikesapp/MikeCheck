"""Unit tests for treatment analysis tools."""

from unittest.mock import MagicMock

import pytest

from app.analysis.treatment_classifier import TreatmentType
from app.tools.treatment import (
    _coerce_cases,
    _coerce_failed_requests,
    _coerce_incomplete_flag,
    _coerce_warnings,
    check_case_validity_impl,
    get_citing_cases_impl,
)


# Test helper/coercion functions
@pytest.mark.unit
def test_coerce_failed_requests_with_list():
    """Test coercing failed requests from list of dicts."""
    raw = [{"error": "timeout"}, {"error": "not found"}]
    result = _coerce_failed_requests(raw)
    assert len(result) == 2
    assert result[0]["error"] == "timeout"


@pytest.mark.unit
def test_coerce_failed_requests_with_non_dict_entries():
    """Test coercing failed requests filters out non-dicts."""
    raw = [{"error": "timeout"}, "invalid", None, {"error": "not found"}]
    result = _coerce_failed_requests(raw)
    assert len(result) == 2
    assert all(isinstance(item, dict) for item in result)


@pytest.mark.unit
def test_coerce_failed_requests_with_non_list():
    """Test coercing failed requests with non-list input."""
    assert _coerce_failed_requests(None) == []
    assert _coerce_failed_requests("string") == []
    assert _coerce_failed_requests(123) == []


@pytest.mark.unit
def test_coerce_warnings_with_strings():
    """Test coercing warnings from list of strings."""
    raw = ["warning 1", "warning 2"]
    result = _coerce_warnings(raw)
    assert len(result) == 2
    assert result[0] == "warning 1"


@pytest.mark.unit
def test_coerce_warnings_with_dicts():
    """Test coercing warnings from list of dicts."""
    raw = [
        {"signal": "overruled", "case_name": "Test Case"},
        {"signal": "questioned", "case_name": "Another Case"},
    ]
    result = _coerce_warnings(raw)
    assert len(result) == 2
    assert result[0]["signal"] == "overruled"


@pytest.mark.unit
def test_coerce_warnings_with_mixed_types():
    """Test coercing warnings with mixed string and dict entries."""
    raw = ["simple warning", {"signal": "overruled", "case_name": "Test Case"}, "another warning"]
    result = _coerce_warnings(raw)
    assert len(result) == 3
    assert isinstance(result[0], str)
    assert isinstance(result[1], dict)


@pytest.mark.unit
def test_coerce_warnings_with_non_list():
    """Test coercing warnings with non-list input."""
    assert _coerce_warnings(None) == []
    assert _coerce_warnings("string") == []
    assert _coerce_warnings(123) == []


@pytest.mark.unit
def test_coerce_incomplete_flag_true():
    """Test coercing incomplete flag with True value."""
    assert _coerce_incomplete_flag(True) is True


@pytest.mark.unit
def test_coerce_incomplete_flag_false():
    """Test coercing incomplete flag with False value."""
    assert _coerce_incomplete_flag(False) is False


@pytest.mark.unit
def test_coerce_incomplete_flag_other_values():
    """Test coercing incomplete flag with non-boolean values."""
    assert _coerce_incomplete_flag(None) is False
    assert _coerce_incomplete_flag("true") is False
    assert _coerce_incomplete_flag(1) is False
    assert _coerce_incomplete_flag([]) is False


@pytest.mark.unit
def test_coerce_cases_with_valid_dicts():
    """Test coercing cases from list of dicts."""
    raw = [
        {"caseName": "Case 1", "citation": ["123 U.S. 456"]},
        {"caseName": "Case 2", "citation": ["789 U.S. 012"]},
    ]
    result = _coerce_cases(raw)
    assert len(result) == 2
    assert result[0]["caseName"] == "Case 1"


@pytest.mark.unit
def test_coerce_cases_filters_non_dicts():
    """Test coercing cases filters out non-dict entries."""
    raw = [{"caseName": "Case 1"}, "invalid", None, 123, {"caseName": "Case 2"}]
    result = _coerce_cases(raw)
    assert len(result) == 2
    assert all(isinstance(case, dict) for case in result)


@pytest.mark.unit
def test_coerce_cases_empty_list():
    """Test coercing cases with empty list."""
    assert _coerce_cases([]) == []


# Test check_case_validity_impl
@pytest.mark.unit
async def test_check_case_validity_impl_case_not_found(mock_client):
    """Test check_case_validity when case lookup fails."""
    mock_client.lookup_citation.return_value = {"error": "Case not found"}

    result = await check_case_validity_impl("999 U.S. 999")

    assert "error" in result
    assert "Could not find case" in result["error"]
    assert result["citation"] == "999 U.S. 999"


@pytest.mark.unit
async def test_check_case_validity_impl_no_citing_cases(mock_client):
    """Test check_case_validity when no citing cases are found."""
    mock_client.lookup_citation.return_value = {
        "caseName": "Test Case",
        "citation": ["123 U.S. 456"],
    }
    mock_client.find_citing_cases.return_value = {
        "results": [],
        "warnings": [],
        "failed_requests": [],
        "incomplete_data": False,
    }

    result = await check_case_validity_impl("123 U.S. 456")

    assert result["is_good_law"] is True
    assert result["confidence"] == 0.5
    assert result["total_citing_cases"] == 0
    assert "No citing cases found" in result["summary"]


@pytest.mark.unit
async def test_check_case_validity_impl_unexpected_response_format(mock_client):
    """Test check_case_validity when API returns unexpected format."""
    mock_client.lookup_citation.return_value = {
        "caseName": "Test Case",
        "citation": ["123 U.S. 456"],
    }
    mock_client.find_citing_cases.return_value = {
        "results": "not a list",  # Invalid format
        "warnings": [],
    }

    result = await check_case_validity_impl("123 U.S. 456")

    assert "error" in result
    assert "Unexpected response format" in result["error"]
    assert result["incomplete_data"] is True


@pytest.mark.unit
async def test_check_case_validity_impl_with_positive_treatment(mock_client, mocker):
    """Test check_case_validity with positive treatment signals."""
    mock_client.lookup_citation.return_value = {
        "caseName": "Test Case",
        "citation": ["123 U.S. 456"],
    }

    citing_case = {
        "caseName": "Citing Case",
        "citation": ["789 U.S. 012"],
        "dateFiled": "2020-01-15",
        "opinions": [{"id": 111}],
    }

    mock_client.find_citing_cases.return_value = {
        "results": [citing_case],
        "warnings": [],
        "failed_requests": [],
        "incomplete_data": False,
    }

    # Mock the classifier
    mock_treatment = MagicMock()
    mock_treatment.treatment_type = TreatmentType.POSITIVE
    mock_treatment.confidence = 0.9
    mock_treatment.signals_found = []
    mock_treatment.excerpt = "This case followed the precedent."
    mock_treatment.case_name = "Citing Case"
    mock_treatment.citation = "789 U.S. 012"
    mock_treatment.date_filed = "2020-01-15"

    mock_classifier = mocker.patch("app.tools.treatment.classifier")
    mock_classifier.classify_treatment.return_value = mock_treatment
    mock_classifier.should_fetch_full_text.return_value = False

    mock_aggregated = MagicMock()
    mock_aggregated.is_good_law = True
    mock_aggregated.confidence = 0.9
    mock_aggregated.summary = "Case is good law"
    mock_aggregated.total_citing_cases = 1
    mock_aggregated.positive_count = 1
    mock_aggregated.negative_count = 0
    mock_aggregated.neutral_count = 0
    mock_aggregated.unknown_count = 0
    mock_aggregated.negative_treatments = []

    mock_classifier.aggregate_treatments.return_value = mock_aggregated

    result = await check_case_validity_impl("123 U.S. 456")

    assert result["is_good_law"] is True
    assert result["confidence"] == 0.9
    assert result["positive_count"] == 1
    assert result["negative_count"] == 0
    assert "Case appears reliable" in result["recommendation"]


@pytest.mark.unit
async def test_check_case_validity_impl_with_negative_treatment(mock_client, mocker):
    """Test check_case_validity with negative treatment signals."""
    mock_client.lookup_citation.return_value = {
        "caseName": "Test Case",
        "citation": ["123 U.S. 456"],
    }

    citing_case = {
        "caseName": "Overruling Case",
        "citation": ["999 U.S. 111"],
        "dateFiled": "2023-06-01",
        "opinions": [{"id": 222}],
    }

    mock_client.find_citing_cases.return_value = {
        "results": [citing_case],
        "warnings": [],
        "failed_requests": [],
        "incomplete_data": False,
    }

    # Mock the classifier
    mock_signal = MagicMock()
    mock_signal.signal = "overruled"
    mock_signal.context = "This case was explicitly overruled."

    mock_treatment = MagicMock()
    mock_treatment.treatment_type = TreatmentType.NEGATIVE
    mock_treatment.confidence = 0.95
    mock_treatment.signals_found = [mock_signal]
    mock_treatment.excerpt = "This case was explicitly overruled."
    mock_treatment.case_name = "Overruling Case"
    mock_treatment.citation = "999 U.S. 111"
    mock_treatment.date_filed = "2023-06-01"

    mock_classifier = mocker.patch("app.tools.treatment.classifier")
    mock_classifier.classify_treatment.return_value = mock_treatment
    mock_classifier.should_fetch_full_text.return_value = False

    mock_aggregated = MagicMock()
    mock_aggregated.is_good_law = False
    mock_aggregated.confidence = 0.95
    mock_aggregated.summary = "Case overruled"
    mock_aggregated.total_citing_cases = 1
    mock_aggregated.positive_count = 0
    mock_aggregated.negative_count = 1
    mock_aggregated.neutral_count = 0
    mock_aggregated.unknown_count = 0
    mock_aggregated.negative_treatments = [mock_treatment]

    mock_classifier.aggregate_treatments.return_value = mock_aggregated

    result = await check_case_validity_impl("123 U.S. 456")

    assert result["is_good_law"] is False
    assert result["negative_count"] == 1
    assert "Manual review recommended" in result["recommendation"]
    assert len(result["warnings"]) > 0


@pytest.mark.unit
async def test_check_case_validity_impl_with_incomplete_data(mock_client, mocker):
    """Test check_case_validity with incomplete data adjusts confidence."""
    mock_client.lookup_citation.return_value = {
        "caseName": "Test Case",
        "citation": ["123 U.S. 456"],
    }

    citing_case = {
        "caseName": "Citing Case",
        "citation": ["789 U.S. 012"],
        "dateFiled": "2020-01-15",
        "opinions": [{"id": 111}],
    }

    mock_client.find_citing_cases.return_value = {
        "results": [citing_case],
        "warnings": ["Some data unavailable"],
        "failed_requests": [{"url": "/api/endpoint", "error": "timeout"}],
        "incomplete_data": True,
    }

    # Mock the classifier
    mock_treatment = MagicMock()
    mock_treatment.treatment_type = TreatmentType.POSITIVE
    mock_treatment.confidence = 0.9
    mock_treatment.signals_found = []
    mock_treatment.excerpt = "This case followed the precedent."
    mock_treatment.case_name = "Citing Case"
    mock_treatment.citation = "789 U.S. 012"
    mock_treatment.date_filed = "2020-01-15"

    mock_classifier = mocker.patch("app.tools.treatment.classifier")
    mock_classifier.classify_treatment.return_value = mock_treatment
    mock_classifier.should_fetch_full_text.return_value = False

    mock_aggregated = MagicMock()
    mock_aggregated.is_good_law = True
    mock_aggregated.confidence = 0.9
    mock_aggregated.summary = "Case is good law"
    mock_aggregated.total_citing_cases = 1
    mock_aggregated.positive_count = 1
    mock_aggregated.negative_count = 0
    mock_aggregated.neutral_count = 0
    mock_aggregated.unknown_count = 0
    mock_aggregated.negative_treatments = []

    mock_classifier.aggregate_treatments.return_value = mock_aggregated

    result = await check_case_validity_impl("123 U.S. 456")

    assert result["incomplete_data"] is True
    assert result["confidence"] < 0.9  # Confidence should be reduced (0.9 * 0.8 = 0.72)
    assert len(result["failed_requests"]) == 1
    assert len(result["warnings"]) >= 1


# Test get_citing_cases_impl
@pytest.mark.unit
async def test_get_citing_cases_impl_basic(mock_client, mocker):
    """Test get_citing_cases basic functionality."""
    citing_case = {
        "caseName": "Citing Case",
        "citation": ["789 U.S. 012"],
        "dateFiled": "2020-01-15",
        "opinions": [{"id": 111}],
    }

    mock_client.find_citing_cases.return_value = {
        "results": [citing_case],
        "warnings": [],
        "failed_requests": [],
        "incomplete_data": False,
    }

    # Mock the classifier
    mock_treatment = MagicMock()
    mock_treatment.treatment_type = TreatmentType.POSITIVE
    mock_treatment.confidence = 0.85
    mock_treatment.signals_found = [MagicMock(signal="followed")]
    mock_treatment.excerpt = "This case followed the precedent."
    mock_treatment.case_name = "Citing Case"
    mock_treatment.citation = "789 U.S. 012"
    mock_treatment.date_filed = "2020-01-15"

    mock_classifier = mocker.patch("app.tools.treatment.classifier")
    mock_classifier.classify_treatment.return_value = mock_treatment

    result = await get_citing_cases_impl("123 U.S. 456")

    assert result["citation"] == "123 U.S. 456"
    assert result["total_found"] == 1
    assert len(result["citing_cases"]) == 1
    assert result["citing_cases"][0]["case_name"] == "Citing Case"
    assert result["citing_cases"][0]["treatment"] == "positive"


@pytest.mark.unit
async def test_get_citing_cases_impl_with_filter(mock_client, mocker):
    """Test get_citing_cases with treatment filter."""
    positive_case = {
        "caseName": "Positive Case",
        "citation": ["111 U.S. 111"],
        "dateFiled": "2020-01-15",
        "opinions": [{"id": 111}],
    }

    negative_case = {
        "caseName": "Negative Case",
        "citation": ["222 U.S. 222"],
        "dateFiled": "2021-06-01",
        "opinions": [{"id": 222}],
    }

    mock_client.find_citing_cases.return_value = {
        "results": [positive_case, negative_case],
        "warnings": [],
        "failed_requests": [],
        "incomplete_data": False,
    }

    # Mock the classifier to return different treatments
    mock_positive_treatment = MagicMock()
    mock_positive_treatment.treatment_type = TreatmentType.POSITIVE
    mock_positive_treatment.confidence = 0.85
    mock_positive_treatment.signals_found = [MagicMock(signal="followed")]
    mock_positive_treatment.excerpt = "Followed."
    mock_positive_treatment.case_name = "Positive Case"
    mock_positive_treatment.citation = "111 U.S. 111"
    mock_positive_treatment.date_filed = "2020-01-15"

    mock_negative_treatment = MagicMock()
    mock_negative_treatment.treatment_type = TreatmentType.NEGATIVE
    mock_negative_treatment.confidence = 0.90
    mock_negative_treatment.signals_found = [MagicMock(signal="overruled")]
    mock_negative_treatment.excerpt = "Overruled."
    mock_negative_treatment.case_name = "Negative Case"
    mock_negative_treatment.citation = "222 U.S. 222"
    mock_negative_treatment.date_filed = "2021-06-01"

    mock_classifier = mocker.patch("app.tools.treatment.classifier")
    mock_classifier.classify_treatment.side_effect = [
        mock_positive_treatment,
        mock_negative_treatment,
    ]

    # Filter for negative only
    result = await get_citing_cases_impl("123 U.S. 456", treatment_filter="negative")

    assert result["total_found"] == 2
    assert len(result["citing_cases"]) == 1
    assert result["citing_cases"][0]["case_name"] == "Negative Case"
    assert result["filter_applied"] == "negative"


@pytest.mark.unit
async def test_get_citing_cases_impl_unexpected_response_format(mock_client):
    """Test get_citing_cases with unexpected response format."""
    mock_client.find_citing_cases.return_value = {
        "results": "not a list",  # Invalid format
        "warnings": [],
    }

    result = await get_citing_cases_impl("123 U.S. 456")

    assert result["total_found"] == 0
    assert len(result["citing_cases"]) == 0
    assert result["incomplete_data"] is True


@pytest.mark.unit
async def test_get_citing_cases_impl_with_limit(mock_client):
    """Test get_citing_cases respects limit parameter."""
    mock_client.find_citing_cases.return_value = {
        "results": [],
        "warnings": [],
        "failed_requests": [],
        "incomplete_data": False,
    }

    await get_citing_cases_impl("123 U.S. 456", limit=50)

    mock_client.find_citing_cases.assert_called_once()
    call_args = mock_client.find_citing_cases.call_args
    assert call_args[1]["limit"] == 50
