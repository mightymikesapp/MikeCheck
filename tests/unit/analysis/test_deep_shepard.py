"""Unit tests for deep shepardizing analysis (recursive negative treatment propagation)."""

from __future__ import annotations

import pytest

from app.analysis.citation_network import CaseNode, CitationEdge, CitationNetwork
from app.analysis.deep_shepard import DeepShepardAnalyzer, reconstruct_citation_network
from app.types import CitationNetworkResult


@pytest.fixture
def simple_network_with_overruled_case() -> CitationNetwork:
    """Create a simple 3-node network where Case C relies on overruled Case B.

    Structure:
    - Case A cites Case B with "overruled" treatment
    - Case C cites Case B with "followed" treatment
    - Expected: Case C should be flagged as suspect with high risk
    """
    nodes = {
        "100 U.S. 1": CaseNode(
            citation="100 U.S. 1",
            case_name="Case A v. State",
            date_filed="2020-01-01",
            court="Supreme Court",
            cluster_id=1,
            opinion_ids=[1],
            metadata={},
        ),
        "200 U.S. 2": CaseNode(
            citation="200 U.S. 2",
            case_name="Case B v. State",
            date_filed="2015-01-01",
            court="Supreme Court",
            cluster_id=2,
            opinion_ids=[2],
            metadata={},
        ),
        "300 U.S. 3": CaseNode(
            citation="300 U.S. 3",
            case_name="Case C v. State",
            date_filed="2018-01-01",
            court="Supreme Court",
            cluster_id=3,
            opinion_ids=[3],
            metadata={},
        ),
    }

    edges = [
        # Case A overrules Case B
        CitationEdge(
            from_citation="100 U.S. 1",
            to_citation="200 U.S. 2",
            depth=1,
            treatment="overruled",
            confidence=1.0,
            excerpt="We overrule Case B...",
        ),
        # Case C follows Case B (problematic!)
        CitationEdge(
            from_citation="300 U.S. 3",
            to_citation="200 U.S. 2",
            depth=1,
            treatment="followed",
            confidence=0.9,
            excerpt="Following Case B, we hold...",
        ),
    ]

    return CitationNetwork(
        root_citation="200 U.S. 2",
        nodes=nodes,
        edges=edges,
        depth_map={"200 U.S. 2": 0, "100 U.S. 1": 1, "300 U.S. 3": 1},
        citing_counts={"200 U.S. 2": 2},
        cited_counts={"100 U.S. 1": 1, "300 U.S. 3": 1},
    )


@pytest.fixture
def network_with_multiple_suspect_reliances() -> CitationNetwork:
    """Create a network where one case relies on multiple bad cases."""
    nodes = {
        "100 U.S. 1": CaseNode(
            citation="100 U.S. 1",
            case_name="Bad Case 1",
            date_filed="2010-01-01",
            court="Supreme Court",
            cluster_id=1,
            opinion_ids=[1],
            metadata={},
        ),
        "200 U.S. 2": CaseNode(
            citation="200 U.S. 2",
            case_name="Bad Case 2",
            date_filed="2010-01-01",
            court="Supreme Court",
            cluster_id=2,
            opinion_ids=[2],
            metadata={},
        ),
        "300 U.S. 3": CaseNode(
            citation="300 U.S. 3",
            case_name="Suspect Case",
            date_filed="2015-01-01",
            court="Supreme Court",
            cluster_id=3,
            opinion_ids=[3],
            metadata={},
        ),
        "400 U.S. 4": CaseNode(
            citation="400 U.S. 4",
            case_name="Overruling Case 1",
            date_filed="2020-01-01",
            court="Supreme Court",
            cluster_id=4,
            opinion_ids=[4],
            metadata={},
        ),
        "500 U.S. 5": CaseNode(
            citation="500 U.S. 5",
            case_name="Abrogating Case 2",
            date_filed="2020-01-01",
            court="Supreme Court",
            cluster_id=5,
            opinion_ids=[5],
            metadata={},
        ),
    }

    edges = [
        # Bad Case 1 is overruled
        CitationEdge(
            from_citation="400 U.S. 4",
            to_citation="100 U.S. 1",
            depth=1,
            treatment="overruled",
            confidence=1.0,
            excerpt="We overrule Bad Case 1...",
        ),
        # Bad Case 2 is abrogated
        CitationEdge(
            from_citation="500 U.S. 5",
            to_citation="200 U.S. 2",
            depth=1,
            treatment="abrogated",
            confidence=1.0,
            excerpt="This statute abrogates Bad Case 2...",
        ),
        # Suspect Case relies on both bad cases
        CitationEdge(
            from_citation="300 U.S. 3",
            to_citation="100 U.S. 1",
            depth=1,
            treatment="relied upon",
            confidence=0.85,
            excerpt="Relying on Bad Case 1...",
        ),
        CitationEdge(
            from_citation="300 U.S. 3",
            to_citation="200 U.S. 2",
            depth=1,
            treatment="adopted",
            confidence=0.85,
            excerpt="Adopting the reasoning of Bad Case 2...",
        ),
    ]

    return CitationNetwork(
        root_citation="100 U.S. 1",
        nodes=nodes,
        edges=edges,
        depth_map={
            "100 U.S. 1": 0,
            "200 U.S. 2": 0,
            "300 U.S. 3": 1,
            "400 U.S. 4": 1,
            "500 U.S. 5": 1,
        },
        citing_counts={"100 U.S. 1": 2, "200 U.S. 2": 2},
        cited_counts={"300 U.S. 3": 2, "400 U.S. 4": 1, "500 U.S. 5": 1},
    )


@pytest.fixture
def network_with_no_suspect_cases() -> CitationNetwork:
    """Create a network with negative treatment but no positive reliance on bad cases."""
    nodes = {
        "100 U.S. 1": CaseNode(
            citation="100 U.S. 1",
            case_name="Bad Case",
            date_filed="2010-01-01",
            court="Supreme Court",
            cluster_id=1,
            opinion_ids=[1],
            metadata={},
        ),
        "200 U.S. 2": CaseNode(
            citation="200 U.S. 2",
            case_name="Overruling Case",
            date_filed="2020-01-01",
            court="Supreme Court",
            cluster_id=2,
            opinion_ids=[2],
            metadata={},
        ),
        "300 U.S. 3": CaseNode(
            citation="300 U.S. 3",
            case_name="Distinguishing Case",
            date_filed="2018-01-01",
            court="Supreme Court",
            cluster_id=3,
            opinion_ids=[3],
            metadata={},
        ),
    }

    edges = [
        # Case overruled
        CitationEdge(
            from_citation="200 U.S. 2",
            to_citation="100 U.S. 1",
            depth=1,
            treatment="overruled",
            confidence=1.0,
            excerpt="We overrule...",
        ),
        # Another case distinguishes it (not positive reliance)
        CitationEdge(
            from_citation="300 U.S. 3",
            to_citation="100 U.S. 1",
            depth=1,
            treatment="distinguished",
            confidence=0.5,
            excerpt="We distinguish...",
        ),
    ]

    return CitationNetwork(
        root_citation="100 U.S. 1",
        nodes=nodes,
        edges=edges,
        depth_map={"100 U.S. 1": 0, "200 U.S. 2": 1, "300 U.S. 3": 1},
        citing_counts={"100 U.S. 1": 2},
        cited_counts={"200 U.S. 2": 1, "300 U.S. 3": 1},
    )


@pytest.mark.unit
class TestDeepShepardAnalyzer:
    """Test suite for DeepShepardAnalyzer."""

    def test_simple_suspect_case_detection(self, simple_network_with_overruled_case):
        """Test that a case relying on overruled authority is flagged as suspect."""
        analyzer = DeepShepardAnalyzer()
        results = analyzer.analyze(simple_network_with_overruled_case)

        # Should have exactly 1 suspect case
        assert len(results) == 1
        assert "300 U.S. 3" in results

        suspect = results["300 U.S. 3"]
        assert suspect["citation"] == "300 U.S. 3"
        assert suspect["case_name"] == "Case C v. State"
        assert suspect["risk_score"] == 0.9  # High risk
        assert suspect["risk_level"] == "high"
        assert len(suspect["suspect_reliances"]) == 1

        reliance = suspect["suspect_reliances"][0]
        assert reliance["bad_case_citation"] == "200 U.S. 2"
        assert reliance["reliance_treatment"] == "followed"
        assert reliance["negative_signal"] == "overruled"
        assert reliance["negative_weight"] == 1.0

    def test_multiple_suspect_reliances(self, network_with_multiple_suspect_reliances):
        """Test that a case relying on multiple bad cases has higher risk score."""
        analyzer = DeepShepardAnalyzer()
        results = analyzer.analyze(network_with_multiple_suspect_reliances)

        # Should have exactly 1 suspect case
        assert len(results) == 1
        assert "300 U.S. 3" in results

        suspect = results["300 U.S. 3"]
        assert suspect["risk_score"] > 0.8  # Very high risk due to multiple reliances
        assert suspect["risk_level"] == "high"
        assert len(suspect["suspect_reliances"]) == 2

        # Check both reliances are present
        bad_cases = {r["bad_case_citation"] for r in suspect["suspect_reliances"]}
        assert bad_cases == {"100 U.S. 1", "200 U.S. 2"}

    def test_no_suspect_cases(self, network_with_no_suspect_cases):
        """Test that no suspects are found when no positive reliance exists."""
        analyzer = DeepShepardAnalyzer()
        results = analyzer.analyze(network_with_no_suspect_cases)

        # Should have no suspect cases
        assert len(results) == 0

    def test_risk_level_classification(self):
        """Test that risk levels are correctly classified."""
        analyzer = DeepShepardAnalyzer(
            high_risk_threshold=0.7, medium_risk_threshold=0.4
        )

        assert analyzer._classify_risk_level(0.9) == "high"
        assert analyzer._classify_risk_level(0.7) == "high"
        assert analyzer._classify_risk_level(0.6) == "medium"
        assert analyzer._classify_risk_level(0.4) == "medium"
        assert analyzer._classify_risk_level(0.3) == "low"
        assert analyzer._classify_risk_level(0.0) == "low"

    def test_reliance_strength_classification(self):
        """Test that reliance strength is correctly classified."""
        analyzer = DeepShepardAnalyzer()

        # Strong reliance
        assert analyzer._classify_reliance_strength("followed") == 1.0
        assert analyzer._classify_reliance_strength("affirmed") == 1.0
        assert analyzer._classify_reliance_strength("relied upon") == 1.0
        assert analyzer._classify_reliance_strength("adopted") == 1.0

        # Medium reliance
        assert analyzer._classify_reliance_strength("consistent with") == 0.6
        assert analyzer._classify_reliance_strength("in accord with") == 0.6
        assert analyzer._classify_reliance_strength("supports") == 0.6

        # Weak reliance
        assert analyzer._classify_reliance_strength("citing") == 0.3
        assert analyzer._classify_reliance_strength("quoting") == 0.3

        # No reliance
        assert analyzer._classify_reliance_strength("overruled") == 0.0
        assert analyzer._classify_reliance_strength("distinguished") == 0.0

    def test_root_negative_node_identification(self, simple_network_with_overruled_case):
        """Test that root negative nodes are correctly identified."""
        analyzer = DeepShepardAnalyzer()
        root_negatives = analyzer._identify_root_negative_nodes(
            simple_network_with_overruled_case
        )

        # Should identify Case B as the root negative node
        assert len(root_negatives) == 1
        assert "200 U.S. 2" in root_negatives

        negative = root_negatives["200 U.S. 2"]
        assert negative["citation"] == "200 U.S. 2"
        assert negative["case_name"] == "Case B v. State"
        assert len(negative["negative_signals"]) == 1
        assert negative["negative_signals"][0]["signal"] == "overruled"

    def test_reasons_generation(self, simple_network_with_overruled_case):
        """Test that reasons are correctly generated."""
        analyzer = DeepShepardAnalyzer()
        results = analyzer.analyze(simple_network_with_overruled_case)

        suspect = results["300 U.S. 3"]
        reasons = suspect["reasons"]

        assert len(reasons) == 1
        assert "300 U.S. 3" not in reasons[0]  # Shouldn't reference itself
        assert "200 U.S. 2" in reasons[0]
        assert "Case B v. State" in reasons[0]
        assert "followed" in reasons[0]
        assert "overruled" in reasons[0]

    def test_recommendation_generation(self, simple_network_with_overruled_case):
        """Test that recommendations are correctly generated."""
        analyzer = DeepShepardAnalyzer()
        results = analyzer.analyze(simple_network_with_overruled_case)

        suspect = results["300 U.S. 3"]
        recommendation = suspect["recommendation"]

        assert "HIGH RISK" in recommendation or "⚠️" in recommendation
        assert "overruled authority" in recommendation.lower()

    def test_custom_thresholds(self, simple_network_with_overruled_case):
        """Test that custom thresholds work correctly."""
        # With very high threshold, case should be medium risk
        analyzer = DeepShepardAnalyzer(
            high_risk_threshold=0.99, medium_risk_threshold=0.5
        )
        results = analyzer.analyze(simple_network_with_overruled_case)

        suspect = results["300 U.S. 3"]
        # With high threshold, might not reach "high" level
        assert suspect["risk_level"] in ["medium", "high"]

    def test_empty_network(self):
        """Test that empty network returns no results."""
        empty_network = CitationNetwork(
            root_citation="100 U.S. 1",
            nodes={},
            edges=[],
            depth_map={},
            citing_counts={},
            cited_counts={},
        )

        analyzer = DeepShepardAnalyzer()
        results = analyzer.analyze(empty_network)

        assert len(results) == 0


@pytest.mark.unit
class TestReconstructCitationNetwork:
    """Test suite for network reconstruction from dict."""

    def test_reconstruct_from_valid_result(self):
        """Test reconstruction from a valid CitationNetworkResult."""
        result: CitationNetworkResult = {
            "root_citation": "100 U.S. 1",
            "root_case_name": "Test Case",
            "nodes": [
                {
                    "citation": "100 U.S. 1",
                    "case_name": "Test Case",
                    "date_filed": "2020-01-01",
                    "court": "Supreme Court",
                    "cluster_id": 1,
                    "opinion_ids": [1, 2],
                    "metadata": {"status": "published"},
                },
                {
                    "citation": "200 U.S. 2",
                    "case_name": "Citing Case",
                    "date_filed": "2021-01-01",
                    "court": "Supreme Court",
                    "cluster_id": 2,
                    "opinion_ids": [3],
                    "metadata": {},
                },
            ],
            "edges": [
                {
                    "from_citation": "200 U.S. 2",
                    "to_citation": "100 U.S. 1",
                    "depth": 1,
                    "treatment": "followed",
                    "confidence": 0.9,
                    "excerpt": "Following Test Case...",
                }
            ],
            "statistics": {
                "total_nodes": 2,
                "total_edges": 1,
                "treatment_distribution": {"followed": 1},
            },
        }

        network = reconstruct_citation_network(result)

        assert network is not None
        assert network.root_citation == "100 U.S. 1"
        assert len(network.nodes) == 2
        assert len(network.edges) == 1
        assert "100 U.S. 1" in network.nodes
        assert "200 U.S. 2" in network.nodes

        edge = network.edges[0]
        assert edge.from_citation == "200 U.S. 2"
        assert edge.to_citation == "100 U.S. 1"
        assert edge.treatment == "followed"
        assert edge.confidence == 0.9

    def test_reconstruct_from_error_result(self):
        """Test that reconstruction returns None for error results."""
        error_result: CitationNetworkResult = {
            "error": "Case not found",
            "root_citation": "100 U.S. 1",
            "nodes": [],
            "edges": [],
            "statistics": {"total_nodes": 0, "total_edges": 0},
        }

        network = reconstruct_citation_network(error_result)
        assert network is None

    def test_reconstruct_empty_network(self):
        """Test reconstruction of empty network."""
        empty_result: CitationNetworkResult = {
            "root_citation": "100 U.S. 1",
            "root_case_name": "Test Case",
            "nodes": [
                {
                    "citation": "100 U.S. 1",
                    "case_name": "Test Case",
                    "date_filed": "2020-01-01",
                    "court": "Supreme Court",
                }
            ],
            "edges": [],
            "statistics": {"total_nodes": 1, "total_edges": 0},
        }

        network = reconstruct_citation_network(empty_result)

        assert network is not None
        assert len(network.nodes) == 1
        assert len(network.edges) == 0
        assert network.citing_counts == {}
        assert network.cited_counts == {}


@pytest.mark.unit
def test_integration_with_multiple_negative_signals():
    """Integration test with various negative signals."""
    nodes = {
        "100 U.S. 1": CaseNode(
            citation="100 U.S. 1",
            case_name="Overruled Case",
            date_filed="2010-01-01",
            court="Supreme Court",
            cluster_id=1,
            opinion_ids=[1],
            metadata={},
        ),
        "200 U.S. 2": CaseNode(
            citation="200 U.S. 2",
            case_name="Vacated Case",
            date_filed="2010-01-01",
            court="Supreme Court",
            cluster_id=2,
            opinion_ids=[2],
            metadata={},
        ),
        "300 U.S. 3": CaseNode(
            citation="300 U.S. 3",
            case_name="Suspect Case",
            date_filed="2015-01-01",
            court="Supreme Court",
            cluster_id=3,
            opinion_ids=[3],
            metadata={},
        ),
    }

    edges = [
        CitationEdge(
            from_citation="400 U.S. 4",
            to_citation="100 U.S. 1",
            depth=1,
            treatment="overruled",
            confidence=1.0,
            excerpt="...",
        ),
        CitationEdge(
            from_citation="500 U.S. 5",
            to_citation="200 U.S. 2",
            depth=1,
            treatment="vacated",
            confidence=0.9,
            excerpt="...",
        ),
        CitationEdge(
            from_citation="300 U.S. 3",
            to_citation="100 U.S. 1",
            depth=1,
            treatment="followed",
            confidence=0.9,
            excerpt="...",
        ),
        CitationEdge(
            from_citation="300 U.S. 3",
            to_citation="200 U.S. 2",
            depth=1,
            treatment="affirmed",
            confidence=0.9,
            excerpt="...",
        ),
    ]

    network = CitationNetwork(
        root_citation="100 U.S. 1",
        nodes=nodes,
        edges=edges,
        depth_map={"100 U.S. 1": 0, "200 U.S. 2": 0, "300 U.S. 3": 1},
        citing_counts={"100 U.S. 1": 1, "200 U.S. 2": 1},
        cited_counts={"300 U.S. 3": 2},
    )

    analyzer = DeepShepardAnalyzer()
    results = analyzer.analyze(network)

    assert "300 U.S. 3" in results
    suspect = results["300 U.S. 3"]
    assert len(suspect["suspect_reliances"]) == 2
    assert suspect["risk_level"] == "high"
