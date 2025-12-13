"""Deep Shepardizing: Recursive Negative Treatment Propagation.

This module implements "Deep Shepardizing" which detects cases that are indirectly
compromised because they rely on overruled, abrogated, or otherwise invalidated authority.

Traditional Shepardizing only checks if a case has been directly overruled. Deep Shepardizing
goes further by identifying cases that may be suspect because they cite and rely upon
cases that have been negatively treated.
"""

from __future__ import annotations

import logging
from typing import Any

from app.analysis.citation_network import CaseNode, CitationEdge, CitationNetwork
from app.logging_utils import log_event
from app.types import CitationNetworkResult, IndirectTreatmentStatus, SuspectReliance

logger = logging.getLogger(__name__)


def reconstruct_citation_network(network_result: CitationNetworkResult) -> CitationNetwork | None:
    """Reconstruct a CitationNetwork object from a CitationNetworkResult dict.

    Args:
        network_result: The CitationNetworkResult dict from build_citation_network_impl

    Returns:
        CitationNetwork object or None if reconstruction fails
    """
    if "error" in network_result:
        return None

    # Reconstruct nodes
    nodes: dict[str, CaseNode] = {}
    for node_dict in network_result.get("nodes", []):
        citation = node_dict.get("citation")
        if not citation:
            continue

        node = CaseNode(
            citation=citation,
            case_name=node_dict.get("case_name") or "Unknown Case",
            date_filed=node_dict.get("date_filed"),
            court=node_dict.get("court"),
            cluster_id=node_dict.get("cluster_id"),
            opinion_ids=node_dict.get("opinion_ids", []),
            metadata=node_dict.get("metadata", {}),
        )
        nodes[citation] = node

    # Reconstruct edges
    edges: list[CitationEdge] = []
    for edge_dict in network_result.get("edges", []):
        edge = CitationEdge(
            from_citation=edge_dict.get("from_citation", ""),
            to_citation=edge_dict.get("to_citation", ""),
            depth=edge_dict.get("depth", 0),
            treatment=edge_dict.get("treatment"),
            confidence=edge_dict.get("confidence", 0.0),
            excerpt=edge_dict.get("excerpt", ""),
        )
        edges.append(edge)

    # Build depth map
    depth_map: dict[str, int] = {}
    root_citation = network_result.get("root_citation", "")
    if root_citation:
        depth_map[root_citation] = 0

    for edge in edges:
        if edge.from_citation not in depth_map:
            depth_map[edge.from_citation] = edge.depth

    # Build citation counts
    citing_counts: dict[str, int] = {}
    cited_counts: dict[str, int] = {}

    for edge in edges:
        citing_counts[edge.to_citation] = citing_counts.get(edge.to_citation, 0) + 1
        cited_counts[edge.from_citation] = cited_counts.get(edge.from_citation, 0) + 1

    return CitationNetwork(
        root_citation=root_citation,
        nodes=nodes,
        edges=edges,
        depth_map=depth_map,
        citing_counts=citing_counts,
        cited_counts=cited_counts,
    )

# Strong negative signals that indicate a case is "bad law"
ROOT_NEGATIVE_SIGNALS = {
    "overruled",
    "abrogated",
    "overturned",
    "vacated",
    "no longer good law",
    "superseded",
}

# Positive signals indicating strong reliance
STRONG_RELIANCE_SIGNALS = {
    "followed",
    "affirmed",
    "reaffirmed",
    "adopted",
    "relied on",
    "relied upon",
    "upheld",
    "confirmed",
    "applied",
}

# Medium reliance signals
MEDIUM_RELIANCE_SIGNALS = {
    "consistent with",
    "in accord with",
    "agree with",
    "supports",
    "cited with approval",
}


class DeepShepardAnalyzer:
    """Analyzer for detecting indirect negative treatment propagation.

    This analyzer identifies cases that may be compromised because they rely on
    cases that have been overruled, abrogated, or otherwise negatively treated.
    """

    def __init__(
        self,
        high_risk_threshold: float = 0.7,
        medium_risk_threshold: float = 0.4,
    ) -> None:
        """Initialize the Deep Shepard analyzer.

        Args:
            high_risk_threshold: Minimum risk score for "high" risk classification (default: 0.7)
            medium_risk_threshold: Minimum risk score for "medium" risk classification (default: 0.4)
        """
        self.high_risk_threshold = high_risk_threshold
        self.medium_risk_threshold = medium_risk_threshold

    def analyze(
        self,
        network: CitationNetwork,
        request_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, IndirectTreatmentStatus]:
        """Analyze a citation network for indirect negative treatment.

        Args:
            network: The citation network to analyze
            request_id: Optional request ID for logging
            job_id: Optional job ID for logging

        Returns:
            Dictionary mapping citations to their indirect treatment status
        """
        log_event(
            logger,
            "Starting deep shepardizing analysis",
            tool_name="deep_shepard_analyzer",
            request_id=request_id,
            job_id=job_id,
            query_params={"root_citation": network.root_citation},
            event="deep_shepard_start",
        )

        # Step 1: Identify root negative nodes
        root_negative_nodes = self._identify_root_negative_nodes(network)

        if not root_negative_nodes:
            log_event(
                logger,
                "No root negative nodes found",
                tool_name="deep_shepard_analyzer",
                request_id=request_id,
                job_id=job_id,
                event="deep_shepard_no_negatives",
            )
            return {}

        log_event(
            logger,
            f"Found {len(root_negative_nodes)} root negative nodes",
            tool_name="deep_shepard_analyzer",
            request_id=request_id,
            job_id=job_id,
            extra_context={"negative_citations": list(root_negative_nodes.keys())},
            event="deep_shepard_negatives_found",
        )

        # Step 2: Find suspect nodes that rely on root negative nodes
        suspect_nodes = self._find_suspect_nodes(network, root_negative_nodes)

        log_event(
            logger,
            f"Identified {len(suspect_nodes)} suspect nodes",
            tool_name="deep_shepard_analyzer",
            request_id=request_id,
            job_id=job_id,
            extra_context={
                "suspect_count": len(suspect_nodes),
                "high_risk_count": sum(
                    1 for s in suspect_nodes.values() if s["risk_score"] >= self.high_risk_threshold
                ),
            },
            event="deep_shepard_complete",
        )

        return suspect_nodes

    def _identify_root_negative_nodes(
        self,
        network: CitationNetwork,
    ) -> dict[str, dict[str, Any]]:
        """Identify cases with explicit strong negative treatment signals.

        Args:
            network: The citation network to analyze

        Returns:
            Dictionary mapping citations to their negative treatment info
        """
        root_negatives: dict[str, dict[str, Any]] = {}

        for edge in network.edges:
            # Check if this edge represents a negative treatment
            if not edge.treatment:
                continue

            treatment_lower = edge.treatment.lower()

            # Check if it's a root negative signal
            if any(signal in treatment_lower for signal in ROOT_NEGATIVE_SIGNALS):
                # The "to_citation" is the case being negatively treated
                cited_case = edge.to_citation

                if cited_case not in root_negatives:
                    node = network.nodes.get(cited_case)
                    root_negatives[cited_case] = {
                        "citation": cited_case,
                        "case_name": node.case_name if node else None,
                        "negative_signals": [],
                    }

                root_negatives[cited_case]["negative_signals"].append(
                    {
                        "signal": edge.treatment,
                        "citing_case": edge.from_citation,
                        "confidence": edge.confidence,
                        "excerpt": edge.excerpt,
                    }
                )

        return root_negatives

    def _find_suspect_nodes(
        self,
        network: CitationNetwork,
        root_negative_nodes: dict[str, dict[str, Any]],
    ) -> dict[str, IndirectTreatmentStatus]:
        """Find cases that positively rely on root negative nodes.

        Args:
            network: The citation network
            root_negative_nodes: Dictionary of cases with negative treatment

        Returns:
            Dictionary of suspect cases with their risk assessment
        """
        suspect_nodes: dict[str, dict[str, Any]] = {}

        # Iterate through all edges to find positive reliances on bad cases
        for edge in network.edges:
            # Check if this edge cites a root negative node
            if edge.to_citation not in root_negative_nodes:
                continue

            # Check if the treatment indicates positive reliance
            if not edge.treatment:
                continue

            treatment_lower = edge.treatment.lower()
            reliance_strength = self._classify_reliance_strength(treatment_lower)

            if reliance_strength == 0.0:
                # Not a positive reliance, skip
                continue

            # This is a suspect node - it positively relies on a bad case
            citing_case = edge.from_citation

            if citing_case not in suspect_nodes:
                node = network.nodes.get(citing_case)
                suspect_nodes[citing_case] = {
                    "citation": citing_case,
                    "case_name": node.case_name if node else None,
                    "suspect_reliances": [],
                    "reasons": [],
                }

            # Get the bad case info
            bad_case = root_negative_nodes[edge.to_citation]
            negative_signals = bad_case["negative_signals"]

            # Get the strongest negative signal for this bad case
            strongest_signal = max(negative_signals, key=lambda x: x["confidence"])

            # Add this reliance to the suspect node
            reliance: SuspectReliance = {
                "bad_case_citation": edge.to_citation,
                "bad_case_name": bad_case["case_name"],
                "reliance_treatment": edge.treatment,
                "reliance_confidence": edge.confidence,
                "reliance_excerpt": edge.excerpt or "",
                "negative_signal": strongest_signal["signal"],
                "negative_weight": strongest_signal["confidence"],
            }

            suspect_nodes[citing_case]["suspect_reliances"].append(reliance)

        # Calculate risk scores and generate recommendations
        result: dict[str, IndirectTreatmentStatus] = {}
        for citation, suspect_data in suspect_nodes.items():
            risk_score = self._calculate_risk_score(suspect_data["suspect_reliances"])
            risk_level = self._classify_risk_level(risk_score)

            reasons = self._generate_reasons(suspect_data["suspect_reliances"])
            recommendation = self._generate_recommendation(risk_score, risk_level)

            status: IndirectTreatmentStatus = {
                "citation": citation,
                "case_name": suspect_data["case_name"],
                "risk_score": risk_score,
                "risk_level": risk_level,
                "reasons": reasons,
                "suspect_reliances": suspect_data["suspect_reliances"],
                "recommendation": recommendation,
            }

            result[citation] = status

        return result

    def _classify_reliance_strength(self, treatment: str) -> float:
        """Classify the strength of reliance based on treatment signal.

        Args:
            treatment: The treatment signal (normalized to lowercase)

        Returns:
            Reliance strength from 0.0 (no reliance) to 1.0 (strong reliance)
        """
        if any(signal in treatment for signal in STRONG_RELIANCE_SIGNALS):
            return 1.0
        elif any(signal in treatment for signal in MEDIUM_RELIANCE_SIGNALS):
            return 0.6
        else:
            # Check for general positive indicators
            if any(
                word in treatment
                for word in ["citing", "quoting", "referencing", "noting", "observing"]
            ):
                return 0.3
            return 0.0

    def _calculate_risk_score(self, reliances: list[SuspectReliance]) -> float:
        """Calculate an overall risk score for a suspect case.

        The risk score is based on:
        - Number of suspect reliances
        - Strength of reliance (treatment type)
        - Severity of negative treatment of the cited cases

        Args:
            reliances: List of suspect reliances

        Returns:
            Risk score from 0.0 to 1.0
        """
        if not reliances:
            return 0.0

        total_risk = 0.0
        for reliance in reliances:
            # Base risk from the negative treatment weight
            negative_weight = reliance.get("negative_weight", 0.5)

            # Adjust by reliance confidence
            reliance_confidence = reliance.get("reliance_confidence", 0.5)

            # Reliance strength based on treatment type
            reliance_treatment = reliance.get("reliance_treatment", "").lower()
            reliance_strength = self._classify_reliance_strength(reliance_treatment)

            # Combined risk: negative weight * reliance confidence * reliance strength
            risk = negative_weight * reliance_confidence * reliance_strength

            total_risk += risk

        # Normalize by number of reliances, but cap at 1.0
        # More suspect reliances increase risk but with diminishing returns
        avg_risk = total_risk / len(reliances)
        multiplier = min(1.0 + (len(reliances) - 1) * 0.2, 1.5)

        final_risk = min(avg_risk * multiplier, 1.0)
        return round(final_risk, 3)

    def _classify_risk_level(self, risk_score: float) -> str:
        """Classify risk level based on risk score.

        Args:
            risk_score: The calculated risk score

        Returns:
            Risk level: "high", "medium", or "low"
        """
        if risk_score >= self.high_risk_threshold:
            return "high"
        elif risk_score >= self.medium_risk_threshold:
            return "medium"
        else:
            return "low"

    def _generate_reasons(self, reliances: list[SuspectReliance]) -> list[str]:
        """Generate human-readable reasons for the risk assessment.

        Args:
            reliances: List of suspect reliances

        Returns:
            List of reason strings
        """
        reasons = []

        for reliance in reliances:
            bad_case = reliance.get("bad_case_citation", "unknown case")
            bad_case_name = reliance.get("bad_case_name")
            reliance_treatment = reliance.get("reliance_treatment", "cited")
            negative_signal = reliance.get("negative_signal", "negatively treated")

            if bad_case_name:
                reason = (
                    f"Relies on {bad_case} ({bad_case_name}) via '{reliance_treatment}', "
                    f"which has been '{negative_signal}'"
                )
            else:
                reason = (
                    f"Relies on {bad_case} via '{reliance_treatment}', "
                    f"which has been '{negative_signal}'"
                )

            reasons.append(reason)

        return reasons

    def _generate_recommendation(self, risk_score: float, risk_level: str) -> str:
        """Generate a recommendation based on risk assessment.

        Args:
            risk_score: The calculated risk score
            risk_level: The classified risk level

        Returns:
            Recommendation string
        """
        if risk_level == "high":
            return (
                f"⚠️ HIGH RISK (score: {risk_score:.2f}): This case may be "
                "compromised due to reliance on overruled authority. "
                "Carefully verify all reasoning and consider finding alternative support."
            )
        elif risk_level == "medium":
            return (
                f"⚠ MEDIUM RISK (score: {risk_score:.2f}): This case cites "
                "negatively-treated authority. Review the cited cases to ensure "
                "the reasoning remains valid."
            )
        else:
            return (
                f"ℹ️ LOW RISK (score: {risk_score:.2f}): This case has minor "
                "connections to negatively-treated authority. Exercise normal caution."
            )


def analyze_deep_shepard(
    network: CitationNetwork,
    high_risk_threshold: float = 0.7,
    medium_risk_threshold: float = 0.4,
    request_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, IndirectTreatmentStatus]:
    """Convenience function for deep shepardizing analysis.

    Args:
        network: The citation network to analyze
        high_risk_threshold: Minimum risk score for "high" risk (default: 0.7)
        medium_risk_threshold: Minimum risk score for "medium" risk (default: 0.4)
        request_id: Optional request ID for logging
        job_id: Optional job ID for logging

    Returns:
        Dictionary mapping citations to their indirect treatment status
    """
    analyzer = DeepShepardAnalyzer(
        high_risk_threshold=high_risk_threshold,
        medium_risk_threshold=medium_risk_threshold,
    )
    return analyzer.analyze(network, request_id=request_id, job_id=job_id)
