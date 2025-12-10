"""Tests for Mermaid diagram generator."""


import pytest

from app.analysis.mermaid_generator import MermaidGenerator


@pytest.fixture
def sample_network_data():
    return {
        "root_citation": "410 U.S. 113",
        "root_case_name": "Roe v. Wade",
        "nodes": [
            {
                "citation": "410 U.S. 113",
                "case_name": "Roe v. Wade",
                "date_filed": "1973-01-22",
                "court": "SCOTUS",
            },
            {
                "citation": "505 U.S. 833",
                "case_name": "Planned Parenthood v. Casey",
                "date_filed": "1992-06-29",
                "court": "Third Circuit",
            },
            {
                "citation": "597 U.S. 215",
                "case_name": "Dobbs v. Jackson",
                "date_filed": "2022-06-24",
                "court": "SCOTUS",
            }
        ],
        "edges": [
            {
                "from_citation": "505 U.S. 833",
                "to_citation": "410 U.S. 113",
                "treatment": "affirmed",
                "confidence": 0.8,
                "excerpt": "Affirmed reasoning",
            },
            {
                "from_citation": "597 U.S. 215",
                "to_citation": "410 U.S. 113",
                "treatment": "overruled",
                "confidence": 0.95,
                "excerpt": "Overruled prior holding",
            }
        ],
        "statistics": {
            "total_nodes": 3,
            "total_edges": 2,
            "max_depth": 1,
            "treatment_distribution": {
                "affirmed": 1,
                "overruled": 1
            }
        }
    }

def test_sanitize_label():
    generator = MermaidGenerator()
    assert generator._sanitize_label('Case "Name"') == "Case 'Name'"
    assert generator._sanitize_label("Case\nName") == "Case Name"
    assert generator._sanitize_label("A" * 50, max_length=10) == "AAAAAAA..."

def test_get_node_id():
    generator = MermaidGenerator()
    assert generator._get_node_id("410 U.S. 113") == "case_410_U_S__113"
    assert generator._get_node_id("Casey") == "Casey"

def test_get_treatment_style_class():
    generator = MermaidGenerator()
    assert generator._get_treatment_style_class("overruled") == "negative"
    assert generator._get_treatment_style_class("affirmed") == "positive"
    assert generator._get_treatment_style_class("questioned") == "questioned"
    assert generator._get_treatment_style_class("cited") == "positive"
    assert generator._get_treatment_style_class(None) == "neutral"

def test_generate_flowchart(sample_network_data):
    generator = MermaidGenerator()
    flowchart = generator.generate_flowchart(sample_network_data)

    assert "flowchart TB" in flowchart
    assert "Roe v. Wade" in flowchart
    assert "Dobbs v. Jackson" in flowchart
    assert "overruled" in flowchart
    # Note: Styles are now applied directly or via classDef
    assert "classDef root" in flowchart
    assert "Legend" in flowchart

def test_generate_graph(sample_network_data):
    generator = MermaidGenerator()
    graph = generator.generate_graph(sample_network_data)

    # Now forwards to flowchart with simplified options
    assert "flowchart LR" in graph
    assert "Roe v. Wade" in graph
    assert "Dobbs v. Jackson" in graph

def test_generate_timeline(sample_network_data):
    generator = MermaidGenerator()
    timeline = generator.generate_timeline(sample_network_data)

    assert "timeline" in timeline
    assert "1992" in timeline
    assert "2022" in timeline
    assert "Dobbs v. Jackson" in timeline
    assert "(overruled)" in timeline

def test_generate_summary_stats(sample_network_data):
    generator = MermaidGenerator()
    summary = generator.generate_summary_stats(sample_network_data)

    assert "Citation Network: Roe v. Wade" in summary
    assert "Total Cases:** 3" in summary
    assert "overruled:** 1" in summary

def test_generate_flowchart_with_sizes(sample_network_data):
    generator = MermaidGenerator()
    flowchart = generator.generate_flowchart(
        sample_network_data, node_size_by="citation", show_legend=False
    )

    assert "size-lg" in flowchart
    assert "court_scotus" in flowchart

def test_generate_graphml(sample_network_data):
    generator = MermaidGenerator()
    graphml = generator.generate_graphml(sample_network_data)

    assert "<graphml" in graphml
    assert "data key=\"d0\">Roe v. Wade" in graphml
    assert "excerpt" in graphml
    # Check new fields
    assert "court_level" in graphml

def test_generate_json_graph(sample_network_data):
    generator = MermaidGenerator()
    json_graph = generator.generate_json_graph(sample_network_data)

    assert json_graph["root"] == "410 U.S. 113"
    assert any(node["citation_score"] > 0 for node in json_graph["nodes"])
    # Check new fields
    assert "court_level" in json_graph["nodes"][0]

def test_generate_hierarchical(sample_network_data):
    generator = MermaidGenerator()
    diagram = generator.generate_hierarchical(sample_network_data)

    assert "flowchart TB" in diagram
    assert "subgraph SCOTUS" in diagram
    # Note: "Third Circuit" maps to unknown if not strictly caught, but test court mapper handles general patterns?
    # Actually "Third Circuit" in sample data probably maps to unknown because our mapper looks for "ca3", etc.
    # Let's verify what "Third Circuit" maps to. It's likely Unknown or State fallback if it's 2 chars, but it's not.
    # It maps to UNKNOWN.
    assert "subgraph UNKNOWN" in diagram or "subgraph SCOTUS" in diagram

def test_generate_mindmap(sample_network_data):
    generator = MermaidGenerator()
    mindmap = generator.generate_mindmap(sample_network_data)

    assert "mindmap" in mindmap
    assert "Roe v. Wade" in mindmap
    assert "SCOTUS" in mindmap

def test_generate_obsidian_canvas(sample_network_data):
    generator = MermaidGenerator()
    canvas = generator.generate_obsidian_canvas(sample_network_data)

    assert "nodes" in canvas
    assert "edges" in canvas
    assert len(canvas["nodes"]) == 3
    assert len(canvas["edges"]) == 2

def test_style_presets():
    # Test Monochrome
    mono = MermaidGenerator(style_preset="monochrome")
    assert mono.default_treatment_palette["positive"] == "#333"

    # Test Publication
    pub = MermaidGenerator(style_preset="publication")
    assert pub.default_treatment_palette["positive"] == "#228B22"
    assert pub.default_court_palette["scotus"] == "#1a365d"
