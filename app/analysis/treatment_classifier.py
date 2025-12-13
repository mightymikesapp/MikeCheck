"""Treatment classification for legal citations.

This module analyzes how citing cases treat a target case, classifying treatment as:
- Positive: Case is followed, affirmed, applied, or relied upon
- Negative: Case is overruled, questioned, criticized, or limited
- Neutral: Case is cited without clear positive or negative treatment
"""

import bisect
import functools
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from app.analysis.document_processing import FootnoteParser
from app.types import CourtListenerCase, TreatmentStats

logger = logging.getLogger(__name__)

LocationType = Literal["body", "footnote"]

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
    location_type: LocationType = "body"


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
    location_type: LocationType = "body"  # indicates primary location of signals


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
            r"(?:did|does|do|will|would|could|ca)n't\s+$",
            r"declin(?:ed|e)\s+to\s+$",
            r"refus(?:ed|e)\s+to\s+$",
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

        # For legacy compatibility or if iterative checks are restored
        self.negative_patterns = {
            re.compile(p, re.IGNORECASE): (s, w) for p, (s, w) in NEGATIVE_SIGNALS.items()
        }
        self.positive_patterns = {
            re.compile(p, re.IGNORECASE): (s, w) for p, (s, w) in POSITIVE_SIGNALS.items()
        }

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
        """
        Determine whether a detected signal is negated by nearby preceding text.

        Parameters:
            text (str): Full text containing the signal.
            position (int): Character index in `text` where the signal was detected.
            window (int): Number of characters before `position` to inspect for negation indicators (default 50).

        Returns:
            bool: True if a negation indicator is found within the preceding window, False otherwise.
        """
        start = max(0, position - window)
        preceding = text[start:position].lower()
        return bool(self.negation_pattern.search(preceding))

    def _get_court_weight(self, court_id: str | None) -> float:
        """
        Compute a weight multiplier representing the hierarchical importance of a court.

        Parameters:
            court_id (str | None): Identifier for the court (e.g., "scotus", "us", "ca9", "d2", "dist"). If None or empty, a default intermediate weight is used.

        Returns:
            float: Weight used to scale confidence by court authority:
                - 1.0 for the U.S. Supreme Court ("scotus" or "us"),
                - 0.8 for federal appellate courts ("caN" or containing "cir") or when `court_id` is missing,
                - 0.6 for district-level courts ("dN" or containing "dist"),
                - 0.7 for other/unrecognized court identifiers.
        """
        if not court_id:
            return 0.8

        court_id = court_id.lower()
        if "scotus" in court_id or "us" == court_id:
            return 1.0
        if re.match(r"ca\d+", court_id) or "cir" in court_id:
            return 0.8
        if re.match(r"d\d+", court_id) or "dist" in court_id:
            return 0.6

        return 0.7  # State/other courts default

    def _map_opinion_type(self, op_type: str | None) -> str:
        """
        Normalize a raw CourtListener opinion type into a simplified category.

        Parameters:
                op_type (str | None): Raw opinion type string from CourtListener (may be None).

        Returns:
                str: One of "majority", "dissent", or "concurrence" corresponding to the simplified opinion category.
        """
        if not op_type:
            return "majority"
        op_type = op_type.lower()
        if "dissent" in op_type:
            return "dissent"
        if "concurrence" in op_type or "concurring" in op_type:
            return "concurrence"
        return "majority"  # lead, combined, per_curiam, etc.

    @functools.lru_cache(maxsize=128)
    def _get_citation_patterns(self, citation: str) -> list[re.Pattern[str]]:
        """Get compiled regex patterns for a citation (cached)."""
        """Return compiled regular-expression patterns to locate mentions of a citation in text.

        Always includes a pattern that matches the exact citation with flexible whitespace (e.g., spaces or tabs). If the citation matches a US-style reporter pattern like "123 U.S. 456" and is present in WELL_KNOWN_CASES, also includes a pattern that matches the corresponding well-known case name.

        Args:
            citation (str): The citation string to compile patterns for.

        Returns:
            list[re.Pattern]: Compiled regex patterns that match the citation and, when applicable, its well-known case name. This function's results are cached.
        """
        citation_pattern = re.escape(citation).replace(r"\ ", r"\s+")
        patterns = [
            re.compile(citation_pattern, re.IGNORECASE),
        ]

        # Pattern 2: If citation is "XXX U.S. YYY", also try case name
        us_cite_match = re.match(r"(\d+)\s+U\.?S\.?\s+(\d+)", citation, re.IGNORECASE)
        if us_cite_match and citation in WELL_KNOWN_CASES:
            case_name = WELL_KNOWN_CASES[citation]
            patterns.append(re.compile(re.escape(case_name).replace(r"\ ", r"\s+"), re.IGNORECASE))
        return patterns

    def extract_signals(
        self,
        text: str,
        citation: str,
        opinion_type: str = "majority",
        location_type: LocationType = "body",
    ) -> list[TreatmentSignal]:
        """Extract treatment signals for a specific citation.

        Extracts treatment signals for a specific citation from the provided text.

        Args:
            text: Text to search for mentions of the citation.
            citation: Citation string to locate and analyze within the text.
            opinion_type: Opinion category to attach to extracted signals (e.g., "majority", "dissent", "concurrence").
            location_type: Location of the text (e.g., "body", "footnote") to track citation authority.

        Returns:
            A list of :class:`TreatmentSignal` instances including the normalized signal
            name, inferred treatment type, position, a context excerpt, and the
            supplied ``opinion_type`` and ``location_type``.
        """
        signals: list[TreatmentSignal] = []

        # 1. Find all citation matches
        patterns = self._get_citation_patterns(citation)
        citation_matches = []
        for pattern in patterns:
            for match in pattern.finditer(text):
                citation_matches.append(match)

        if not citation_matches:
            # Fallback: scan beginning of text if no citation found
            # Matches original behavior of checking text[:500]
            search_regions = [(0, min(500, len(text)))]
            citation_positions = [0]
        else:
            # Sort matches by start position
            citation_matches.sort(key=lambda m: m.start())
            citation_positions = [m.start() for m in citation_matches]

            # 2. Calculate search regions (merge overlapping windows)
            window = 400
            regions = []
            for match in citation_matches:
                start = max(0, match.start() - window)
                end = min(len(text), match.end() + window)
                regions.append((start, end))

            # Merge regions
            merged_regions = []
            if regions:
                curr_start, curr_end = regions[0]
                for start, end in regions[1:]:
                    if start <= curr_end:  # Overlap or adjacent
                        curr_end = max(curr_end, end)
                    else:
                        merged_regions.append((curr_start, curr_end))
                        curr_start, curr_end = start, end
                merged_regions.append((curr_start, curr_end))
            search_regions = merged_regions

        # 3. Scan regions for signals
        for start, end in search_regions:
            region_text = text[start:end]

            for match in self.combined_signal_pattern.finditer(region_text):
                # match.start() is relative to region_text start
                # Absolute position
                abs_start = start + match.start()

                # Check for negation
                # _is_negated checks text[...:position] relative to the passed text
                if self._is_negated(region_text, match.start()):
                    continue

                group_name = match.lastgroup
                if not group_name:
                    continue

                signal, _, treatment_type = self.group_map[group_name]

                # Find nearest citation for 'position' field
                # citation_positions is sorted.
                # Use bisect to find insertion point
                idx = bisect.bisect_left(citation_positions, abs_start)
                # Candidates: idx-1 and idx
                candidates = []
                if idx < len(citation_positions):
                    candidates.append(citation_positions[idx])
                if idx > 0:
                    candidates.append(citation_positions[idx - 1])

                nearest_pos = candidates[0] if candidates else 0
                if len(candidates) > 1:
                    # Pick closest
                    if abs(candidates[1] - abs_start) < abs(candidates[0] - abs_start):
                        nearest_pos = candidates[1]

                # Create context excerpt centered on signal
                # +/- 100 chars
                ctx_start = max(0, match.start() - 100)
                ctx_end = min(len(region_text), match.end() + 100)
                excerpt = region_text[ctx_start:ctx_end]

                signals.append(
                    TreatmentSignal(
                        signal=signal,
                        treatment_type=treatment_type,
                        position=nearest_pos,
                        context=excerpt,
                        opinion_type=opinion_type,
                        location_type=location_type,
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

        Args:
            citing_case: CourtListener response containing the citing opinion(s).
            target_citation: The citation we want to analyze.
            full_text: Optional pre-combined text of the citing case; if provided, it is
                analyzed directly instead of the structured opinion fields.

        Returns:
            A :class:`TreatmentAnalysis` summarizing detected treatment signals and
            derived confidence scores.
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
                op_type = self._map_opinion_type(opinion.get("type"))

                # Try to parse HTML to separate body from footnotes
                html_lawbox = opinion.get("html_lawbox")
                if html_lawbox:
                    try:
                        # Parse HTML to separate body and footnotes
                        parsed = FootnoteParser.parse_html(html_lawbox)

                        # Extract signals from body
                        body_signals = self.extract_signals(
                            parsed.body_text, target_citation, op_type, location_type="body"
                        )
                        all_signals.extend(body_signals)

                        # Extract signals from footnotes
                        footnote_signals: list[TreatmentSignal] = []
                        if parsed.footnote_text:
                            footnote_signals = self.extract_signals(
                                parsed.footnote_text,
                                target_citation,
                                op_type,
                                location_type="footnote",
                            )
                            all_signals.extend(footnote_signals)

                        # Determine treatment for this opinion with body precedence
                        if body_signals:
                            op_treatment, _ = self._aggregate_signals(body_signals)
                        elif footnote_signals:
                            op_treatment, _ = self._aggregate_signals(footnote_signals)
                        else:
                            op_treatment = TreatmentType.NEUTRAL

                    except Exception as e:
                        logger.warning(f"Failed to parse html_lawbox, falling back to plain text: {e}")
                        # Fallback to plain text
                        op_text = opinion.get("plain_text") or opinion.get("snippet") or ""
                        if op_text:
                            signals = self.extract_signals(op_text, target_citation, op_type)
                            all_signals.extend(signals)
                            op_treatment, _ = self._aggregate_signals(signals)
                        else:
                            continue
                else:
                    # Fallback: Try plain text with heuristic parsing
                    plain_text = opinion.get("plain_text")
                    if plain_text:
                        try:
                            parsed = FootnoteParser.parse_plain_text_fallback(plain_text)

                            # Extract signals from body
                            body_signals = self.extract_signals(
                                parsed.body_text, target_citation, op_type, location_type="body"
                            )
                            all_signals.extend(body_signals)

                            # Extract signals from footnotes if detected
                            footnote_signals = []
                            if parsed.footnote_text:
                                footnote_signals = self.extract_signals(
                                    parsed.footnote_text,
                                    target_citation,
                                    op_type,
                                    location_type="footnote",
                                )
                                all_signals.extend(footnote_signals)

                            if body_signals:
                                op_treatment, _ = self._aggregate_signals(body_signals)
                            elif footnote_signals:
                                op_treatment, _ = self._aggregate_signals(footnote_signals)
                            else:
                                op_treatment = TreatmentType.NEUTRAL

                        except Exception as e:
                            logger.warning(f"Failed to parse plain text for footnotes: {e}")
                            # Final fallback: treat entire text as body
                            signals = self.extract_signals(plain_text, target_citation, op_type)
                            all_signals.extend(signals)
                            op_treatment, _ = self._aggregate_signals(signals)
                    else:
                        # Last resort: use snippet
                        op_text = opinion.get("snippet") or ""
                        if not op_text:
                            continue
                        signals = self.extract_signals(op_text, target_citation, op_type)
                        all_signals.extend(signals)
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
            _, conf = self._aggregate_signals(
                [s for s in all_signals if s.opinion_type == "majority"],
                court_weight,
            )
            final_confidence = conf

        elif majority_treatment == TreatmentType.POSITIVE:
            treatment_context = "majority_positive"
            final_treatment = TreatmentType.POSITIVE
            _, conf = self._aggregate_signals(
                [s for s in all_signals if s.opinion_type == "majority"],
                court_weight,
            )
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
            _, conf = self._aggregate_signals(
                [s for s in all_signals if s.opinion_type == "dissent"]
            )
            final_confidence = conf * 0.5  # Discount dissent confidence

        elif concurrence_treatment == TreatmentType.NEGATIVE:
            treatment_context = "concurrence_negative_only"
            final_treatment = TreatmentType.NEGATIVE
            _, conf = self._aggregate_signals(
                [s for s in all_signals if s.opinion_type == "concurrence"]
            )
            final_confidence = conf * 0.7

        else:
            # Fallback to simple aggregation of all signals if no clear breakdown
            final_treatment, final_confidence = self._aggregate_signals(all_signals, court_weight)
            if final_treatment == TreatmentType.NEGATIVE:
                treatment_context = "majority_negative"  # assume majority if unsure
            elif final_treatment == TreatmentType.POSITIVE:
                treatment_context = "majority_positive"

        # 3. Determine primary location type and apply footnote confidence adjustment
        body_signals = [s for s in all_signals if s.location_type == "body"]
        footnote_signals = [s for s in all_signals if s.location_type == "footnote"]

        body_treatment, body_confidence = (
            self._aggregate_signals(body_signals, court_weight)
            if body_signals
            else (TreatmentType.NEUTRAL, 0.0)
        )
        footnote_treatment, footnote_confidence = (
            self._aggregate_signals(footnote_signals, court_weight)
            if footnote_signals
            else (TreatmentType.NEUTRAL, 0.0)
        )

        # Determine primary location based on where signals were found (body precedence)
        primary_location: LocationType = (
            "body" if body_signals else "footnote" if footnote_signals else "body"
        )

        # Apply confidence adjustment if negative signals are found only in footnotes
        # Per requirements: downgrade confidence by 0.2 for footnote-only negative signals
        negative_signals = [s for s in all_signals if s.treatment_type == TreatmentType.NEGATIVE]
        if negative_signals:
            negative_in_body = any(s.location_type == "body" for s in negative_signals)
            negative_in_footnotes = any(s.location_type == "footnote" for s in negative_signals)

            if negative_in_footnotes and not negative_in_body:
                # If body contains any signals, let it dictate treatment, then downgrade confidence
                if body_signals:
                    final_treatment = body_treatment
                    final_confidence = body_confidence
                    primary_location = "body"
                else:
                    final_confidence = footnote_confidence
                    primary_location = "footnote"

                logger.info(
                    f"Negative treatment signals found only in footnotes for {citing_case.get('caseName', 'Unknown')}. "
                    f"Reducing confidence from {final_confidence:.2f} to {max(0.0, final_confidence - 0.2):.2f}"
                )
                final_confidence = max(0.0, final_confidence - 0.2)

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
            location_type=primary_location,
        )

    def aggregate_treatments(
        self,
        treatments: list[TreatmentAnalysis],
        target_citation: str,
    ) -> AggregatedTreatment:
        """
        Combine multiple TreatmentAnalysis objects into a single AggregatedTreatment summarizing counts, overall context, confidence, and good-law determination.

        Aggregates per-case treatment classifications and per-opinion breakdowns, identifies critical negative treatments (majority/lead negative opinions with high confidence) that make the target citation not good law, and computes an overall confidence score and human-readable summary.

        Parameters:
            treatments (list[TreatmentAnalysis]): Analyses of individual citing cases to aggregate.
            target_citation (str): The citation being summarized.

        Returns:
            AggregatedTreatment: Summary for the target citation including is_good_law, confidence, counts by treatment type, lists of positive and negative TreatmentAnalysis, a textual summary, overall treatment context, and treatment-by-opinion-type breakdown.
        """
        positive_count = sum(1 for t in treatments if t.treatment_type == TreatmentType.POSITIVE)
        negative_count = sum(1 for t in treatments if t.treatment_type == TreatmentType.NEGATIVE)
        neutral_count = sum(1 for t in treatments if t.treatment_type == TreatmentType.NEUTRAL)
        unknown_count = sum(1 for t in treatments if t.treatment_type == TreatmentType.UNKNOWN)

        negative_treatments = [t for t in treatments if t.treatment_type == TreatmentType.NEGATIVE]
        positive_treatments = [t for t in treatments if t.treatment_type == TreatmentType.POSITIVE]

        # Calculate Breakdown by Opinion Type
        # We need to sum up stats across all cases
        breakdown: dict[str, TreatmentStats] = defaultdict(
            lambda: {"positive": 0, "negative": 0, "neutral": 0}
        )

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
            t
            for t in negative_treatments
            if t.confidence >= 0.7 and "dissent" not in t.treatment_context
        ]

        # Check for "majority_negative" context explicitly
        strong_majority_negative = any(
            t.treatment_context == "majority_negative" and t.confidence >= 0.7
            for t in negative_treatments
        )

        is_good_law = not (strong_majority_negative or len(critical_negative_cases) > 0)

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
            overall_context,
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

    def _aggregate_signals(
        self,
        signals: list[TreatmentSignal],
        court_weight: float = 1.0,
    ) -> tuple[TreatmentType, float]:
        """
        Determine the overall treatment type and a confidence score from a list of extracted treatment signals.

        Given extracted TreatmentSignal objects, the function chooses the strongest negative signal (if any) to classify the treatment as NEGATIVE, otherwise the strongest positive signal (if any) to classify as POSITIVE. If no signals are present, it returns NEUTRAL with a default confidence.

        Parameters:
            signals (list[TreatmentSignal]): Extracted signals to aggregate.
            court_weight (float): Multiplier (typically 0.0-1.0+) applied to the selected signal's weight to adjust confidence based on the citing court's importance.

        Returns:
            tuple[TreatmentType, float]: A pair of the aggregated TreatmentType and a confidence score between 0 and 1 (default 0.5 when neutral).
        """
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
        """Return the predefined weight for a normalized treatment signal.

        Retrieve the predefined weight for a normalized treatment signal.

        Args:
            signal: Normalized signal name.
            treatment_type: TreatmentType enum indicating positive or negative signal.

        Returns:
            Weight between 0 and 1 for the signal; returns 0.5 if the signal
            is not found.
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
        """Generate a concise, human-readable treatment summary."""

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
