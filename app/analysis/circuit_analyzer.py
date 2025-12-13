"""Circuit split detection for legal citations.

This module analyzes citing cases grouped by circuit to detect potential circuit splits
where different federal circuits treat the same case in conflicting ways.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field

from app.analysis.treatment_classifier import TreatmentAnalysis, TreatmentType
from app.types import CourtListenerCase

logger = logging.getLogger(__name__)

# Federal circuit court identifiers used by CourtListener
CIRCUIT_COURTS = {
    "ca1": "First Circuit",
    "ca2": "Second Circuit",
    "ca3": "Third Circuit",
    "ca4": "Fourth Circuit",
    "ca5": "Fifth Circuit",
    "ca6": "Sixth Circuit",
    "ca7": "Seventh Circuit",
    "ca8": "Eighth Circuit",
    "ca9": "Ninth Circuit",
    "ca10": "Tenth Circuit",
    "ca11": "Eleventh Circuit",
    "cadc": "D.C. Circuit",
    "cafc": "Federal Circuit",
}


@dataclass
class CircuitTreatment:
    """Treatment analysis for a single circuit."""

    circuit_id: str
    circuit_name: str
    total_cases: int
    positive_count: int
    negative_count: int
    neutral_count: int
    dominant_treatment: TreatmentType
    representative_cases: list[TreatmentAnalysis]
    average_confidence: float


@dataclass
class CircuitSplit:
    """Represents a detected circuit split."""

    citation: str
    case_name: str
    split_type: str  # "direct_conflict", "emerging_split", "potential_split"
    confidence: float
    circuits_involved: list[str]
    conflicting_circuits: dict[str, CircuitTreatment]
    summary: str
    supreme_court_likely: bool = False
    key_cases: list[dict[str, object]] = field(default_factory=list)


class CircuitAnalyzer:
    """Analyzer for detecting circuit splits in case treatment."""

    def __init__(self, min_cases_per_circuit: int = 2, split_threshold: float = 0.6) -> None:
        """Initialize the circuit analyzer.

        Args:
            min_cases_per_circuit: Minimum cases needed in a circuit to consider it
            split_threshold: Threshold for determining dominant treatment (0.6 = 60%)
        """
        self.min_cases_per_circuit = min_cases_per_circuit
        self.split_threshold = split_threshold

    def _extract_circuit_id(self, court: str | None) -> str | None:
        """Extract circuit identifier from court string.

        Args:
            court: Court identifier from CourtListener (e.g., 'ca9', 'scotus')

        Returns:
            Circuit ID if it's a circuit court, None otherwise
        """
        if not court:
            return None

        court_lower = court.lower()

        # Direct match for circuit courts
        if court_lower in CIRCUIT_COURTS:
            return court_lower

        # Handle variations like 'ca9-1' or 'ca9.2'
        match = re.match(r"(ca\d{1,2}|cadc|cafc)", court_lower)
        if match:
            circuit = match.group(1)
            if circuit in CIRCUIT_COURTS:
                return circuit

        return None

    def _group_by_circuit(
        self, cases: list[CourtListenerCase], treatments: list[TreatmentAnalysis]
    ) -> dict[str, list[TreatmentAnalysis]]:
        """Group treatment analyses by circuit.

        Args:
            cases: List of CourtListener cases
            treatments: List of treatment analyses (must match cases 1:1)

        Returns:
            Dictionary mapping circuit IDs to lists of treatments
        """
        circuit_groups: dict[str, list[TreatmentAnalysis]] = defaultdict(list)

        for case, treatment in zip(cases, treatments):
            court = case.get("court")
            circuit_id = self._extract_circuit_id(court)

            if circuit_id:
                circuit_groups[circuit_id].append(treatment)

        return circuit_groups

    def _analyze_circuit_treatment(
        self, circuit_id: str, treatments: list[TreatmentAnalysis]
    ) -> CircuitTreatment:
        """Analyze treatment pattern for a single circuit.

        Args:
            circuit_id: Circuit identifier (e.g., 'ca9')
            treatments: All treatments from this circuit

        Returns:
            CircuitTreatment summarizing this circuit's stance
        """
        total = len(treatments)
        positive = sum(1 for t in treatments if t.treatment_type == TreatmentType.POSITIVE)
        negative = sum(1 for t in treatments if t.treatment_type == TreatmentType.NEGATIVE)
        neutral = sum(1 for t in treatments if t.treatment_type == TreatmentType.NEUTRAL)

        # Determine dominant treatment
        counts = {
            TreatmentType.POSITIVE: positive,
            TreatmentType.NEGATIVE: negative,
            TreatmentType.NEUTRAL: neutral,
        }
        max_count = max(counts.values())
        dominant_candidates = [t for t, count in counts.items() if count == max_count]

        if len(dominant_candidates) > 1:
            dominant = TreatmentType.UNKNOWN
        elif positive == max_count and positive / total >= self.split_threshold:
            dominant = TreatmentType.POSITIVE
        elif negative == max_count and negative / total >= self.split_threshold:
            dominant = TreatmentType.NEGATIVE
        elif neutral == max_count:
            dominant = TreatmentType.NEUTRAL
        else:
            dominant = TreatmentType.UNKNOWN

        # Get representative cases (top by confidence, max 3)
        sorted_treatments = sorted(treatments, key=lambda t: t.confidence, reverse=True)
        representative = sorted_treatments[:3]

        # Calculate average confidence
        avg_confidence = sum(t.confidence for t in treatments) / total if total > 0 else 0.0

        return CircuitTreatment(
            circuit_id=circuit_id,
            circuit_name=CIRCUIT_COURTS.get(circuit_id, circuit_id.upper()),
            total_cases=total,
            positive_count=positive,
            negative_count=negative,
            neutral_count=neutral,
            dominant_treatment=dominant,
            representative_cases=representative,
            average_confidence=avg_confidence,
        )

    def _detect_split_type(
        self, circuit_treatments: dict[str, CircuitTreatment]
    ) -> tuple[str, float, list[str]]:
        """Detect the type and severity of circuit split.

        Args:
            circuit_treatments: Treatment analysis by circuit

        Returns:
            Tuple of (split_type, confidence, circuits_involved)
        """
        # Count circuits by dominant treatment
        treatment_counts: dict[TreatmentType, list[str]] = defaultdict(list)
        for circuit_id, treatment in circuit_treatments.items():
            if treatment.dominant_treatment != TreatmentType.UNKNOWN:
                treatment_counts[treatment.dominant_treatment].append(circuit_id)

        # Check for direct positive vs negative conflict
        has_positive = TreatmentType.POSITIVE in treatment_counts
        has_negative = TreatmentType.NEGATIVE in treatment_counts

        if has_positive and has_negative:
            # Direct conflict: Some circuits positive, others negative
            positive_circuits = treatment_counts[TreatmentType.POSITIVE]
            negative_circuits = treatment_counts[TreatmentType.NEGATIVE]

            # Higher confidence if multiple circuits on each side
            confidence = min(0.95, 0.5 + (len(positive_circuits) + len(negative_circuits)) * 0.1)

            return (
                "direct_conflict",
                confidence,
                positive_circuits + negative_circuits,
            )

        # Check for emerging split (one circuit differs from others)
        if len(treatment_counts) > 1:
            # Get majority and minority treatments
            sorted_treatments = sorted(
                treatment_counts.items(), key=lambda x: len(x[1]), reverse=True
            )
            majority_circuits = sorted_treatments[0][1]
            minority_circuits = sorted_treatments[1][1] if len(sorted_treatments) > 1 else []

            if len(minority_circuits) >= 1 and len(majority_circuits) >= 2:
                confidence = 0.7 if len(minority_circuits) == 1 else 0.8
                return (
                    "emerging_split",
                    confidence,
                    majority_circuits + minority_circuits,
                )

        # Potential split: Different treatments but not strong enough
        if len(treatment_counts) > 1:
            all_circuits = [c for circuits in treatment_counts.values() for c in circuits]
            return ("potential_split", 0.5, all_circuits)

        # No split detected
        return ("no_split", 0.0, [])

    def detect_circuit_split(
        self,
        citation: str,
        case_name: str,
        cases: list[CourtListenerCase],
        treatments: list[TreatmentAnalysis],
    ) -> tuple[CircuitSplit | None, int]:
        """Detect if there's a circuit split for the given case.

        Args:
            citation: Citation being analyzed
            case_name: Name of the case
            cases: List of citing cases
            treatments: Treatment analyses (must match cases 1:1)

        Returns:
            Tuple containing CircuitSplit if split detected (or None) and the number
            of circuits analyzed
        """
        if len(cases) != len(treatments):
            logger.warning(
                f"Mismatched cases and treatments: {len(cases)} cases, {len(treatments)} treatments"
            )
            return None, 0

        # Group by circuit
        circuit_groups = self._group_by_circuit(cases, treatments)

        # Filter circuits with enough cases
        circuit_treatments: dict[str, CircuitTreatment] = {}
        for circuit_id, circuit_treatments_list in circuit_groups.items():
            if len(circuit_treatments_list) >= self.min_cases_per_circuit:
                circuit_treatments[circuit_id] = self._analyze_circuit_treatment(
                    circuit_id, circuit_treatments_list
                )

        circuits_analyzed_count = len(circuit_treatments)

        # Need at least 2 circuits to have a split
        if circuits_analyzed_count < 2:
            return None, circuits_analyzed_count

        # Detect split type
        split_type, confidence, circuits_involved = self._detect_split_type(circuit_treatments)

        if split_type == "no_split":
            return None, circuits_analyzed_count

        # Build summary
        conflicting_descriptions = []
        for circuit_id in circuits_involved:
            treatment = circuit_treatments[circuit_id]
            dominant_str = treatment.dominant_treatment.value
            conflicting_descriptions.append(
                f"{treatment.circuit_name} ({treatment.positive_count}+ / "
                f"{treatment.negative_count}- / {treatment.neutral_count}0): {dominant_str}"
            )

        summary = f"{split_type.replace('_', ' ').title()}: " + "; ".join(
            conflicting_descriptions
        )

        # Assess Supreme Court likelihood
        supreme_court_likely = (
            split_type == "direct_conflict"
            and len(circuits_involved) >= 3
            and confidence >= 0.8
        )

        # Extract key cases
        key_cases: list[dict[str, object]] = []
        for circuit_id in circuits_involved[:4]:  # Max 4 circuits
            treatment = circuit_treatments[circuit_id]
            if treatment.representative_cases:
                best_case = treatment.representative_cases[0]
                key_cases.append(
                    {
                        "circuit": treatment.circuit_name,
                        "citation": best_case.citation,
                        "case_name": best_case.case_name,
                        "treatment": best_case.treatment_type.value,
                        "confidence": round(best_case.confidence, 2),
                        "excerpt": best_case.excerpt[:200] + "..."
                        if len(best_case.excerpt) > 200
                        else best_case.excerpt,
                    }
                )

        return CircuitSplit(
            citation=citation,
            case_name=case_name,
            split_type=split_type,
            confidence=round(confidence, 2),
            circuits_involved=circuits_involved,
            conflicting_circuits=circuit_treatments,
            summary=summary,
            supreme_court_likely=supreme_court_likely,
            key_cases=key_cases,
        ), circuits_analyzed_count
