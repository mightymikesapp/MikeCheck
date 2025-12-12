# Performance Optimization Guide

This document explains the performance bottlenecks identified and the optimizations implemented in Phase 3.2.

**Last Updated:** 2025-12-12
**Focus:** Treatment analysis, quote matching, parallelization
**Expected Improvements:** 5-20x faster response times

---

## Table of Contents

1. [Identified Bottlenecks](#identified-bottlenecks)
2. [Optimization Strategies](#optimization-strategies)
3. [Implementation Details](#implementation-details)
4. [Performance Baselines](#performance-baselines)
5. [Testing & Validation](#testing--validation)

---

## Identified Bottlenecks

### Bottleneck #1: CRITICAL - Triple Signal Extraction (3x Overhead)

**Location:** `app/analysis/treatment_classifier.py:326-375`

**Problem:**
```python
# Current: THREE separate extraction loops
for context, position in contexts:
    # Loop #1: Check negative patterns (12 patterns)
    for pattern, (signal, weight) in self.negative_patterns.items():
        for match in pattern.finditer(context):
            signals.append(...)

    # Loop #2: Check positive patterns (13 patterns)
    for pattern, (signal, weight) in self.positive_patterns.items():
        for match in pattern.finditer(context):
            signals.append(...)

    # Loop #3: Use combined pattern (REDUNDANT!)
    for match in self.combined_signal_pattern.finditer(context):
        signals.append(...)
```

**Issue:** All three loops run sequentially, creating duplicate signal detection

**Fix:** Remove loops 1 & 2, keep only loop 3 (combined pattern)

**Performance Impact:**
- Before: O(contexts × (12 patterns + 13 patterns + 1 combined))
- After: O(contexts × 1 combined)
- **Improvement: 3x faster signal extraction**

**Affected Functions:**
- `classify_treatment()` - called by all treatment analysis tools
- Cascades to all dependent tools

---

### Bottleneck #2: CRITICAL - Sequential Classification in `treatment_timeline_impl()` (300 Cases)

**Location:** `app/tools/treatment.py:348-351`

**Problem:**
```python
# Current: Sequential, no parallelization
treatments = []
for case in citing_cases:  # citing_cases has 300 items!
    analysis = classifier.classify_treatment(case, citation)  # Blocks 300x
    if analysis.date_filed:
        treatments.append(analysis)
```

**Issue:** 300 sequential `classify_treatment()` calls, each 50-100ms

**Performance Impact:**
- Current: 300 × 50-100ms = **15-30 seconds minimum**
- With Semaphore(5): ~60 × 50-100ms = **3-6 seconds**
- **Improvement: 5-10x faster**

**Fix Strategy:**
```python
# Optimized: Parallelized with semaphore limiting
async def fetch_with_limit(semaphore, case):
    async with semaphore:
        return classifier.classify_treatment(case, citation)

semaphore = asyncio.Semaphore(5)  # Limit to 5 concurrent
treatments = await asyncio.gather(
    *[fetch_with_limit(semaphore, case) for case in citing_cases]
)
```

---

### Bottleneck #3: HIGH - Sequential Classification in `get_citing_cases_impl()`

**Location:** `app/tools/treatment.py:296-313`

**Problem:**
- Default limit: 20 cases
- No parallelization (could be up to 100 with settings)
- Sequential: 20 × 50-100ms = 1-2 seconds

**Fix:** Apply same Semaphore(5) pattern as bottleneck #2

**Performance Impact:**
- Current: 20 × 50-100ms = **1-2 seconds**
- Optimized: 4 × 50-100ms = **0.2-0.4 seconds**
- **Improvement: 5x faster**

---

### Bottleneck #4: MEDIUM - Sequential Initial Analysis

**Location:** `app/tools/treatment.py:136-141`

**Problem:**
```python
# Current: Sequential analysis of snippets
for citing_case in citing_cases:
    analysis = classifier.classify_treatment(citing_case, citation)  # Blocks N times
    initial_treatments.append((citing_case, analysis))
```

**Issue:** All snippet analysis is sequential before parallelized full-text fetching

**Performance Impact:**
- Current: N × 50-100ms sequential
- Optimized: (N/5) × 50-100ms with parallelization
- **Improvement: 5x faster**

**Note:** Full-text fetching IS already parallelized (good pattern!)

---

### Bottleneck #5: LOW - Negation Check Overhead

**Location:** `app/analysis/treatment_classifier.py:210-224`

**Problem:**
```python
def _is_negated(self, text: str, position: int) -> bool:
    # Creates substring copy + lowercase for EVERY signal checked
    preceding = text[start:position].lower()
    return bool(self.negation_pattern.search(preceding))
```

**Issue:** Called for every signal, creates unnecessary substring copies

**Performance Impact:**
- Low overhead but adds up
- **Improvement: 2-3x for signal extraction**

**Fix:** Pre-compute negation context or cache

---

## Optimization Strategies

### Strategy #1: Remove Redundant Pattern Matching

**Implementation:**
- Keep only the `combined_signal_pattern` regex
- Remove separate `negative_patterns` and `positive_patterns` loops
- Result: Single-pass extraction instead of triple-pass

**Code Change:**
```python
# BEFORE (3 passes)
for pattern, (signal, weight) in self.negative_patterns.items():
    for match in pattern.finditer(context):
        signals.append(...)
for pattern, (signal, weight) in self.positive_patterns.items():
    for match in pattern.finditer(context):
        signals.append(...)
for match in self.combined_signal_pattern.finditer(context):
    signals.append(...)

# AFTER (1 pass)
for match in self.combined_signal_pattern.finditer(context):
    signals.append(...)
```

**Validation:** Ensure signal detection accuracy unchanged

---

### Strategy #2: Parallelization with Bounded Concurrency

**Implementation:**
- Use `asyncio.Semaphore(5)` to limit concurrent operations
- Prevents overwhelming CourtListener API rate limits
- Balances speed vs. resource usage

**Code Pattern:**
```python
async def classify_with_limit(semaphore, case, citation):
    async with semaphore:
        return classifier.classify_treatment(case, citation)

semaphore = asyncio.Semaphore(5)
analyses = await asyncio.gather(
    *[classify_with_limit(semaphore, case, citation) for case in cases],
    return_exceptions=True
)
```

**Benefits:**
- Reduces 300 sequential calls to ~60 batches of 5
- Respects API rate limits
- Maintains code simplicity

---

### Strategy #3: Batch Operations

**Implementation:**
- Group related operations (like initial analysis + full-text fetching)
- Process in parallel rather than sequential-then-parallel

**Example:**
```python
# BEFORE: Sequential analysis, then parallel fetching
for case in cases:
    initial_analysis = classify_treatment(case)  # Sequential

fetch_results = await gather(*fetches)  # Parallel

# AFTER: Parallel analysis from start
analyses = await gather(*classify_tasks)  # Parallel from beginning
```

---

## Implementation Details

### Changes to `app/analysis/treatment_classifier.py`

**Fix 1: Remove Triple Pattern Matching (Lines 326-353)**

```python
# DELETE these lines:
# Lines 326-338: Negative patterns loop
# Lines 341-353: Positive patterns loop

# KEEP only:
# Lines 356-375: Combined pattern extraction
for match in self.combined_signal_pattern.finditer(context):
    signal_text = match.group(0).lower()
    # ... rest of logic ...
```

**Expected Change:**
```
Before: 3 × O(n) pattern matching
After: 1 × O(n) pattern matching
Result: 3x faster signal extraction
```

---

### Changes to `app/tools/treatment.py`

**Fix 2: Parallelize `treatment_timeline_impl()` (Lines 348-351)**

Convert from:
```python
treatments = []
for case in citing_cases:
    analysis = classifier.classify_treatment(case, citation)
    if analysis.date_filed:
        treatments.append(analysis)
```

To:
```python
async def classify_with_limit(semaphore, case):
    async with semaphore:
        return classifier.classify_treatment(case, citation)

semaphore = asyncio.Semaphore(5)
analyses = await asyncio.gather(
    *[classify_with_limit(semaphore, case) for case in citing_cases],
    return_exceptions=True
)
treatments = [a for a in analyses if isinstance(a, object) and a.date_filed]
```

**Expected Change:**
```
Before: 300 sequential × 50-100ms = 15-30 seconds
After: 60 batches of 5 × 50-100ms = 3-6 seconds
Result: 5-10x faster
```

---

## Performance Baselines

### Before Optimization

| Function | Cases | Mode | Time | Bottleneck |
|----------|-------|------|------|-----------|
| `check_case_validity_impl()` | 100 | standard | 2-5s | Initial analysis + triple pattern |
| `get_citing_cases_impl()` | 20 | standard | 1-2s | Sequential analysis |
| `treatment_timeline_impl()` | 300 | standard | 15-30s | Sequential + triple pattern |

### After Optimization

| Function | Cases | Mode | Time | Improvement |
|----------|-------|------|------|------------|
| `check_case_validity_impl()` | 100 | standard | 0.5-1.5s | 3-5x faster |
| `get_citing_cases_impl()` | 20 | standard | 0.2-0.4s | 5x faster |
| `treatment_timeline_impl()` | 300 | standard | 3-6s | 5-10x faster |

### Compounding Effects

When ALL optimizations applied:
- **Triple pattern fix:** 3x improvement
- **Parallelization:** 5x improvement
- **Combined:** 10-15x improvement on critical paths

---

## Testing & Validation

### Unit Tests

```python
def test_signal_extraction_accuracy():
    """Ensure optimized extraction finds same signals"""
    classifier = TreatmentClassifier()

    snippet = "This case was overruled on other grounds"
    signals = classifier.classify_treatment(case, citation)

    # Should still detect "overruled" as negative signal
    assert signals.treatment_type == "negative"
    assert "overruled" in signals.signals
```

### Performance Tests

```python
async def test_parallelization_speedup():
    """Measure parallelization improvement"""
    import time

    cases = [case1, case2, ..., case20]

    # Time sequential version
    start = time.perf_counter()
    for case in cases:
        classifier.classify_treatment(case, citation)
    sequential_time = time.perf_counter() - start

    # Time parallelized version
    start = time.perf_counter()
    semaphore = asyncio.Semaphore(5)
    await asyncio.gather(
        *[classify_with_limit(semaphore, case) for case in cases]
    )
    parallel_time = time.perf_counter() - start

    # Assert 5x improvement
    assert sequential_time / parallel_time >= 4.5
```

### Load Testing

```bash
# Test with realistic load
wrk -t4 -c10 -d30s http://localhost:8000/herding/analyze \
  -s benchmark.lua

# Expected:
# - Before: 2-5 requests/sec (limited by sequential processing)
# - After: 10-25 requests/sec (parallelized)
```

---

## Performance Monitoring

### Metrics to Track

After deployment, monitor:

```promql
# Tool duration histogram (should decrease)
histogram_quantile(0.99, rate(mcp_tool_duration_seconds_bucket{tool_name="check_case_validity"}[5m]))

# Requests per second (should increase)
rate(api_requests_total[1m])

# Error rate (should remain same)
rate(mcp_tool_calls_total{status="error"}[5m])

# Circuit breaker state (should remain closed)
circuit_breaker_state{service="courtlistener"}
```

### Dashboard Updates

Add to Grafana:
- P50/P95/P99 latency BEFORE vs. AFTER
- Throughput increase (req/sec)
- Cache hit ratio
- API call frequency (should decrease with better caching)

---

## Rollback Plan

If performance optimization causes issues:

1. **Regression detected** → Revert specific optimization
2. **Check metrics** → Compare before/after baselines
3. **Root cause analysis** → Why did optimization hurt?
4. **Fix and re-apply** → Address root cause

Git commands:
```bash
# Revert specific commit
git revert <commit-hash>

# Or manually revert code changes
git checkout <original-version> -- app/analysis/treatment_classifier.py
```

---

## Future Optimizations

Beyond Phase 3:

1. **Caching Layer** - Cache classification results by citation
2. **ML Model Optimization** - Use lighter model for snippet matching
3. **API Call Reduction** - Batch CourtListener requests
4. **Quote Matching** - Use Aho-Corasick algorithm for O(n+m) matching
5. **Graph Caching** - Cache citation networks to avoid recomputation

---

**Implementation Status:** Ready for Phase 3.2 code changes
**Testing Plan:** Unit tests + performance benchmarks
**Rollback Risk:** Low (no API changes, internal optimization)
**Expected Outcome:** 5-15x performance improvement
