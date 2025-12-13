"""Unit tests for jurisdiction analysis tools."""

import pytest

from app.analysis.circuit_analyzer import CircuitAnalyzer, TreatmentType
from app.analysis.treatment_classifier import TreatmentAnalysis
from app.tools.jurisdiction import find_circuit_splits_impl


@pytest.mark.unit
class TestCircuitAnalyzer:
    """Test suite for CircuitAnalyzer class."""

    def test_extract_circuit_id_valid_circuits(self):
        """Test extraction of valid circuit IDs."""
        analyzer = CircuitAnalyzer()

        # Standard circuit formats
        assert analyzer._extract_circuit_id("ca9") == "ca9"
        assert analyzer._extract_circuit_id("ca1") == "ca1"
        assert analyzer._extract_circuit_id("ca11") == "ca11"
        assert analyzer._extract_circuit_id("cadc") == "cadc"
        assert analyzer._extract_circuit_id("cafc") == "cafc"

        # Case insensitive
        assert analyzer._extract_circuit_id("CA9") == "ca9"
        assert analyzer._extract_circuit_id("CaDC") == "cadc"

        # With variations
        assert analyzer._extract_circuit_id("ca9-1") == "ca9"
        assert analyzer._extract_circuit_id("ca9.2") == "ca9"

    def test_extract_circuit_id_invalid(self):
        """Test extraction returns None for non-circuit courts."""
        analyzer = CircuitAnalyzer()

        # Supreme Court
        assert analyzer._extract_circuit_id("scotus") is None

        # District courts
        assert analyzer._extract_circuit_id("cacd") is None  # Central District of CA
        assert analyzer._extract_circuit_id("nysd") is None  # Southern District of NY

        # State courts
        assert analyzer._extract_circuit_id("cal") is None

        # Invalid
        assert analyzer._extract_circuit_id("") is None
        assert analyzer._extract_circuit_id(None) is None

    def test_group_by_circuit(self):
        """Test grouping cases by circuit."""
        analyzer = CircuitAnalyzer()

        # Create test cases
        cases = [
            {"id": 1, "court": "ca9", "caseName": "Case 1"},
            {"id": 2, "court": "ca9", "caseName": "Case 2"},
            {"id": 3, "court": "ca5", "caseName": "Case 3"},
            {"id": 4, "court": "scotus", "caseName": "Case 4"},  # Not a circuit
        ]

        # Create matching treatments
        treatments = [
            TreatmentAnalysis(
                case_name="Case 1",
                case_id="1",
                citation="1 F.3d 1",
                treatment_type=TreatmentType.POSITIVE,
                confidence=0.8,
                signals_found=[],
                excerpt="",
            ),
            TreatmentAnalysis(
                case_name="Case 2",
                case_id="2",
                citation="2 F.3d 2",
                treatment_type=TreatmentType.POSITIVE,
                confidence=0.9,
                signals_found=[],
                excerpt="",
            ),
            TreatmentAnalysis(
                case_name="Case 3",
                case_id="3",
                citation="3 F.3d 3",
                treatment_type=TreatmentType.NEGATIVE,
                confidence=0.7,
                signals_found=[],
                excerpt="",
            ),
            TreatmentAnalysis(
                case_name="Case 4",
                case_id="4",
                citation="4 U.S. 4",
                treatment_type=TreatmentType.NEUTRAL,
                confidence=0.5,
                signals_found=[],
                excerpt="",
            ),
        ]

        groups = analyzer._group_by_circuit(cases, treatments)

        # Should have 2 circuit groups (ca9 and ca5)
        assert len(groups) == 2
        assert "ca9" in groups
        assert "ca5" in groups
        assert len(groups["ca9"]) == 2
        assert len(groups["ca5"]) == 1

    def test_analyze_circuit_treatment_positive_dominant(self):
        """Test analysis when circuit has dominant positive treatment."""
        analyzer = CircuitAnalyzer(split_threshold=0.6)

        treatments = [
            TreatmentAnalysis(
                case_name="Case 1",
                case_id="1",
                citation="1 F.3d 1",
                treatment_type=TreatmentType.POSITIVE,
                confidence=0.9,
                signals_found=[],
                excerpt="followed the holding",
            ),
            TreatmentAnalysis(
                case_name="Case 2",
                case_id="2",
                citation="2 F.3d 2",
                treatment_type=TreatmentType.POSITIVE,
                confidence=0.8,
                signals_found=[],
                excerpt="affirmed the rule",
            ),
            TreatmentAnalysis(
                case_name="Case 3",
                case_id="3",
                citation="3 F.3d 3",
                treatment_type=TreatmentType.NEUTRAL,
                confidence=0.5,
                signals_found=[],
                excerpt="cited without comment",
            ),
        ]

        result = analyzer._analyze_circuit_treatment("ca9", treatments)

        assert result.circuit_id == "ca9"
        assert result.circuit_name == "Ninth Circuit"
        assert result.total_cases == 3
        assert result.positive_count == 2
        assert result.negative_count == 0
        assert result.neutral_count == 1
        # 2/3 = 66.7% > 60% threshold, so positive is dominant
        assert result.dominant_treatment == TreatmentType.POSITIVE
        assert len(result.representative_cases) == 3
        assert result.average_confidence > 0.5

    def test_analyze_circuit_treatment_negative_dominant(self):
        """Test analysis when circuit has dominant negative treatment."""
        analyzer = CircuitAnalyzer(split_threshold=0.6)

        treatments = [
            TreatmentAnalysis(
                case_name="Case 1",
                case_id="1",
                citation="1 F.3d 1",
                treatment_type=TreatmentType.NEGATIVE,
                confidence=0.9,
                signals_found=[],
                excerpt="overruled",
            ),
            TreatmentAnalysis(
                case_name="Case 2",
                case_id="2",
                citation="2 F.3d 2",
                treatment_type=TreatmentType.NEGATIVE,
                confidence=0.8,
                signals_found=[],
                excerpt="criticized",
            ),
        ]

        result = analyzer._analyze_circuit_treatment("ca5", treatments)

        assert result.dominant_treatment == TreatmentType.NEGATIVE
        assert result.negative_count == 2

    def test_detect_split_type_direct_conflict(self):
        """Test detection of direct circuit split (positive vs negative)."""
        analyzer = CircuitAnalyzer()

        circuit_treatments = {
            "ca9": analyzer._analyze_circuit_treatment(
                "ca9",
                [
                    TreatmentAnalysis(
                        case_name="Case 1",
                        case_id="1",
                        citation="1 F.3d 1",
                        treatment_type=TreatmentType.POSITIVE,
                        confidence=0.9,
                        signals_found=[],
                        excerpt="",
                    ),
                    TreatmentAnalysis(
                        case_name="Case 2",
                        case_id="2",
                        citation="2 F.3d 2",
                        treatment_type=TreatmentType.POSITIVE,
                        confidence=0.8,
                        signals_found=[],
                        excerpt="",
                    ),
                ],
            ),
            "ca5": analyzer._analyze_circuit_treatment(
                "ca5",
                [
                    TreatmentAnalysis(
                        case_name="Case 3",
                        case_id="3",
                        citation="3 F.3d 3",
                        treatment_type=TreatmentType.NEGATIVE,
                        confidence=0.9,
                        signals_found=[],
                        excerpt="",
                    ),
                    TreatmentAnalysis(
                        case_name="Case 4",
                        case_id="4",
                        citation="4 F.3d 4",
                        treatment_type=TreatmentType.NEGATIVE,
                        confidence=0.8,
                        signals_found=[],
                        excerpt="",
                    ),
                ],
            ),
        }

        split_type, confidence, circuits = analyzer._detect_split_type(circuit_treatments)

        assert split_type == "direct_conflict"
        assert confidence >= 0.7
        assert "ca9" in circuits
        assert "ca5" in circuits

    def test_detect_split_type_no_split(self):
        """Test when no split is detected (all circuits agree)."""
        analyzer = CircuitAnalyzer()

        circuit_treatments = {
            "ca9": analyzer._analyze_circuit_treatment(
                "ca9",
                [
                    TreatmentAnalysis(
                        case_name="Case 1",
                        case_id="1",
                        citation="1 F.3d 1",
                        treatment_type=TreatmentType.POSITIVE,
                        confidence=0.9,
                        signals_found=[],
                        excerpt="",
                    ),
                ],
            ),
            "ca5": analyzer._analyze_circuit_treatment(
                "ca5",
                [
                    TreatmentAnalysis(
                        case_name="Case 2",
                        case_id="2",
                        citation="2 F.3d 2",
                        treatment_type=TreatmentType.POSITIVE,
                        confidence=0.8,
                        signals_found=[],
                        excerpt="",
                    ),
                ],
            ),
        }

        split_type, confidence, circuits = analyzer._detect_split_type(circuit_treatments)

        assert split_type == "no_split"
        assert confidence == 0.0

    def test_detect_circuit_split_with_split(self):
        """Test full circuit split detection with conflicting circuits."""
        analyzer = CircuitAnalyzer(min_cases_per_circuit=2)

        cases = [
            {"id": 1, "court": "ca9", "caseName": "Ninth 1"},
            {"id": 2, "court": "ca9", "caseName": "Ninth 2"},
            {"id": 3, "court": "ca5", "caseName": "Fifth 1"},
            {"id": 4, "court": "ca5", "caseName": "Fifth 2"},
        ]

        treatments = [
            TreatmentAnalysis(
                case_name="Ninth 1",
                case_id="1",
                citation="1 F.3d 1",
                treatment_type=TreatmentType.POSITIVE,
                confidence=0.9,
                signals_found=[],
                excerpt="followed",
            ),
            TreatmentAnalysis(
                case_name="Ninth 2",
                case_id="2",
                citation="2 F.3d 2",
                treatment_type=TreatmentType.POSITIVE,
                confidence=0.8,
                signals_found=[],
                excerpt="affirmed",
            ),
            TreatmentAnalysis(
                case_name="Fifth 1",
                case_id="3",
                citation="3 F.3d 3",
                treatment_type=TreatmentType.NEGATIVE,
                confidence=0.9,
                signals_found=[],
                excerpt="overruled",
            ),
            TreatmentAnalysis(
                case_name="Fifth 2",
                case_id="4",
                citation="4 F.3d 4",
                treatment_type=TreatmentType.NEGATIVE,
                confidence=0.85,
                signals_found=[],
                excerpt="criticized",
            ),
        ]

        split, circuits_analyzed = analyzer.detect_circuit_split(
            "410 U.S. 113", "Roe v. Wade", cases, treatments
        )

        assert split is not None
        assert circuits_analyzed == 2
        assert split.split_type == "direct_conflict"
        assert "ca9" in split.circuits_involved
        assert "ca5" in split.circuits_involved
        assert len(split.key_cases) > 0
        assert circuits_analyzed == 2

    def test_detect_circuit_split_insufficient_data(self):
        """Test that no split is detected with insufficient data."""
        analyzer = CircuitAnalyzer(min_cases_per_circuit=2)

        # Only 1 case per circuit (below minimum)
        cases = [
            {"id": 1, "court": "ca9", "caseName": "Ninth 1"},
            {"id": 2, "court": "ca5", "caseName": "Fifth 1"},
        ]

        treatments = [
            TreatmentAnalysis(
                case_name="Ninth 1",
                case_id="1",
                citation="1 F.3d 1",
                treatment_type=TreatmentType.POSITIVE,
                confidence=0.9,
                signals_found=[],
                excerpt="",
            ),
            TreatmentAnalysis(
                case_name="Fifth 1",
                case_id="2",
                citation="2 F.3d 2",
                treatment_type=TreatmentType.NEGATIVE,
                confidence=0.9,
                signals_found=[],
                excerpt="",
            ),
        ]

        split, circuits_analyzed = analyzer.detect_circuit_split(
            "410 U.S. 113", "Roe v. Wade", cases, treatments
        )

        assert split is None
        assert circuits_analyzed == 0


@pytest.mark.unit
async def test_find_circuit_splits_no_citing_cases(mock_client, mocker):
    """Test circuit split detection when no citing cases are found."""
    # Patch get_client for jurisdiction module
    mocker.patch("app.tools.jurisdiction.get_client", return_value=mock_client)

    # Mock no citing cases
    mock_client.find_citing_cases.return_value = {
        "results": [],
        "warnings": [],
        "failed_requests": [],
        "incomplete_data": False,
    }

    result = await find_circuit_splits_impl("410 U.S. 113")

    assert result["split_detected"] is False
    assert result["message"] == "No citing cases found"


@pytest.mark.unit
async def test_find_circuit_splits_case_not_found(mock_client, mocker):
    """Test error handling when target case is not found."""
    # Patch get_client for jurisdiction module
    mocker.patch("app.tools.jurisdiction.get_client", return_value=mock_client)

    mock_client.lookup_citation.return_value = {"error": "Case not found"}

    result = await find_circuit_splits_impl("999 U.S. 999")

    assert "error" in result
    assert "Could not find case" in result["error"]


@pytest.mark.unit
async def test_find_circuit_splits_with_split(mock_client, mocker):
    """Test successful circuit split detection."""
    # Mock target case
    mock_client.lookup_citation.return_value = {
        "caseName": "Miranda v. Arizona",
        "citation": ["384 U.S. 436"],
        "dateFiled": "1966-06-13",
    }

    # Mock citing cases from different circuits
    mock_client.find_citing_cases.return_value = {
        "results": [
            {
                "id": 1,
                "caseName": "Ninth Circuit Case 1",
                "citation": ["100 F.3d 100"],
                "court": "ca9",
                "snippet": "We follow Miranda and affirm its holding",
                "opinions": [{"id": 1001, "snippet": "affirmed"}],
            },
            {
                "id": 2,
                "caseName": "Ninth Circuit Case 2",
                "citation": ["101 F.3d 101"],
                "court": "ca9",
                "snippet": "Miranda is followed in this circuit",
                "opinions": [{"id": 1002, "snippet": "followed"}],
            },
            {
                "id": 3,
                "caseName": "Fifth Circuit Case 1",
                "citation": ["200 F.3d 200"],
                "court": "ca5",
                "snippet": "Miranda is questioned and criticized",
                "opinions": [{"id": 2001, "snippet": "criticized"}],
            },
            {
                "id": 4,
                "caseName": "Fifth Circuit Case 2",
                "citation": ["201 F.3d 201"],
                "court": "ca5",
                "snippet": "We decline to follow Miranda",
                "opinions": [{"id": 2002, "snippet": "declined to follow"}],
            },
        ],
        "warnings": [],
        "failed_requests": [],
        "incomplete_data": False,
    }

    # Patch get_client for jurisdiction module
    mocker.patch("app.tools.jurisdiction.get_client", return_value=mock_client)

    result = await find_circuit_splits_impl("384 U.S. 436", min_cases_per_circuit=2)

    assert result["split_detected"] is True
    assert result["split_type"] == "direct_conflict"
    assert set(result["circuits_involved"]) == {"ca9", "ca5"}
    assert "circuit_details" in result
    assert len(result["circuit_details"]) == 2
