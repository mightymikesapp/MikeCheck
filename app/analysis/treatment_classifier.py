"""Treatment classification for legal citations.

This module analyzes how citing cases treat a target case, classifying treatment as:
- Positive: Case is followed, affirmed, applied, or relied upon
- Negative: Case is overruled, questioned, criticized, or limited
- Neutral: Case is cited without clear positive or negative treatment
"""

import functools
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from app.types import CourtListenerCase, TreatmentStats

logger = logging.getLogger(__name__)

WELL_KNOWN_CASES = {
    "410 U.S. 113": "Roe v. Wade",
    "539 U.S. 558": "Lawrence v. Texas",
    "505 U.S. 833": "Planned Parenthood v. Casey",
}


class TreatmentType(Enum):
    """Classification of how a case treats another case."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


@dataclass
class TreatmentSignal:
    """A treatment signal found in text."""

    signal: str
    treatment_type: TreatmentType
    position: int
    context: str
    opinion_type: str = "majority"  # majority, concurrence, dissent


@dataclass
class TreatmentAnalysis:
    """Analysis of treatment for a single citing case."""

    case_name: str
    case_id: str
    citation: str
    treatment_type: TreatmentType
    confidence: float
    signals_found: list[TreatmentSignal]
    excerpt: str
    date_filed: str | None = None
    treatment_context: str = "unknown"  # majority, dissent_only, mixed, etc.
    opinion_breakdown: dict[str, TreatmentType] = field(default_factory=dict)


@dataclass
class AggregatedTreatment:
    """Aggregated treatment analysis across multiple citing cases."""

    citation: str
    is_good_law: bool
    confidence: float
    total_citing_cases: int
    positive_count: int
    negative_count: int
    neutral_count: int
    unknown_count: int
    negative_treatments: list[TreatmentAnalysis]
    positive_treatments: list[TreatmentAnalysis]
    summary: str
    treatment_context: str = "unknown"
    treatment_by_opinion_type: dict[str, TreatmentStats] = field(default_factory=dict)


# Treatment signal patterns with weights
NEGATIVE_SIGNALS = {
    r"\bdeclined\s+to\s+follow\b": ("declined to follow", 0.85),
    r"\brefused\s+to\s+follow\b": ("refused to follow", 0.85),
    r"\bdisagreed\s+with\b": ("disagreed with", 0.8),
    r"\boverruled\b": ("overruled", 1.0),
    r"\babrogated\b": ("abrogated", 1.0),
    r"\boverturned\b": ("overturned", 1.0),
    r"\breversed\b": ("reversed", 0.9),
    r"\bdisapproved\b": ("disapproved", 0.85),
    r"\brejected\b": ("rejected", 0.8),
    r"\bquestioned\b": ("questioned", 0.7),
    r"\bcriticized\b": ("criticized", 0.7),
    r"\blimited\s+to\b": ("limited to", 0.7),
    r"\bdistinguished\b": ("distinguished", 0.4),  # Reduced from 0.5
    r"\bno\s+longer\s+good\s+law\b": ("no longer good law", 1.0),
    r"\b(?:did\s+)?not\s+follow(?:ed)?\b": ("not followed", 0.85),
    r"\bsuperseded\b": ("superseded", 0.95),
    r"\bvacated\b": ("vacated", 0.9),
}

POSITIVE_SIGNALS = {
    r"\bfollowed\b": ("followed", 0.9),
    r"\baffirmed\b": ("affirmed", 0.9),
    r"\breaffirm(?:ed|s)?\b": ("reaffirmed", 0.95),
    r"\badopted\b": ("adopted", 0.85),
    r"\bapplied\b": ("applied", 0.8),
    r"\brelied\s+(?:up)?on\b": ("relied on", 0.85),
    r"\bconsistent\s+with\b": ("consistent with", 0.7),
    r"\bin\s+accord\s+with\b": ("in accord with", 0.8),
    r"\bagree\s+with\b": ("agree with", 0.8),
    r"\bsupport(?:s|ed|ing)\b": ("supports", 0.7),
    r"\bupheld\b": ("upheld", 0.9),
    r"\bconfirmed\b": ("confirmed", 0.85),
    r"\bcited\s+with\s+approval\b": ("cited with approval", 0.8),
    r"\bexplained\b": ("explained", 0.6),
    r"\bharmonized\b": ("harmonized", 0.7),
}


class TreatmentClassifier:
    """Classifier for determining how cases treat other cases."""

    def __init__(self) -> None:
        """Initialize the treatment classifier."""
        # Optimize signal patterns: Combine all into one regex
        # Sort by length descending to ensure specific patterns match first
        # (e.g. "declined to follow" before "follow")
        all_patterns = []
        for p, (s, w) in NEGATIVE_SIGNALS.items():
            all_patterns.append((p, s, w, TreatmentType.NEGATIVE))
        for p, (s, w) in POSITIVE_SIGNALS.items():
            all_patterns.append((p, s, w, TreatmentType.POSITIVE))

        all_patterns.sort(key=lambda x: len(x[0]), reverse=True)

        regex_parts = []
        self.group_map = {}
        for i, (p, s, w, t) in enumerate(all_patterns):
            # Strip leading/trailing \b for optimization to allow regex engine
            # to check boundary once
            pattern_body = p
            if pattern_body.startswith(r"\b"):
                pattern_body = pattern_body[2:]
            if pattern_body.endswith(r"\b"):
                pattern_body = pattern_body[:-2]

            group_name = f"s_{i}"
            regex_parts.append(f"(?P<{group_name}>{pattern_body})")
            self.group_map[group_name] = (s, w, t)

        # Combine all patterns into one regex wrapped in word boundaries
        self.combined_signal_pattern = re.compile(
            r"\b(?:" + "|".join(regex_parts) + r")\b", re.IGNORECASE
        )

        # Optimize negation patterns
        # Strip \b from start as we wrap in \b
        negation_patterns = [
            r"not\s+$",
            r"(?:did|does|do|will|would|could|can)\s+not\s+$",
            r"(?:did|does|do|will|would|could|can)n't\s+$",
            r"declined\s+to\s+$",
            r"refused\s+to\s+$",
        ]
        self.negation_pattern = re.compile(
            r"\b(?:" + "|".join(f"(?:{p})" for p in negation_patterns) + ")", re.IGNORECASE
        )

        # Optimize signal weight lookup (O(1))
        self.signal_weights = {}
        for s, w in NEGATIVE_SIGNALS.values():
            self.signal_weights[(s, TreatmentType.NEGATIVE)] = w
        for s, w in POSITIVE_SIGNALS.values():
            self.signal_weights[(s, TreatmentType.POSITIVE)] = w

    def should_fetch_full_text(
        self,
        initial_analysis: "TreatmentAnalysis",
        strategy: str,
    ) -> bool:
        """Determine if full text should be fetched for deeper analysis."""
        if strategy == "never":
            return False

        if strategy == "always":
            return True

        if strategy == "negative_only":
            return initial_analysis.treatment_type == TreatmentType.NEGATIVE

        if strategy == "smart":
            return (
                initial_analysis.treatment_type == TreatmentType.NEGATIVE
                or initial_analysis.confidence < 0.6
                or initial_analysis.treatment_type == TreatmentType.UNKNOWN
            )

        return False

    def _is_negated(self, text: str, position: int, window: int = 50) -> bool:
        """Check if a signal at the given position is negated."""
        start = max(0, position - window)
        preceding = text[start:position].lower()

        negation_patterns = [
            r"\bnot\s+$",
            r"\b(?:did|does|do|will|would|could|can)\s+not\s+$",
            r"\b(?:did|does|do|will|would|could|can)n't\s+$",
            r"\bdeclined\s+to\s+$",
            r"\brefused\s+to\s+$",
        ]

        for pattern in negation_patterns:
            if re.search(pattern, preceding):
                return True

        return False
        return bool(self.negation_pattern.search(preceding))

    def _get_court_weight(self, court_id: str | None) -> float:
        """Get weight multiplier based on court hierarchy."""
        if not court_id:
            return 0.8

        court_id = court_id.lower()
        if "scotus" in court_id or "us" == court_id:
            return 1.0
        if re.match(r"ca\d+", court_id) or "cir" in court_id:
            return 0.8
        if re.match(r"d\d+", court_id) or "dist" in court_id:
            return 0.6

        return 0.7

    def _map_opinion_type(self, op_type: str | None) -> str:
        """Map CourtListener opinion type to simplified category."""
        if not op_type:
            return "majority"
        op_type = op_type.lower()
        if "dissent" in op_type:
            return "dissent"
        if "concurrence" in op_type or "concurring" in op_type:
            return "concurrence"
        return "majority"  # lead, combined, per_curiam, etc.

    def extract_signals(
        self, text: str, citation: str, opinion_type: str = "majority"
    ) -> list[TreatmentSignal]:
        """Extract treatment signals from text mentioning the citation."""
            return 0.6  # District courts

        return 0.7  # State/other courts default

    @functools.lru_cache(maxsize=128)
    def _get_citation_patterns(self, citation: str) -> list[re.Pattern]:
        """Get compiled regex patterns for a citation (cached)."""
        citation_pattern = re.escape(citation).replace(r"\ ", r"\s+")
        patterns = [
            re.compile(citation_pattern, re.IGNORECASE),
        ]

        # Pattern 2: If citation is "XXX U.S. YYY", also try case name
        us_cite_match = re.match(r"(\d+)\s+U\.?S\.?\s+(\d+)", citation, re.IGNORECASE)
        if us_cite_match and citation in WELL_KNOWN_CASES:
            case_name = WELL_KNOWN_CASES[citation]
            patterns.append(
                re.compile(re.escape(case_name).replace(r"\ ", r"\s+"), re.IGNORECASE)
            )
        return patterns

    def extract_signals(self, text: str, citation: str) -> list[TreatmentSignal]:
        """Extract treatment signals from text mentioning the citation.

        Args:
            text: Text to analyze
            citation: The citation being analyzed

        Returns:
            List of treatment signals found
        """
        signals: list[TreatmentSignal] = []
        contexts = self._extract_citation_contexts(text, citation)

        for context, position in contexts:
            # Check for negative signals
            for pattern, (signal, weight) in self.negative_patterns.items():
                for match in pattern.finditer(context):
                    if self._is_negated(context, match.start()):
                        continue
                    signals.append(
                        TreatmentSignal(
                            signal=signal,
                            treatment_type=TreatmentType.NEGATIVE,
                            position=position,
                            context=context[:200],
                            opinion_type=opinion_type,
                        )
                    )

            # Check for positive signals
            for pattern, (signal, weight) in self.positive_patterns.items():
                for match in pattern.finditer(context):
                    if self._is_negated(context, match.start()):
                        continue
                    signals.append(
                        TreatmentSignal(
                            signal=signal,
                            treatment_type=TreatmentType.POSITIVE,
                            position=position,
                            context=context[:200],
                            opinion_type=opinion_type,
                        )
                    )
            # Use combined regex for single-pass extraction (O(L) instead of O(L*P))
            for match in self.combined_signal_pattern.finditer(context):
                group_name = match.lastgroup
                if not group_name:
                    continue

                signal, _, treatment_type = self.group_map[group_name]

                # Check for negation
                if self._is_negated(context, match.start()):
                    continue

                signals.append(
                    TreatmentSignal(
                        signal=signal,
                        treatment_type=treatment_type,
                        position=position,
                        context=context[:200],  # First 200 chars
                    )
                )

        return signals

    def classify_treatment(
        self,
        citing_case: CourtListenerCase,
        target_citation: str,
        full_text: str | None = None,
    ) -> TreatmentAnalysis:
        """Classify how a citing case treats the target citation.

        If full_text is provided, it's used as a single blob (usually for legacy compatibility).
        Ideally, we use the structured opinions in citing_case.
        """
        all_signals: list[TreatmentSignal] = []
        opinion_breakdown: dict[str, TreatmentType] = {}

        # 1. Extract signals
        if full_text:
            # If explicit full text provided, assume majority/combined
            logger.debug(f"Using full text ({len(full_text)} chars) for analysis")
            signals = self.extract_signals(full_text, target_citation, "majority")
            all_signals.extend(signals)
            opinion_breakdown["majority"] = self._aggregate_signals(signals)[0]

        elif citing_case.get("opinions"):
            # Process structured opinions
            for opinion in citing_case["opinions"]:
                # Opinion text might be in snippet, plain_text, or html
                op_text = (
                    opinion.get("snippet")
                    or opinion.get("plain_text")
                    or str(opinion.get("html_lawbox") or "")
                )
                if not op_text:
                    continue

                op_type = self._map_opinion_type(opinion.get("type"))
                signals = self.extract_signals(op_text, target_citation, op_type)
                all_signals.extend(signals)

                # Determine treatment for this specific opinion
                op_treatment, _ = self._aggregate_signals(signals)
                # Only record if meaningful (not neutral/unknown, unless it's the only one)
                if op_treatment != TreatmentType.NEUTRAL or op_type not in opinion_breakdown:
                    opinion_breakdown[op_type] = op_treatment

        else:
            # Fallback to legacy fields
            text_parts = []
            if citing_case.get("syllabus"):
                text_parts.append(citing_case["syllabus"])
            if citing_case.get("plain_text"):
                text_parts.append(citing_case["plain_text"])
            if citing_case.get("snippet"):
                text_parts.append(citing_case["snippet"])

            text = "\n\n".join(text_parts)
            signals = self.extract_signals(text, target_citation, "majority")
            all_signals.extend(signals)
            opinion_breakdown["majority"] = self._aggregate_signals(signals)[0]

        # 2. Determine Overall Treatment Context
        # Logic: Majority > Concurrence > Dissent
        majority_treatment = opinion_breakdown.get("majority", TreatmentType.NEUTRAL)
        concurrence_treatment = opinion_breakdown.get("concurrence", TreatmentType.NEUTRAL)
        dissent_treatment = opinion_breakdown.get("dissent", TreatmentType.NEUTRAL)

        treatment_context = "neutral"
        final_treatment = TreatmentType.NEUTRAL
        final_confidence = 0.5
        court_weight = self._get_court_weight(citing_case.get("court"))

        if majority_treatment == TreatmentType.NEGATIVE:
            treatment_context = "majority_negative"
            final_treatment = TreatmentType.NEGATIVE
            _, conf = self._aggregate_signals([s for s in all_signals if s.opinion_type == "majority"])
            final_confidence = conf

        elif majority_treatment == TreatmentType.POSITIVE:
            treatment_context = "majority_positive"
            final_treatment = TreatmentType.POSITIVE
            _, conf = self._aggregate_signals([s for s in all_signals if s.opinion_type == "majority"])
            final_confidence = conf
            if dissent_treatment == TreatmentType.NEGATIVE:
                treatment_context = "majority_positive_dissent_negative"

        elif dissent_treatment == TreatmentType.NEGATIVE:
            # Negative ONLY in dissent (or concurrence)
            treatment_context = "dissent_negative_only"
            # The case citing it generally stands, but dissent criticizes.
            # We mark the case's treatment as NEGATIVE but with context "dissent_negative_only"
            # Wait, if we mark it NEGATIVE, it counts as a negative citing case.
            # But `aggregate_treatments` will handle the "is_good_law" logic.
            # For the individual case analysis, it IS a negative treatment (by the dissent).
            # But maybe we should return NEUTRAL or MIXED for the case itself?
            # "The tool classifies treatment as Positive, Negative, Neutral".
            # If I say Negative, it implies the case is negative.
            # Let's say Negative, but with lower confidence?
            final_treatment = TreatmentType.NEGATIVE
            _, conf = self._aggregate_signals([s for s in all_signals if s.opinion_type == "dissent"])
            final_confidence = conf * 0.5  # Discount dissent confidence

        elif concurrence_treatment == TreatmentType.NEGATIVE:
            treatment_context = "concurrence_negative_only"
            final_treatment = TreatmentType.NEGATIVE
            _, conf = self._aggregate_signals([s for s in all_signals if s.opinion_type == "concurrence"])
            final_confidence = conf * 0.7

        else:
            # Fallback to simple aggregation of all signals if no clear breakdown
            final_treatment, final_confidence = self._aggregate_signals(all_signals, court_weight)
            if final_treatment == TreatmentType.NEGATIVE:
                treatment_context = "majority_negative" # assume majority if unsure
            elif final_treatment == TreatmentType.POSITIVE:
                treatment_context = "majority_positive"

        excerpt = self._extract_best_excerpt("", target_citation, all_signals)

        return TreatmentAnalysis(
            case_name=citing_case.get("caseName", "Unknown"),
            case_id=str(citing_case.get("id", "")),
            citation=citing_case.get("citation", [""])[0] if citing_case.get("citation") else "",
            treatment_type=final_treatment,
            confidence=final_confidence,
            signals_found=all_signals,
            excerpt=excerpt,
            date_filed=citing_case.get("dateFiled"),
            treatment_context=treatment_context,
            opinion_breakdown=opinion_breakdown,
        )

    def aggregate_treatments(
        self,
        treatments: list[TreatmentAnalysis],
        target_citation: str,
    ) -> AggregatedTreatment:
        """Aggregate multiple treatment analyses into overall assessment.

        Majority/lead opinions drive core validity.
        Concurrences/dissents influence warnings/confidence but don't flip validity alone.
        """
        positive_count = sum(1 for t in treatments if t.treatment_type == TreatmentType.POSITIVE)
        negative_count = sum(1 for t in treatments if t.treatment_type == TreatmentType.NEGATIVE)
        neutral_count = sum(1 for t in treatments if t.treatment_type == TreatmentType.NEUTRAL)
        unknown_count = sum(1 for t in treatments if t.treatment_type == TreatmentType.UNKNOWN)

        negative_treatments = [t for t in treatments if t.treatment_type == TreatmentType.NEGATIVE]
        positive_treatments = [t for t in treatments if t.treatment_type == TreatmentType.POSITIVE]

        # Calculate Breakdown by Opinion Type
        # We need to sum up stats across all cases
        breakdown: dict[str, TreatmentStats] = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0})

        for t in treatments:
            for op_type, treatment in t.opinion_breakdown.items():
                if treatment == TreatmentType.POSITIVE:
                    breakdown[op_type]["positive"] += 1
                elif treatment == TreatmentType.NEGATIVE:
                    breakdown[op_type]["negative"] += 1
                elif treatment == TreatmentType.NEUTRAL:
                    breakdown[op_type]["neutral"] += 1

        # Determine Validity
        # Only Majority/Lead negatives flip validity
        critical_negative_cases = [
            t for t in negative_treatments
            if t.confidence >= 0.7 and "dissent" not in t.treatment_context
        ]

        # Check for "majority_negative" context explicitly
        strong_majority_negative = any(
            t.treatment_context == "majority_negative" and t.confidence >= 0.7
            for t in negative_treatments
        )

        is_good_law = not (strong_majority_negative or len(critical_negative_cases) > 1)

        # Calculate overall confidence
        confidence = 0.7
        if not is_good_law:
            confidence = max((t.confidence for t in critical_negative_cases), default=0.8)
        else:
            # It is good law, but are there warnings?
            dissent_negatives = [t for t in negative_treatments if "dissent" in t.treatment_context]
            if dissent_negatives:
                # Reduce confidence slightly
                confidence = 0.85
            elif positive_count > negative_count * 2:
                confidence = 0.95

        # Determine overall context label
        overall_context = "neutral"
        if not is_good_law:
            overall_context = "majority_negative"
        elif any(t.treatment_context == "dissent_negative_only" for t in negative_treatments):
            overall_context = "dissent_negative_only"
        elif positive_count > 0:
            overall_context = "majority_positive"

        summary = self._generate_summary(
            positive_count,
            negative_count,
            neutral_count,
            is_good_law,
            negative_treatments,
            overall_context
        )

        return AggregatedTreatment(
            citation=target_citation,
            is_good_law=is_good_law,
            confidence=min(confidence, 0.95),
            total_citing_cases=len(treatments),
            positive_count=positive_count,
            negative_count=negative_count,
            neutral_count=neutral_count,
            unknown_count=unknown_count,
            negative_treatments=negative_treatments,
            positive_treatments=positive_treatments,
            summary=summary,
            treatment_context=overall_context,
            treatment_by_opinion_type=dict(breakdown),
        )

    def _extract_citation_contexts(
        self,
        text: str,
        citation: str,
        window: int = 400,
    ) -> list[tuple[str, int]]:
        """Extract context windows around mentions of the citation."""
        contexts = []
        citation_pattern = re.escape(citation).replace(r"\ ", r"\s+")
        patterns_to_try = [re.compile(citation_pattern, re.IGNORECASE)]

        us_cite_match = re.match(r"(\d+)\s+U\.?S\.?\s+(\d+)", citation, re.IGNORECASE)
        if us_cite_match:
            well_known_cases = {
                "410 U.S. 113": "Roe v. Wade",
                "539 U.S. 558": "Lawrence v. Texas",
                "505 U.S. 833": "Planned Parenthood v. Casey",
            }
            if citation in well_known_cases:
                case_name = well_known_cases[citation]
                patterns_to_try.append(
                    re.compile(re.escape(case_name).replace(r"\ ", r"\s+"), re.IGNORECASE)
                )

        # Get cached patterns
        patterns_to_try = self._get_citation_patterns(citation)

        for pattern in patterns_to_try:
            for match in pattern.finditer(text):
                start = max(0, match.start() - window)
                end = min(len(text), match.end() + window)
                context = text[start:end]
                contexts.append((context, match.start()))

        return contexts if contexts else [(text[:500], 0)]

    def _aggregate_signals(
        self,
        signals: list[TreatmentSignal],
        court_weight: float = 1.0,
    ) -> tuple[TreatmentType, float]:
        """Aggregate signals into overall treatment type and confidence."""
        if not signals:
            return TreatmentType.NEUTRAL, 0.5

        negative_signals = [s for s in signals if s.treatment_type == TreatmentType.NEGATIVE]
        positive_signals = [s for s in signals if s.treatment_type == TreatmentType.POSITIVE]

        if negative_signals:
            strongest = max(
                negative_signals,
                key=lambda s: self._get_signal_weight(s.signal, TreatmentType.NEGATIVE),
            )
            weight = self._get_signal_weight(strongest.signal, TreatmentType.NEGATIVE)
            return TreatmentType.NEGATIVE, weight * court_weight

        elif positive_signals:
            strongest = max(
                positive_signals,
                key=lambda s: self._get_signal_weight(s.signal, TreatmentType.POSITIVE),
            )
            weight = self._get_signal_weight(strongest.signal, TreatmentType.POSITIVE)
            return TreatmentType.POSITIVE, weight * court_weight

        return TreatmentType.NEUTRAL, 0.5

    def _get_signal_weight(self, signal: str, treatment_type: TreatmentType) -> float:
        signals_dict = (
            NEGATIVE_SIGNALS if treatment_type == TreatmentType.NEGATIVE else POSITIVE_SIGNALS
        )
        for pattern_text, (sig, weight) in signals_dict.items():
            if sig == signal:
                return weight
        return 0.5
        """Get the weight for a signal.

        Args:
            signal: Signal text
            treatment_type: Type of treatment

        Returns:
            Weight between 0 and 1
        """
        # Optimized O(1) lookup
        return self.signal_weights.get((signal, treatment_type), 0.5)

    def _extract_best_excerpt(
        self,
        text: str,
        citation: str,
        signals: list[TreatmentSignal],
    ) -> str:
        if signals:
            best_signal = max(
                signals,
                key=lambda s: self._get_signal_weight(s.signal, s.treatment_type),
            )
            return best_signal.context
        return ""

    def _generate_summary(
        self,
        positive_count: int,
        negative_count: int,
        neutral_count: int,
        is_good_law: bool,
        negative_treatments: list[TreatmentAnalysis],
        context: str = "neutral",
    ) -> str:
        """Generate human-readable summary of treatment analysis."""
        if not is_good_law:
            signals = ", ".join(
                set(s.signal for t in negative_treatments for s in t.signals_found[:2])
            )
            return (
                f"⚠️  Case may not be good law. Found {negative_count} negative treatment(s) "
                f"including: {signals}. Recommend manual review."
            )

        if context == "dissent_negative_only":
            return (
                f"⚠️  Case is valid, but negative commentary appears in dissenting opinions. "
                f"Found {negative_count} negative signal(s) in dissents."
            )

        if negative_count > 0:
            return (
                f"⚡ Case appears to be good law but has {negative_count} negative treatment(s). "
                f"Also {positive_count} positive, {neutral_count} neutral citations."
            )

        if positive_count > 5:
            return (
                f"✓ Case appears to be good law with strong positive treatment "
                f"({positive_count} positive citations)."
            )

        return (
            f"Case cited {positive_count + negative_count + neutral_count} times "
            f"with no significant negative treatment."
        )
