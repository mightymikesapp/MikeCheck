"""Mermaid diagram generation for citation networks.

This module converts citation networks into Mermaid diagram syntax
for visualization in Obsidian and other markdown-compatible tools.
It also provides export helpers for GraphML/JSON structures to
support external visualization utilities.
"""

import logging
import uuid
from collections import defaultdict
from html import escape
from itertools import cycle
from typing import Any

from app.analysis.court_mapper import CourtLevel, get_court_level
from app.types import CitationNetworkResult

logger = logging.getLogger(__name__)


class MermaidGenerator:
    """Generator for creating Mermaid diagrams from citation networks."""

    def __init__(self, style_preset: str = "default") -> None:
        """Initialize the Mermaid generator.

        Args:
            style_preset: Styling preset ("default", "publication", "monochrome")
        """
        self.style_preset = style_preset
        self._init_palettes()

    def _init_palettes(self) -> None:
        """Initialize color palettes based on style preset."""
        if self.style_preset == "monochrome":
            self.default_treatment_palette = {
                "positive": "#333",
                "negative": "#000",
                "questioned": "#666",
                "neutral": "#999",
            }
            self.default_court_palette = {
                "scotus": "#000",
                "circuit": "#333",
                "district": "#666",
                "state": "#999",
                "unknown": "#ccc",
            }
            self.edge_styles = {
                "positive": "stroke:#333,stroke-width:2px",
                "negative": "stroke:#000,stroke-width:2px,stroke-dasharray: 5 5",
                "neutral": "stroke:#999,stroke-width:1px,stroke-dasharray: 2 2",
            }
        elif self.style_preset == "publication":
            # Publication-quality high contrast colors
            self.default_treatment_palette = {
                "positive": "#228B22",  # Forest Green
                "negative": "#DC143C",  # Crimson
                "questioned": "#DAA520",  # Goldenrod
                "neutral": "#808080",  # Gray
            }
            self.default_court_palette = {
                "scotus": "#1a365d",  # Dark Blue
                "circuit": "#2c5282",  # Medium Blue
                "district": "#4299e1",  # Light Blue
                "state": "#48bb78",  # Green
                "unknown": "#a0aec0",  # Gray
            }
            self.edge_styles = {
                "positive": "stroke:#228B22,stroke-width:2px",
                "negative": "stroke:#DC143C,stroke-width:2px,stroke-dasharray: 5 5",
                "neutral": "stroke:#808080,stroke-width:1px,stroke-dasharray: 2 2",
            }
        else:
            # Default preset
            self.default_treatment_palette = {
                "positive": "#228B22",
                "negative": "#DC143C",
                "questioned": "#DAA520",
                "neutral": "#666",
            }
            self.default_court_palette = {
                "scotus": "#4A90E2",
                "circuit": "#7B61FF",
                "district": "#2DBE8D",
                "state": "#FF9F1C",
                "unknown": "#B0B0B0",
            }
            self.edge_styles = {
                "positive": "stroke:#228B22,stroke-width:2px",
                "negative": "stroke:#DC143C,stroke-width:2px",
                "neutral": "stroke:#666,stroke-width:1px",
            }

    def _build_color_palette(
        self, values: list[str], base_palette: dict[str, str]
    ) -> dict[str, str]:
        """Assign colors to categorical values using a palette with fallbacks."""
        # Only cycle colors if using default palette and keys are missing
        if self.style_preset == "monochrome":
            colors = ["#333", "#666", "#999", "#ccc"]
        else:
            colors = [
                "#4A90E2",
                "#2DBE8D",
                "#FF9F1C",
                "#7B61FF",
                "#EF476F",
                "#06D6A0",
                "#FFD166",
                "#118AB2",
            ]

        palette = base_palette.copy()
        color_cycle = cycle(colors)

        for value in values:
            key = (value or "unknown").lower()
            if key not in palette:
                palette[key] = next(color_cycle)

        return palette

    def _calculate_node_scores(
        self, network: CitationNetworkResult
    ) -> tuple[dict[str, int], dict[str, int]]:
        """Calculate citation and authority scores for nodes."""
        citation_counts: dict[str, int] = defaultdict(int)
        authority_counts: dict[str, int] = defaultdict(int)

        for edge in network.get("edges", []):
            citation_counts[edge["to_citation"]] += 1
            authority_counts[edge["from_citation"]] += 1

        return dict(citation_counts), dict(authority_counts)

    def _size_class(self, score: int, max_score: int) -> str:
        """Get a size class name based on score magnitude."""
        if max_score <= 1:
            return "size-sm"

        ratio = score / max_score
        if ratio > 0.66:
            return "size-lg"
        if ratio > 0.33:
            return "size-md"
        return "size-sm"

    def _sanitize_class_key(self, value: str | None) -> str:
        """Convert arbitrary text to a Mermaid-safe class key."""
        key = (value or "unknown").lower()
        cleaned = "".join(ch if ch.isalnum() else "_" for ch in key)
        return cleaned or "unknown"

    def _sanitize_label(self, text: str | None, max_length: int = 40) -> str:
        """Sanitize text for use in Mermaid node labels."""
        if not text:
            return "Unknown"

        # Remove characters that break Mermaid syntax
        text = text.replace('"', "'").replace("\n", " ").replace("\r", " ")
        text = text.replace("[", "(").replace("]", ")")
        text = text.replace("{", "(").replace("}", ")")

        # Truncate if too long
        if len(text) > max_length:
            text = text[: max_length - 3] + "..."

        return text

    def _get_node_id(self, citation: str) -> str:
        """Generate a valid Mermaid node ID from a citation."""
        node_id = citation.replace(" ", "_").replace(".", "_")
        node_id = node_id.replace(",", "_").replace("-", "_")
        if node_id and not node_id[0].isalpha():
            node_id = "case_" + node_id
        return node_id

    def _get_treatment_style_class(self, treatment: str | None) -> str:
        """Get abstract style class for a treatment type."""
        if not treatment:
            return "neutral"

        treatment_lower = treatment.lower()

        if any(
            neg in treatment_lower
            for neg in ["overruled", "reversed", "vacated", "abrogated", "superseded"]
        ):
            return "negative"

        if any(
            q in treatment_lower for q in ["questioned", "criticized", "limited", "distinguished"]
        ):
            return "questioned"

        if any(
            pos in treatment_lower
            for pos in ["followed", "affirmed", "approved", "adopted", "cited"]
        ):
            return "positive"

        return "neutral"

    def generate_flowchart(
        self,
        network: CitationNetworkResult,
        direction: str = "TB",
        include_dates: bool = True,
        color_by_treatment: bool = True,
        color_by_court: bool = True,
        node_size_by: str | None = None,
        court_palette: dict[str, str] | None = None,
        treatment_palette: dict[str, str] | None = None,
        show_legend: bool = True,
    ) -> str:
        """Generate a standard Mermaid flowchart."""
        lines = [f"flowchart {direction}"]

        # Process scores for sizing
        citation_scores, authority_scores = self._calculate_node_scores(network)
        size_scores = (
            citation_scores
            if node_size_by == "citation"
            else authority_scores
            if node_size_by == "authority"
            else {}
        )
        max_size_score = max(size_scores.values()) if size_scores else 1

        # Resolve palettes
        active_court_palette = self.default_court_palette.copy()
        if court_palette:
            active_court_palette.update(court_palette)

        active_treatment_palette = self.default_treatment_palette.copy()
        if treatment_palette:
            active_treatment_palette.update(treatment_palette)

        # Create nodes
        node_map = {}
        for node in network["nodes"]:
            citation = node["citation"]
            node_id = self._get_node_id(citation)
            node_map[citation] = node_id

            case_name = self._sanitize_label(node.get("case_name"), max_length=30)
            label_parts = [case_name]
            if include_dates:
                date_filed = node.get("date_filed")
                if date_filed:
                    label_parts.append(date_filed[:4])

            label = (
                f"{label_parts[0]}<br/>{label_parts[1]}" if len(label_parts) > 1 else label_parts[0]
            )

            classes = []
            if citation == network["root_citation"]:
                classes.append("root")

            if color_by_court:
                # Map precise court string to level for coloring
                court_level = get_court_level(node.get("court"))
                classes.append(f"court_{court_level.value}")

            if node_size_by:
                score = size_scores.get(citation, 0)
                classes.append(self._size_class(score, max_size_score))

            class_suffix = f":::{','.join(classes)}" if classes else ""
            lines.append(f'    {node_id}["{label}"]{class_suffix}')

        # Create edges
        link_index = 0
        for edge in network["edges"]:
            from_id = node_map.get(edge["from_citation"])
            to_id = node_map.get(edge["to_citation"])

            if not from_id or not to_id:
                continue

            treatment = edge.get("treatment")
            confidence = edge.get("confidence") or 0
            edge_text = (
                f"{self._sanitize_label(treatment, 15)}"
                if (treatment and confidence > 0)
                else "cites"
            )

            lines.append(f'    {from_id} -->|"{edge_text}"| {to_id}')

            if color_by_treatment and treatment:
                style_class = self._get_treatment_style_class(treatment)
                # Use edge styles from preset
                style_def = self.edge_styles.get(style_class, self.edge_styles["neutral"])
                # If specific palette override provided, use that color instead of preset style color
                if treatment_palette:
                    color = self._get_color(style_class, active_treatment_palette)
                    lines.append(f"    linkStyle {link_index} stroke:{color},stroke-width:2px")
                else:
                    lines.append(f"    linkStyle {link_index} {style_def}")
            link_index += 1

        self._add_class_defs(
            lines,
            active_court_palette,
            active_treatment_palette,
            color_by_court,
            show_legend,
            node_size_by,
        )
        return "\n".join(lines)

    def generate_hierarchical(
        self,
        network: CitationNetworkResult,
        show_legend: bool = True,
    ) -> str:
        """Generate a hierarchical flowchart with court levels as subgraphs."""
        lines = ["flowchart TB"]

        # Group nodes by court level
        nodes_by_level = defaultdict(list)
        node_map = {}

        for node in network["nodes"]:
            level = get_court_level(node.get("court"))
            nodes_by_level[level].append(node)
            node_map[node["citation"]] = self._get_node_id(node["citation"])

        # Order of levels: SCOTUS -> Circuit -> District -> State -> Unknown
        level_order = [
            CourtLevel.SCOTUS,
            CourtLevel.CIRCUIT,
            CourtLevel.DISTRICT,
            CourtLevel.STATE,
            CourtLevel.UNKNOWN,
        ]

        # Generate subgraphs
        for level in level_order:
            nodes = nodes_by_level.get(level)
            if not nodes:
                continue

            lines.append(f"    subgraph {level.name}")
            lines.append("      direction TB")

            for node in nodes:
                node_id = node_map[node["citation"]]
                case_name = self._sanitize_label(node.get("case_name"), max_length=30)

                # Apply court coloring class
                class_suffix = f":::court_{level.value}"
                if node["citation"] == network["root_citation"]:
                    class_suffix += ",root"

                lines.append(f'      {node_id}["{case_name}"]{class_suffix}')

            lines.append("    end")

        # Edges
        link_index = 0
        for edge in network["edges"]:
            from_id = node_map.get(edge["from_citation"])
            to_id = node_map.get(edge["to_citation"])
            if from_id and to_id:
                lines.append(f"    {from_id} --> {to_id}")

                # Style edges
                treatment = edge.get("treatment")
                if treatment:
                    style_class = self._get_treatment_style_class(treatment)
                    style_def = self.edge_styles.get(style_class, self.edge_styles["neutral"])
                    lines.append(f"    linkStyle {link_index} {style_def}")
                link_index += 1

        self._add_class_defs(
            lines,
            self.default_court_palette,
            self.default_treatment_palette,
            True,
            show_legend,
            None,
        )
        return "\n".join(lines)

    def generate_mindmap(self, network: CitationNetworkResult) -> str:
        """Generate a radial mindmap diagram."""
        lines = ["mindmap"]
        lines.append("  root((" + self._sanitize_label(network.get("root_case_name")) + "))")

        # Organize by court level for the first ring
        citing_nodes = [n for n in network["nodes"] if n["citation"] != network["root_citation"]]

        # Group by court level
        by_level = defaultdict(list)
        for node in citing_nodes:
            level = get_court_level(node.get("court"))
            by_level[level].append(node)

        for level, nodes in by_level.items():
            lines.append(f"    {level.name}")
            for node in nodes:
                case_name = self._sanitize_label(node.get("case_name"), max_length=25)
                # Find treatment for annotation
                treatment = ""
                for edge in network["edges"]:
                    if edge["from_citation"] == node["citation"]:
                        if edge.get("treatment"):
                            treatment = f"({edge['treatment']})"
                        break

                lines.append(f"      {case_name} {treatment}")

        return "\n".join(lines)

    def generate_timeline(
        self,
        network: CitationNetworkResult,
        treatment_filter: list[str] | None = None,
    ) -> str:
        """Generate a Mermaid timeline."""
        # Collect cases by year
        timeline_data: dict[str, list[tuple[str, str | None]]] = {}

        for node in network["nodes"]:
            if node["citation"] == network["root_citation"]:
                continue

            date_filed = node.get("date_filed")
            if not date_filed:
                continue

            year = date_filed[:4]

            treatment = None
            for edge in network["edges"]:
                if edge["from_citation"] == node["citation"]:
                    treatment = edge.get("treatment")
                    break

            if treatment_filter and treatment not in treatment_filter:
                continue

            case_name = self._sanitize_label(node.get("case_name"), max_length=20)
            if year not in timeline_data:
                timeline_data[year] = []
            timeline_data[year].append((case_name, treatment))

        lines = ["timeline"]
        lines.append(
            f"    title History of {self._sanitize_label(network.get('root_case_name'))}"
        )

        for year in sorted(timeline_data.keys()):
            cases = timeline_data[year]
            lines.append(f"    {year}")
            for case_name, treatment in cases[:5]:
                if treatment:
                    lines.append(f"      : {case_name} <br> ({treatment})")
                else:
                    lines.append(f"      : {case_name}")

        return "\n".join(lines)

    def _add_class_defs(
        self,
        lines: list[str],
        court_palette: dict[str, str],
        treatment_palette: dict[str, str],
        color_by_court: bool,
        show_legend: bool,
        node_size_by: str | None,
    ) -> None:
        """Add CSS class definitions to the Mermaid diagram."""
        lines.append("")
        # Use style preset colors
        lines.append(
            f"    classDef root fill:{court_palette.get('scotus', '#4A90E2')},stroke:#333,stroke-width:4px,color:#fff"
        )
        lines.append("    classDef size-sm stroke-width:1px")
        lines.append("    classDef size-md stroke-width:2px,fill-opacity:90%")
        lines.append("    classDef size-lg stroke-width:3px,fill-opacity:85%")
        lines.append("    classDef legend fill:#f6f8fa,stroke:#d0d7de,stroke-width:1px")

        if color_by_court:
            for court_key, color in court_palette.items():
                lines.append(
                    f"    classDef court_{court_key} fill:{color},stroke:#1A1A1A,stroke-width:1.5px,color:#fff"
                )

        if show_legend:
            lines.append("    subgraph Legend")
            lines.append("      direction TB")

            if color_by_court:
                lines.append('      legend_courts[["Courts"]]:::legend')
                for court_key, color in court_palette.items():
                    # Map court key to readable label
                    label = court_key.upper()
                    lines.append(f'      legend_court_{court_key}["{label}"]:::court_{court_key}')

            if node_size_by:
                lines.append(f'      legend_sizes[["Size by {node_size_by}"]]:::legend')
                lines.append('      legend_large["High"]:::size-lg')

            lines.append("    end")

    def _get_color(self, style_class: str, palette: dict[str, str]) -> str:
        return palette.get(style_class, palette.get("neutral", "#666"))

    def generate_graph(
        self,
        network: CitationNetworkResult,
        direction: str = "LR",
        show_treatments: bool = True,
        color_by_court: bool = True,
        node_size_by: str | None = None,
        court_palette: dict[str, str] | None = None,
        show_legend: bool = False,
    ) -> str:
        """Forwarder to flowchart for now to maintain API compatibility but with simpler defaults."""
        return self.generate_flowchart(
            network,
            direction=direction,
            include_dates=False,
            color_by_treatment=show_treatments,
            color_by_court=color_by_court,
            node_size_by=node_size_by,
            court_palette=court_palette,
            show_legend=show_legend,
        )

    def generate_graphml(self, network: CitationNetworkResult) -> str:
        """Export GraphML with enhanced metadata."""
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<graphml xmlns="http://graphml.graphdrawing.org/xmlns" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">',
            '  <key id="d0" for="node" attr.name="label" attr.type="string"/>',
            '  <key id="d1" for="node" attr.name="court" attr.type="string"/>',
            '  <key id="d2" for="node" attr.name="court_level" attr.type="string"/>',
            '  <key id="d3" for="node" attr.name="date_filed" attr.type="string"/>',
            '  <key id="d4" for="edge" attr.name="treatment" attr.type="string"/>',
            '  <key id="d5" for="edge" attr.name="confidence" attr.type="double"/>',
            '  <key id="d6" for="edge" attr.name="excerpt" attr.type="string"/>',
            '  <graph id="citation_network" edgedefault="directed">',
        ]

        for node in network.get("nodes", []):
            node_id = self._get_node_id(node["citation"])
            court_level = get_court_level(node.get("court")).value

            lines.append(f'    <node id="{escape(node_id)}">')
            lines.append(f'      <data key="d0">{escape(node.get("case_name") or "")}</data>')
            lines.append(f'      <data key="d1">{escape(str(node.get("court", "")))}</data>')
            lines.append(f'      <data key="d2">{court_level}</data>')
            lines.append(f'      <data key="d3">{escape(str(node.get("date_filed", "")))}</data>')
            lines.append("    </node>")

        for i, edge in enumerate(network.get("edges", [])):
            source = self._get_node_id(edge["from_citation"])
            target = self._get_node_id(edge["to_citation"])
            lines.append(
                f'    <edge id="e{i}" source="{escape(source)}" target="{escape(target)}">'
            )
            lines.append(f'      <data key="d4">{escape(str(edge.get("treatment", "")))}</data>')
            lines.append(f'      <data key="d5">{edge.get("confidence", 0.0)}</data>')
            lines.append(f'      <data key="d6">{escape(str(edge.get("excerpt", "")))}</data>')
            lines.append("    </edge>")

        lines.append("  </graph>")
        lines.append("</graphml>")

        return "\n".join(lines)

    def generate_json_graph(self, network: CitationNetworkResult) -> dict[str, Any]:
        """Export enhanced JSON graph."""
        citation_scores, authority_scores = self._calculate_node_scores(network)

        nodes = []
        for node in network.get("nodes", []):
            citation = node["citation"]
            nodes.append(
                {
                    "id": self._get_node_id(citation),
                    "citation": citation,
                    "case_name": node.get("case_name"),
                    "court": node.get("court"),
                    "court_level": get_court_level(node.get("court")).value,
                    "date_filed": node.get("date_filed"),
                    "citation_score": citation_scores.get(citation, 0),
                    "authority_score": authority_scores.get(citation, 0),
                    "is_root": citation == network.get("root_citation"),
                }
            )

        edges = []
        for edge in network.get("edges", []):
            edges.append(
                {
                    "source": self._get_node_id(edge["from_citation"]),
                    "target": self._get_node_id(edge["to_citation"]),
                    "treatment": edge.get("treatment"),
                    "confidence": edge.get("confidence", 0.0),
                    "excerpt": edge.get("excerpt", ""),
                }
            )

        return {"nodes": nodes, "edges": edges, "root": network.get("root_citation")}

    def generate_obsidian_canvas(self, network: CitationNetworkResult) -> dict[str, Any]:
        """Generate Obsidian Canvas JSON format."""
        canvas_nodes = []
        canvas_edges = []

        # Simple grid layout
        x_spacing = 400
        y_spacing = 200
        cols = 5

        node_lookup = {}

        for i, node in enumerate(network.get("nodes", [])):
            node_id = str(uuid.uuid4())
            citation = node["citation"]
            node_lookup[citation] = node_id

            is_root = citation == network.get("root_citation")
            color = "1" if is_root else "2"  # 1=Red, 2=Orange (Basic Obsidian colors)

            # Grid position
            x = (i % cols) * x_spacing
            y = (i // cols) * y_spacing

            text = f"## {node['case_name']}\n**{citation}**\n\n{node.get('date_filed', '')}\n{node.get('court', '')}"

            canvas_nodes.append(
                {
                    "id": node_id,
                    "x": x,
                    "y": y,
                    "width": 300,
                    "height": 150,
                    "color": color,
                    "type": "text",
                    "text": text,
                }
            )

        for edge in network.get("edges", []):
            from_id = node_lookup.get(edge["from_citation"])
            to_id = node_lookup.get(edge["to_citation"])

            if from_id and to_id:
                canvas_edges.append(
                    {
                        "id": str(uuid.uuid4()),
                        "fromNode": from_id,
                        "fromSide": "bottom",
                        "toNode": to_id,
                        "toSide": "top",
                        "label": edge.get("treatment") or "cites",
                    }
                )

        return {"nodes": canvas_nodes, "edges": canvas_edges}

    def generate_summary_stats(self, network: CitationNetworkResult) -> str:
        """Generate a text summary of network statistics."""
        stats = network.get("statistics", {})

        lines = [
            f"# Citation Network: {network['root_case_name']}",
            f"**Citation:** {network['root_citation']}",
            "",
            "## Network Statistics",
            f"- **Total Cases:** {stats.get('total_nodes', 0)}",
            f"- **Total Citations:** {stats.get('total_edges', 0)}",
            f"- **Network Depth:** {stats.get('max_depth', 0)}",
            "",
        ]

        treatment_dist = stats.get("treatment_distribution", {})
        if treatment_dist:
            lines.append("## Treatment Distribution")
            for treatment, count in sorted(
                treatment_dist.items(), key=lambda x: x[1], reverse=True
            ):
                lines.append(f"- **{treatment}:** {count}")
            lines.append("")

        return "\n".join(lines)
