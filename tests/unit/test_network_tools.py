"""Unit tests for citation network tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.tools.network import (
    build_citation_network_impl,
    filter_citation_network_impl,
    get_network_statistics_impl,
    visualize_citation_network_impl,
    export_citation_network_impl,
    generate_citation_report_impl,
)
from app.analysis.treatment_classifier import TreatmentType


# Test build_citation_network_impl
@pytest.mark.unit
async def test_build_citation_network_impl_case_not_found(mock_client):
    """Test build_citation_network when case lookup fails."""
    mock_client.lookup_citation.return_value = {"error": "Case not found"}

    result = await build_citation_network_impl("999 U.S. 999")

    assert "error" in result
    assert "Could not find case for citation" in result["error"]


@pytest.mark.unit
async def test_build_citation_network_impl_unexpected_results(mock_client):
    """Gracefully handle non-list results from the API."""
    root_case = {
        "caseName": "Root Case",
        "citation": ["123 U.S. 456"],
        "dateFiled": "1990-01-01",
        "court": "scotus",
    }

    mock_client.lookup_citation.return_value = root_case
    mock_client.find_citing_cases.return_value = {
        "results": "not-a-list",
        "warnings": ["bad format"],
        "failed_requests": [{"error": "timeout"}],
        "incomplete_data": False,
    }

    result = await build_citation_network_impl("123 U.S. 456")

    assert result["error"].startswith("Unexpected response format")
    assert result["incomplete_data"] is True
    assert result["warnings"] == ["bad format"]


@pytest.mark.unit
async def test_build_citation_network_impl_no_citing_cases(mock_client):
    """Test build_citation_network with no citing cases."""
    root_case = {
        "caseName": "Root Case",
        "citation": ["123 U.S. 456"],
        "dateFiled": "1990-01-01",
        "court": "scotus",
    }

    mock_client.lookup_citation.return_value = root_case
    mock_client.find_citing_cases.return_value = {
        "results": [],
        "warnings": [],
        "failed_requests": [],
        "incomplete_data": True,
    }

    result = await build_citation_network_impl("123 U.S. 456")

    assert result["root_citation"] == "123 U.S. 456"
    assert result["root_case_name"] == "Root Case"
    assert len(result["nodes"]) == 1
    assert len(result["edges"]) == 0
    assert result["statistics"]["message"] == "No citing cases found"
    assert result["incomplete_data"] is True


@pytest.mark.unit
async def test_build_citation_network_impl_with_citing_cases(mock_client, mocker):
    """Test build_citation_network with citing cases."""
    root_case = {
        "caseName": "Root Case",
        "citation": ["123 U.S. 456"],
        "dateFiled": "1990-01-01",
        "court": "scotus",
        "cluster_id": 100,
        "opinions": [{"id": 1000}],
    }

    citing_case = {
        "caseName": "Citing Case",
        "citation": ["789 U.S. 012"],
        "dateFiled": "2000-06-15",
        "court": "ca9",
        "cluster_id": 200,
        "opinions": [{"id": 2000}],
    }

    mock_client.lookup_citation.return_value = root_case
    mock_client.find_citing_cases.return_value = {
        "results": [citing_case],
        "warnings": [],
        "failed_requests": [],
        "incomplete_data": False,
    }

    # Mock treatment analysis
    mock_treatment = MagicMock()
    mock_treatment.treatment_type = TreatmentType.POSITIVE
    mock_treatment.confidence = 0.85
    mock_treatment.excerpt = "This case followed the precedent."

    mock_classifier = mocker.patch("app.tools.network.TreatmentClassifier")
    mock_classifier_instance = mock_classifier.return_value
    mock_classifier_instance.classify_treatment.return_value = mock_treatment

    result = await build_citation_network_impl(
        "123 U.S. 456",
        max_depth=1,
        max_nodes=100,
        include_treatments=True
    )

    assert result["root_citation"] == "123 U.S. 456"
    assert result["root_case_name"] == "Root Case"
    assert len(result["nodes"]) >= 1
    assert len(result["edges"]) >= 0
    assert "statistics" in result


@pytest.mark.unit
async def test_build_citation_network_impl_without_treatments(mock_client):
    """Test build_citation_network without treatment analysis."""
    root_case = {
        "caseName": "Root Case",
        "citation": ["123 U.S. 456"],
        "dateFiled": "1990-01-01",
        "court": "scotus",
        "cluster_id": 100,
        "opinions": [{"id": 1000}],
    }

    citing_case = {
        "caseName": "Citing Case",
        "citation": ["789 U.S. 012"],
        "dateFiled": "2000-06-15",
        "court": "ca9",
        "cluster_id": 200,
        "opinions": [{"id": 2000}],
    }

    mock_client.lookup_citation.return_value = root_case
    mock_client.find_citing_cases.return_value = {
        "results": [citing_case],
        "warnings": [],
        "failed_requests": [],
        "incomplete_data": False,
    }

    result = await build_citation_network_impl(
        "123 U.S. 456",
        max_depth=1,
        max_nodes=100,
        include_treatments=False
    )

    assert result["root_citation"] == "123 U.S. 456"
    assert "nodes" in result
    assert "edges" in result


# Test filter_citation_network_impl
@pytest.mark.unit
async def test_filter_citation_network_impl_by_treatment(mock_client, mocker):
    """Test filter_citation_network by treatment type."""
    # Mock build_citation_network_impl to return a network
    mock_network = {
        "root_citation": "123 U.S. 456",
        "root_case_name": "Root Case",
        "nodes": [
            {
                "citation": "123 U.S. 456",
                "case_name": "Root Case",
                "date_filed": "1990-01-01",
                "court": "scotus",
                "cluster_id": 100,
                "opinion_ids": [1000],
                "metadata": {},
            },
            {
                "citation": "789 U.S. 012",
                "case_name": "Positive Case",
                "date_filed": "2000-06-15",
                "court": "ca9",
                "cluster_id": 200,
                "opinion_ids": [2000],
                "metadata": {},
            },
            {
                "citation": "999 U.S. 111",
                "case_name": "Negative Case",
                "date_filed": "2010-03-20",
                "court": "ca2",
                "cluster_id": 300,
                "opinion_ids": [3000],
                "metadata": {},
            },
        ],
        "edges": [
            {
                "from_citation": "789 U.S. 012",
                "to_citation": "123 U.S. 456",
                "depth": 1,
                "treatment": "positive",
                "confidence": 0.9,
                "excerpt": "Followed precedent.",
            },
            {
                "from_citation": "999 U.S. 111",
                "to_citation": "123 U.S. 456",
                "depth": 1,
                "treatment": "negative",
                "confidence": 0.85,
                "excerpt": "Overruled.",
            },
        ],
        "statistics": {
            "total_nodes": 3,
            "total_edges": 2,
            "treatment_distribution": {"positive": 1, "negative": 1},
        },
    }

    mocker.patch(
        "app.tools.network.build_citation_network_impl",
        return_value=mock_network
    )

    result = await filter_citation_network_impl(
        "123 U.S. 456",
        treatments=["negative"]
    )

    assert result["root_citation"] == "123 U.S. 456"
    assert len(result["edges"]) == 1
    assert result["edges"][0]["treatment"] == "negative"
    assert result["statistics"]["filters_applied"]["treatments"] == ["negative"]


@pytest.mark.unit
async def test_filter_citation_network_impl_by_confidence(mock_client, mocker):
    """Test filter_citation_network by minimum confidence."""
    mock_network = {
        "root_citation": "123 U.S. 456",
        "root_case_name": "Root Case",
        "nodes": [
            {
                "citation": "123 U.S. 456",
                "case_name": "Root Case",
                "date_filed": "1990-01-01",
                "court": "scotus",
                "cluster_id": 100,
                "opinion_ids": [1000],
                "metadata": {},
            },
            {
                "citation": "789 U.S. 012",
                "case_name": "High Confidence Case",
                "date_filed": "2000-06-15",
                "court": "ca9",
                "cluster_id": 200,
                "opinion_ids": [2000],
                "metadata": {},
            },
            {
                "citation": "999 U.S. 111",
                "case_name": "Low Confidence Case",
                "date_filed": "2010-03-20",
                "court": "ca2",
                "cluster_id": 300,
                "opinion_ids": [3000],
                "metadata": {},
            },
        ],
        "edges": [
            {
                "from_citation": "789 U.S. 012",
                "to_citation": "123 U.S. 456",
                "depth": 1,
                "treatment": "positive",
                "confidence": 0.95,
                "excerpt": "High confidence.",
            },
            {
                "from_citation": "999 U.S. 111",
                "to_citation": "123 U.S. 456",
                "depth": 1,
                "treatment": "neutral",
                "confidence": 0.4,
                "excerpt": "Low confidence.",
            },
        ],
        "statistics": {
            "total_nodes": 3,
            "total_edges": 2,
        },
    }

    mocker.patch(
        "app.tools.network.build_citation_network_impl",
        return_value=mock_network
    )

    result = await filter_citation_network_impl(
        "123 U.S. 456",
        min_confidence=0.8
    )

    assert len(result["edges"]) == 1
    assert result["edges"][0]["confidence"] >= 0.8


@pytest.mark.unit
async def test_filter_citation_network_impl_by_date(mock_client, mocker):
    """Test filter_citation_network by date range."""
    mock_network = {
        "root_citation": "123 U.S. 456",
        "root_case_name": "Root Case",
        "nodes": [
            {
                "citation": "123 U.S. 456",
                "case_name": "Root Case",
                "date_filed": "1990-01-01",
                "court": "scotus",
                "cluster_id": 100,
                "opinion_ids": [1000],
                "metadata": {},
            },
            {
                "citation": "789 U.S. 012",
                "case_name": "Old Case",
                "date_filed": "1995-06-15",
                "court": "ca9",
                "cluster_id": 200,
                "opinion_ids": [2000],
                "metadata": {},
            },
            {
                "citation": "999 U.S. 111",
                "case_name": "New Case",
                "date_filed": "2020-03-20",
                "court": "ca2",
                "cluster_id": 300,
                "opinion_ids": [3000],
                "metadata": {},
            },
        ],
        "edges": [
            {
                "from_citation": "789 U.S. 012",
                "to_citation": "123 U.S. 456",
                "depth": 1,
                "treatment": "positive",
                "confidence": 0.9,
                "excerpt": "Old case.",
            },
            {
                "from_citation": "999 U.S. 111",
                "to_citation": "123 U.S. 456",
                "depth": 1,
                "treatment": "positive",
                "confidence": 0.85,
                "excerpt": "New case.",
            },
        ],
        "statistics": {
            "total_nodes": 3,
            "total_edges": 2,
        },
    }

    mocker.patch(
        "app.tools.network.build_citation_network_impl",
        return_value=mock_network
    )

    result = await filter_citation_network_impl(
        "123 U.S. 456",
        date_after="2000-01-01"
    )

    assert len(result["edges"]) == 1
    # Find the node for the remaining edge
    remaining_node = None
    for node in result["nodes"]:
        if node["citation"] == result["edges"][0]["from_citation"]:
            remaining_node = node
            break
    assert remaining_node is not None
    assert remaining_node["date_filed"] >= "2000-01-01"


# Test get_network_statistics_impl
@pytest.mark.unit
async def test_get_network_statistics_impl_basic(mock_client, mocker):
    """Test get_network_statistics basic functionality."""
    mock_network = {
        "root_citation": "123 U.S. 456",
        "root_case_name": "Root Case",
        "nodes": [
            {
                "citation": "123 U.S. 456",
                "case_name": "Root Case",
                "date_filed": "1990-01-01",
                "court": "scotus",
            },
            {
                "citation": "789 U.S. 012",
                "case_name": "Citing Case 1",
                "date_filed": "2000-06-15",
                "court": "ca9",
            },
            {
                "citation": "999 U.S. 111",
                "case_name": "Citing Case 2",
                "date_filed": "2000-08-20",
                "court": "ca2",
            },
        ],
        "edges": [
            {"from_citation": "789 U.S. 012", "to_citation": "123 U.S. 456"},
            {"from_citation": "999 U.S. 111", "to_citation": "123 U.S. 456"},
        ],
        "statistics": {
            "treatment_distribution": {"positive": 1, "neutral": 1},
        },
    }

    mocker.patch(
        "app.tools.network.build_citation_network_impl",
        return_value=mock_network
    )

    result = await get_network_statistics_impl(
        "123 U.S. 456",
        enable_advanced_metrics=False
    )

    assert result["citation"] == "123 U.S. 456"
    assert result["citation_count"] == 2
    assert "temporal_distribution" in result
    assert "court_distribution" in result
    assert "influence_score" in result


@pytest.mark.unit
async def test_get_network_statistics_impl_with_advanced_metrics(mock_client, mocker):
    """Test get_network_statistics with advanced metrics enabled."""
    mock_network = {
        "root_citation": "123 U.S. 456",
        "root_case_name": "Root Case",
        "nodes": [
            {
                "citation": "123 U.S. 456",
                "case_name": "Root Case",
                "date_filed": "1990-01-01",
                "court": "scotus",
            },
            {
                "citation": "789 U.S. 012",
                "case_name": "Citing Case",
                "date_filed": "2000-06-15",
                "court": "ca9",
            },
        ],
        "edges": [
            {
                "from_citation": "789 U.S. 012",
                "to_citation": "123 U.S. 456",
                "treatment": "positive",
                "confidence": 0.9,
            }
        ],
        "statistics": {
            "treatment_distribution": {"positive": 1},
        },
    }

    mocker.patch(
        "app.tools.network.build_citation_network_impl",
        return_value=mock_network
    )

    result = await get_network_statistics_impl(
        "123 U.S. 456",
        enable_advanced_metrics=True,
        enable_community_detection=True
    )

    assert "graph_metrics" in result
    assert "config" in result["graph_metrics"]
    assert result["graph_metrics"]["config"]["enable_advanced_metrics"] is True


# Test visualize_citation_network_impl
@pytest.mark.unit
async def test_visualize_citation_network_impl_flowchart(mock_client, mocker):
    """Test visualize_citation_network with flowchart diagram."""
    mock_network = {
        "root_citation": "123 U.S. 456",
        "root_case_name": "Root Case",
        "nodes": [{"citation": "123 U.S. 456", "case_name": "Root Case"}],
        "edges": [],
    }

    mocker.patch(
        "app.tools.network.build_citation_network_impl",
        return_value=mock_network
    )

    mock_generator = mocker.patch("app.tools.network.MermaidGenerator")
    mock_generator_instance = mock_generator.return_value
    mock_generator_instance.generate_flowchart.return_value = "flowchart TB"
    mock_generator_instance.generate_summary_stats.return_value = "Summary"

    result = await visualize_citation_network_impl(
        "123 U.S. 456",
        diagram_type="flowchart"
    )

    assert result["citation"] == "123 U.S. 456"
    assert "mermaid_syntax" in result
    assert result["node_count"] == 1
    assert result["edge_count"] == 0


@pytest.mark.unit
async def test_visualize_citation_network_impl_all_diagrams(mock_client, mocker):
    """Test visualize_citation_network with all diagram types."""
    mock_network = {
        "root_citation": "123 U.S. 456",
        "root_case_name": "Root Case",
        "nodes": [{"citation": "123 U.S. 456", "case_name": "Root Case"}],
        "edges": [],
    }

    mocker.patch(
        "app.tools.network.build_citation_network_impl",
        return_value=mock_network
    )

    mock_generator = mocker.patch("app.tools.network.MermaidGenerator")
    mock_generator_instance = mock_generator.return_value
    mock_generator_instance.generate_flowchart.return_value = "flowchart"
    mock_generator_instance.generate_hierarchical.return_value = "hierarchical"
    mock_generator_instance.generate_mindmap.return_value = "mindmap"
    mock_generator_instance.generate_timeline.return_value = "timeline"
    mock_generator_instance.generate_summary_stats.return_value = "Summary"

    result = await visualize_citation_network_impl(
        "123 U.S. 456",
        diagram_type="all"
    )

    assert result["all_diagrams"] is not None
    assert "flowchart" in result["all_diagrams"]
    assert "hierarchical" in result["all_diagrams"]
    assert "mindmap" in result["all_diagrams"]
    assert "timeline" in result["all_diagrams"]


# Test export_citation_network_impl
@pytest.mark.unit
async def test_export_citation_network_impl_graphml(mock_client, mocker):
    """Test export_citation_network with GraphML format."""
    mock_network = {
        "root_citation": "123 U.S. 456",
        "root_case_name": "Root Case",
        "nodes": [],
        "edges": [],
    }

    mocker.patch(
        "app.tools.network.build_citation_network_impl",
        return_value=mock_network
    )

    mock_generator = mocker.patch("app.tools.network.MermaidGenerator")
    mock_generator_instance = mock_generator.return_value
    mock_generator_instance.generate_graphml.return_value = "<graphml>...</graphml>"

    result = await export_citation_network_impl("123 U.S. 456", format="graphml")

    assert result["format"] == "graphml"
    assert result["content"] == "<graphml>...</graphml>"
    assert result["mime_type"] == "application/xml"


@pytest.mark.unit
async def test_export_citation_network_impl_json(mock_client, mocker):
    """Test export_citation_network with JSON format."""
    mock_network = {
        "root_citation": "123 U.S. 456",
        "root_case_name": "Root Case",
        "nodes": [],
        "edges": [],
    }

    mocker.patch(
        "app.tools.network.build_citation_network_impl",
        return_value=mock_network
    )

    mock_generator = mocker.patch("app.tools.network.MermaidGenerator")
    mock_generator_instance = mock_generator.return_value
    mock_generator_instance.generate_json_graph.return_value = '{"nodes": []}'

    result = await export_citation_network_impl("123 U.S. 456", format="json")

    assert result["format"] == "json"
    assert result["mime_type"] == "application/json"


@pytest.mark.unit
async def test_export_citation_network_impl_unsupported_format(mock_client, mocker):
    """Test export_citation_network with unsupported format."""
    mock_network = {
        "root_citation": "123 U.S. 456",
        "root_case_name": "Root Case",
        "nodes": [],
        "edges": [],
    }

    mocker.patch(
        "app.tools.network.build_citation_network_impl",
        return_value=mock_network
    )

    result = await export_citation_network_impl("123 U.S. 456", format="invalid")

    assert "error" in result
    assert "Unsupported format" in result["error"]


# Test generate_citation_report_impl
@pytest.mark.unit
async def test_generate_citation_report_impl_full(mock_client, mocker):
    """Test generate_citation_report with all features enabled."""
    mock_network = {
        "root_citation": "123 U.S. 456",
        "root_case_name": "Root Case",
        "nodes": [
            {
                "citation": "123 U.S. 456",
                "case_name": "Root Case",
                "date_filed": "1990-01-01",
                "court": "scotus",
            }
        ],
        "edges": [],
        "statistics": {
            "total_nodes": 1,
            "total_edges": 0,
            "treatment_distribution": {},
        },
    }

    mocker.patch(
        "app.tools.network.build_citation_network_impl",
        return_value=mock_network
    )

    mock_generator = mocker.patch("app.tools.network.MermaidGenerator")
    mock_generator_instance = mock_generator.return_value
    mock_generator_instance.generate_flowchart.return_value = "flowchart TB"

    result = await generate_citation_report_impl(
        "123 U.S. 456",
        include_diagram=True,
        include_statistics=True
    )

    assert result["citation"] == "123 U.S. 456"
    assert result["case_name"] == "Root Case"
    assert "markdown_report" in result
    assert "Citation Analysis: Root Case" in result["markdown_report"]
    assert result["mermaid_diagram"] is not None
    assert result["statistics"] is not None


@pytest.mark.unit
async def test_generate_citation_report_impl_minimal(mock_client, mocker):
    """Test generate_citation_report with minimal features."""
    mock_network = {
        "root_citation": "123 U.S. 456",
        "root_case_name": "Root Case",
        "nodes": [{"citation": "123 U.S. 456", "case_name": "Root Case"}],
        "edges": [],
        "statistics": {"total_nodes": 1, "total_edges": 0},
    }

    mocker.patch(
        "app.tools.network.build_citation_network_impl",
        return_value=mock_network
    )

    result = await generate_citation_report_impl(
        "123 U.S. 456",
        include_diagram=False,
        include_statistics=False
    )

    assert result["citation"] == "123 U.S. 456"
    assert "markdown_report" in result
    assert result["mermaid_diagram"] is None
    assert result["statistics"] is None


@pytest.mark.unit
async def test_generate_citation_report_impl_with_treatment_focus(mock_client, mocker):
    """Test generate_citation_report with treatment focus."""
    mock_network = {
        "root_citation": "123 U.S. 456",
        "root_case_name": "Root Case",
        "nodes": [
            {"citation": "123 U.S. 456", "case_name": "Root Case"},
            {"citation": "789 U.S. 012", "case_name": "Citing Case", "date_filed": "2000-01-01"},
        ],
        "edges": [
            {
                "from_citation": "789 U.S. 012",
                "to_citation": "123 U.S. 456",
                "treatment": "overruled",
                "confidence": 0.95,
                "excerpt": "This case was overruled.",
            }
        ],
        "statistics": {
            "total_nodes": 2,
            "total_edges": 1,
            "treatment_distribution": {"overruled": 1},
        },
    }

    mocker.patch(
        "app.tools.network.build_citation_network_impl",
        return_value=mock_network
    )

    result = await generate_citation_report_impl(
        "123 U.S. 456",
        include_diagram=False,
        include_statistics=False,
        treatment_focus=["overruled"]
    )

    assert "Key Cases" in result["markdown_report"]
    assert "Citing Case" in result["markdown_report"]
    assert "overruled" in result["markdown_report"]
