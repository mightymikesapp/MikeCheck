
import re
import time
import timeit
from app.analysis.treatment_classifier import TreatmentClassifier

# Mock data
LONG_TEXT = "This is a long legal text " * 1000 + "not followed" + " by the court." * 1000
POSITION = len("This is a long legal text " * 1000 + "not followed")
COURT_IDS = ["scotus", "ca9", "d1", "Supreme Court", "District Court", None, "unknown"] * 1000

def current_is_negated(classifier, text, position, window=50):
    start = max(0, position - window)
    preceding = text[start:position].lower()
    return bool(classifier.negation_pattern.search(preceding))

def optimized_is_negated(classifier, text, position, window=50):
    start = max(0, position - window)
    preceding = text[start:position]
    return bool(classifier.negation_pattern.search(preceding))

def benchmark_is_negated():
    classifier = TreatmentClassifier()

    # Warmup
    current_is_negated(classifier, LONG_TEXT, POSITION)
    optimized_is_negated(classifier, LONG_TEXT, POSITION)

    t1 = timeit.timeit(lambda: current_is_negated(classifier, LONG_TEXT, POSITION), number=10000)
    t2 = timeit.timeit(lambda: optimized_is_negated(classifier, LONG_TEXT, POSITION), number=10000)

    print(f"is_negated (10k runs):")
    print(f"Current:   {t1:.4f}s")
    print(f"Optimized: {t2:.4f}s")
    print(f"Improvement: {(t1 - t2) / t1 * 100:.2f}%")

def current_get_court_weight(court_id):
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

# Pre-compiled patterns
CA_PATTERN = re.compile(r"ca\d+")
DIST_PATTERN = re.compile(r"d\d+")

def optimized_get_court_weight(court_id):
    if not court_id:
        return 0.8

    court_id = court_id.lower()
    if "scotus" in court_id or "us" == court_id:
        return 1.0
    if CA_PATTERN.match(court_id) or "cir" in court_id:
        return 0.8
    if DIST_PATTERN.match(court_id) or "dist" in court_id:
        return 0.6

    return 0.7

def benchmark_court_weight():
    t1 = timeit.timeit(lambda: [current_get_court_weight(cid) for cid in COURT_IDS], number=100)
    t2 = timeit.timeit(lambda: [optimized_get_court_weight(cid) for cid in COURT_IDS], number=100)

    print(f"get_court_weight (100 loops of {len(COURT_IDS)} items):")
    print(f"Current:   {t1:.4f}s")
    print(f"Optimized: {t2:.4f}s")
    print(f"Improvement: {(t1 - t2) / t1 * 100:.2f}%")

if __name__ == "__main__":
    benchmark_is_negated()
    benchmark_court_weight()
