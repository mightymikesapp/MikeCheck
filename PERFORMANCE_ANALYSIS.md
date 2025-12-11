# Performance Analysis Report

**Date**: 2025-12-11
**Codebase**: Legal Research Assistant MCP
**Analysis Scope**: Performance anti-patterns, N+1 queries, inefficient algorithms

---

## Executive Summary

This analysis identified **10 significant performance issues** across the codebase, ranging from N+1 query patterns to inefficient algorithms with poor time complexity. The most critical issues are:

1. **N+1 query pattern in treatment analysis** - Sequential full-text fetching
2. **Inefficient fuzzy matching algorithm** - O(n²) complexity with nested loops
3. **Unbatched quote verification** - Sequential processing despite async support
4. **Expensive graph metrics recomputation** - No caching of PageRank/eigenvector centrality

**Estimated Performance Impact**: These issues could cause 3-10x slowdowns on typical workloads, with worst-case scenarios reaching 50-100x for large document sets.

---

## Critical Issues (High Priority)

### 1. N+1 Query Pattern: Sequential Full-Text Fetching

**Location**: `app/tools/treatment.py:176-236`

**Issue**: The treatment analysis fetches full opinion text sequentially, one case at a time.

```python
for citing_case, initial_analysis in initial_treatments:
    needs_full_text = any(
        c is citing_case for c, _ in cases_for_full_text
    ) and full_text_count < settings.max_full_text_fetches

    if needs_full_text:
        try:
            # Extract opinion IDs from the case
            opinion_ids: list[int] = []
            for op in citing_case.get("opinions", []):
                # ... extraction logic ...

            if opinion_ids:
                opinion_id = opinion_ids[0]

                # PERFORMANCE ISSUE: Sequential fetch
                full_text = await client.get_opinion_full_text(
                    opinion_id, request_id=request_id
                )
```

**Impact**:
- If analyzing 50 cases requiring full text, this creates 50 sequential HTTP requests
- With 500ms average API latency: 50 × 0.5s = **25 seconds of blocking I/O**
- Parallelized: Could complete in ~1-2 seconds with proper batching

**Recommendation**:
```python
# Collect all opinion IDs first
opinion_ids_to_fetch = []
for citing_case, initial_analysis in initial_treatments:
    if should_fetch_full_text(citing_case):
        opinion_ids_to_fetch.extend(extract_opinion_ids(citing_case))

# Batch fetch with concurrency limit
async def fetch_with_limit(opinion_id):
    return await client.get_opinion_full_text(opinion_id, request_id=request_id)

# Use asyncio.Semaphore to limit concurrency (e.g., 5 concurrent requests)
semaphore = asyncio.Semaphore(5)

async def bounded_fetch(opinion_id):
    async with semaphore:
        return await fetch_with_limit(opinion_id)

full_texts = await asyncio.gather(
    *[bounded_fetch(op_id) for op_id in opinion_ids_to_fetch[:settings.max_full_text_fetches]]
)
```

**Priority**: 🔴 **HIGH** - This is a classic N+1 pattern causing significant latency.

---

### 2. Inefficient Fuzzy Matching Algorithm

**Location**: `app/analysis/quote_matcher.py:158-241`

**Issue**: The fuzzy matching uses a sliding window with nested loops, resulting in poor time complexity.

```python
def find_quote_fuzzy(self, quote: str, source: str, max_matches: int = 5) -> list[QuoteMatch]:
    # Sliding window approach
    window_size = quote_len
    tolerance = int(quote_len * 0.2)  # Allow 20% size variation

    # PERFORMANCE ISSUE: Triple nested loop
    for start in range(0, source_len - window_size + tolerance + 1, max(1, quote_len // 4)):
        for size in range(
            max(window_size - tolerance, 1),
            min(window_size + tolerance, source_len - start) + 1,
        ):
            end = start + size
            window = normalized_source[start:end]

            similarity = self.calculate_similarity(normalized_quote, window)
            # ...
```

**Complexity Analysis**:
- Outer loop: O(n / (m/4)) = O(4n/m) iterations where n=source length, m=quote length
- Inner loop: O(tolerance) = O(0.2m) iterations
- `calculate_similarity()`: O(m) using SequenceMatcher
- **Total: O(n × m) = O(n²)** for quote length proportional to source

**Real-World Impact**:
- Source text: 50,000 characters (typical legal opinion)
- Quote: 200 characters
- Window step: 200 / 4 = 50 characters
- Outer loop iterations: 50,000 / 50 = 1,000
- Inner loop iterations per outer: ~40 (tolerance)
- SequenceMatcher calls: 1,000 × 40 = **40,000 similarity computations**

Each SequenceMatcher call on ~200 chars takes ~0.1ms → **4 seconds per quote**

**Recommendations**:

1. **Use a faster approximate matching algorithm**:
   - Consider RapidFuzz library (C++ implementation, 10-100x faster)
   - Or use n-gram based pre-filtering to reduce candidates

2. **Increase step size**: Currently stepping by `quote_len // 4`. Increase to `quote_len // 2` or even `quote_len` with overlap:
```python
step_size = max(1, quote_len // 2)  # 2x faster
```

3. **Early termination**: If an exact or near-exact match (>0.98) is found, stop searching:
```python
if similarity >= 0.98:
    break  # Good enough, don't keep searching
```

4. **Pre-filter with Boyer-Moore or similar**:
   - First find approximate positions using fast string search
   - Only run expensive fuzzy match on promising regions

**Priority**: 🔴 **HIGH** - Quadratic complexity on user-facing operation.

---

### 3. Unbatched Quote Verification

**Location**: `app/tools/verification.py:360-387`

**Issue**: `batch_verify_quotes` processes quotes sequentially despite being async.

```python
async def batch_verify_quotes_impl(quotes: list[dict[str, str]], ...) -> dict[str, Any]:
    results = []
    # PERFORMANCE ISSUE: Sequential loop, not parallelized
    for i, quote_data in enumerate(quotes, 1):
        quote = quote_data.get("quote", "")
        citation = quote_data.get("citation", "")
        pinpoint = quote_data.get("pinpoint")

        result = await verify_quote_impl(quote, citation, pinpoint, request_id=request_id)
        results.append(result)
```

**Impact**:
- Verifying 10 quotes with 2s each = **20 seconds total**
- Could be done in ~2-3 seconds with parallelization

**Recommendation**:
```python
async def batch_verify_quotes_impl(quotes: list[dict[str, str]], ...) -> dict[str, Any]:
    # Create tasks for parallel execution
    tasks = []
    for quote_data in quotes:
        quote = quote_data.get("quote", "")
        citation = quote_data.get("citation", "")
        pinpoint = quote_data.get("pinpoint")

        if not quote or not citation:
            # Handle synchronously for errors
            tasks.append(asyncio.create_task(
                asyncio.sleep(0, result={
                    "error": "Missing quote or citation",
                    "quote": quote,
                    "citation": citation,
                })
            ))
        else:
            tasks.append(
                verify_quote_impl(quote, citation, pinpoint, request_id=request_id)
            )

    # Execute all in parallel
    results = await asyncio.gather(*tasks)
    # ... rest of function
```

**Priority**: 🔴 **HIGH** - Trivial fix with major impact.

---

### 4. Expensive Graph Metrics Recomputation

**Location**: `app/tools/network.py:456-492`

**Issue**: PageRank and eigenvector centrality are recomputed every time network statistics are requested, with no caching.

```python
if enable_advanced_metrics:
    import networkx as nx
    # ... build graph ...

    if graph.number_of_nodes() > 0:
        # PERFORMANCE ISSUE: Expensive computation, no caching
        pagerank_scores = nx.pagerank(graph, weight="weight")
        # ...

        try:
            # VERY EXPENSIVE: max_iter=500
            eigenvector_scores = nx.eigenvector_centrality(
                graph, weight="weight", max_iter=500
            )
```

**Impact**:
- PageRank on 100-node graph: ~50-100ms
- Eigenvector centrality with max_iter=500: ~200-500ms
- **Total: 250-600ms** of pure computation per request
- Repeated requests for same citation: wasted computation

**Recommendation**:
1. **Cache computed metrics** by citation + parameters:
```python
# In-memory LRU cache for computed metrics
from functools import lru_cache

@lru_cache(maxsize=100)
def compute_graph_metrics(citation: str, max_nodes: int, weight_config: tuple) -> dict:
    # ... expensive computation ...
    return {
        "pagerank": pagerank_scores,
        "eigenvector_centrality": eigenvector_scores,
        # ...
    }
```

2. **Make metrics optional/lazy**:
   - Compute PageRank by default (faster)
   - Only compute eigenvector centrality if explicitly requested
   - Allow user to request "quick stats" vs "full stats"

3. **Reduce max_iter for eigenvector**:
   - 500 iterations is overkill for most graphs
   - Try 100-200 iterations with tolerance check

**Priority**: 🟠 **MEDIUM-HIGH** - Significant waste but only affects specific operations.

---

## High Impact Issues (Medium Priority)

### 5. Sequential Processing in Semantic Search

**Location**: `app/tools/search.py:164-202`

**Issue**: Full-text fetches are batched but processed sequentially within batches.

```python
# Fetch in batches of 5 to respect rate limits gracefully
batch_size = 5
for i in range(0, len(cases_to_fetch), batch_size):
    batch_ids = cases_to_fetch[i : i + batch_size]
    tasks = [_fetch_full_text_safe(client, cid) for cid in batch_ids]
    # GOOD: Parallelizes within batch
    full_text_results = await asyncio.gather(*tasks)
    # ISSUE: Batches processed sequentially
```

**Impact**:
- Fetching 50 cases with batch_size=5: 10 sequential batches
- Each batch: ~500ms (assuming 5 parallel requests)
- Total: 10 × 0.5s = **5 seconds**

**Why batching?**: Likely to respect API rate limits.

**Recommendation**:
- Current approach is reasonable if rate limits are strict
- Consider using `asyncio.Semaphore` instead for finer control:
```python
semaphore = asyncio.Semaphore(5)  # Max 5 concurrent

async def fetch_with_limit(cid):
    async with semaphore:
        return await _fetch_full_text_safe(client, cid)

# All in one gather, semaphore controls concurrency
full_text_results = await asyncio.gather(
    *[fetch_with_limit(cid) for cid in cases_to_fetch]
)
```

**Priority**: 🟡 **MEDIUM** - Current approach may be intentional for rate limiting.

---

### 6. Cache Key Building Overhead

**Location**: `app/cache.py:65-87`

**Issue**: Cache key building recursively normalizes dictionaries and serializes to JSON for every cache operation.

```python
def _build_key(self, params: dict[str, Any] | str) -> str:
    if isinstance(params, str):
        content = params
    else:
        # PERFORMANCE ISSUE: Recursive normalization + JSON serialization
        def normalize(value: Any) -> Any:
            if isinstance(value, str):
                return value.strip().lower()
            if isinstance(value, (list, tuple)):
                return sorted([normalize(v) for v in value], key=str)
            if isinstance(value, dict):
                return {k.lower() if isinstance(k, str) else k: normalize(v) for k, v in value.items()}
            return value

        normalized = {
            k.lower() if isinstance(k, str) else k: normalize(v)
            for k, v in params.items()
            if v not in (None, "")
        }
        content = json.dumps(normalized, sort_keys=True, separators=(",", ":"))

    return hashlib.sha256(content.encode("utf-8")).hexdigest()
```

**Impact**:
- For large parameter dictionaries (e.g., search results with 100 items)
- Recursive normalization: O(n) where n = total values
- JSON serialization: O(n)
- Called on **every** cache get/set operation
- High-traffic tool: ~1000 cache operations/min → wasting CPU cycles

**Recommendation**:
1. **Use simpler key generation for common cases**:
```python
def _build_key(self, params: dict[str, Any] | str) -> str:
    if isinstance(params, str):
        return hashlib.sha256(params.encode("utf-8")).hexdigest()

    # Fast path for simple params (most common)
    if all(isinstance(v, (str, int, float, bool, type(None))) for v in params.values()):
        # Simple serialization without normalization
        key_str = json.dumps(params, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

    # Slow path for complex params
    # ... existing normalization logic ...
```

2. **Cache the cache keys**: If same params used repeatedly, memoize the key.

3. **Use faster hashing**: SHA256 is cryptographically secure but slow. For cache keys, MD5 or xxhash would be 2-5x faster.

**Priority**: 🟡 **MEDIUM** - Affects all cache operations but impact is relatively small per operation.

---

### 7. Treatment Classification Pattern Matching

**Location**: `app/analysis/treatment_classifier.py:232-263`

**Issue**: Pattern matching iterates through all negative and positive patterns for each context.

```python
for context, position in contexts:
    # PERFORMANCE ISSUE: Iterate through all patterns for each context
    # Check for negative signals
    for pattern, (signal, weight) in self.negative_patterns.items():
        for match in pattern.finditer(context):
            # Check for negation
            if self._is_negated(context, match.start()):
                continue
            # ... create signal ...

    # Check for positive signals
    for pattern, (signal, weight) in self.positive_patterns.items():
        for match in pattern.finditer(context):
            # ... similar logic ...
```

**Impact**:
- 12 negative patterns + 11 positive patterns = 23 regex searches per context
- Average 3 contexts per case × 100 cases = 300 contexts
- 300 × 23 = **6,900 regex searches**

**Current state**: Patterns compiled once in `__init__` ✅ (good!)

**Recommendation**:
1. **Combine patterns into single alternation regex**:
```python
# In __init__
negative_pattern_str = "|".join(f"(?P<{name}>{pattern})" for name, pattern in NEGATIVE_SIGNALS.items())
self.negative_combined = re.compile(negative_pattern_str, re.IGNORECASE)

# In extract_signals
for match in self.negative_combined.finditer(context):
    signal_name = match.lastgroup
    # ... process match ...
```
This reduces 12 regex searches to 1.

2. **Early termination**: If a strong signal is found (weight > 0.9), skip remaining patterns.

3. **Optimize context extraction**: Currently extracts multiple overlapping contexts. Consider deduplication.

**Priority**: 🟡 **MEDIUM** - Pattern matching is fast but adds up at scale.

---

## Low Impact Issues (Low Priority)

### 8. Missing HTTP Connection Pooling Configuration

**Location**: `app/mcp_client.py:76`

**Issue**: No explicit connection pool configuration for httpx client.

```python
timeout = httpx.Timeout(
    timeout=self.settings.courtlistener_timeout,
    connect=self.settings.courtlistener_connect_timeout,
    read=self.settings.courtlistener_read_timeout,
)
# POTENTIAL ISSUE: No explicit limits configured
self.client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)
```

**Default httpx limits**:
- `max_connections=100`
- `max_keepalive_connections=20`

**Impact**:
- For typical usage: defaults are likely fine
- For high concurrency (100+ concurrent requests): might hit limits
- Keep-alive pool of 20 could cause connection churn

**Recommendation**:
```python
limits = httpx.Limits(
    max_connections=200,        # Increase if high concurrency expected
    max_keepalive_connections=50,  # More keep-alive connections
    keepalive_expiry=30.0,      # Keep connections alive longer
)

self.client = httpx.AsyncClient(
    base_url=self.base_url,
    timeout=timeout,
    limits=limits,
    http2=True,  # Enable HTTP/2 if supported by API
)
```

**Priority**: 🟢 **LOW** - Only matters at high concurrency, defaults are reasonable.

---

### 9. Synchronous File I/O in Cache

**Location**: `app/cache.py:94-193`

**Issue**: File operations are synchronous, wrapped in async via `run_in_executor`.

```python
async def aget(self, cache_type: CacheType, key_params: dict[str, Any] | str) -> Any | None:
    """Async retrieve an item from the cache."""
    if not self.enabled:
        return None
    # ISSUE: Wraps sync I/O in executor
    return await asyncio.get_running_loop().run_in_executor(
        None, self.get, cache_type, key_params
    )
```

**Analysis**:
- Using `run_in_executor` is the **correct** approach for sync file I/O
- Prevents blocking the event loop ✅
- Thread pool overhead is minimal (<1ms per call)

**Potential improvement**: For truly async file I/O, use `aiofiles`:
```python
async def aget(self, cache_type: CacheType, key_params: dict[str, Any] | str) -> Any | None:
    if not self.enabled:
        return None

    key = self._build_key(key_params)
    path = self._get_path(cache_type, key)

    if not path.exists():
        self.stats["misses"] += 1
        return None

    # True async file I/O
    import aiofiles
    async with aiofiles.open(path, 'r', encoding='utf-8') as f:
        data = await f.read()
        if cache_type == CacheType.TEXT:
            return data
        else:
            return json.loads(data)
```

**Priority**: 🟢 **LOW** - Current approach is acceptable, improvement is marginal.

---

### 10. Treatment Classifier Threading Limitation

**Location**: `app/tools/network.py:132-139`

**Issue**: Treatment classification uses thread pool but is CPU-bound.

```python
# Use run_in_executor to avoid blocking the event loop if classification is CPU heavy
loop = asyncio.get_running_loop()
tasks = [
    loop.run_in_executor(None, classifier.classify_treatment, c_case, citation)
    for c_case in citing_cases[:max_nodes]
]

treatment_results = await asyncio.gather(*tasks)
```

**Analysis**:
- `classify_treatment` is CPU-bound (regex matching, signal extraction)
- Python's GIL prevents true parallelism in threads
- Thread pool doesn't help CPU-bound work, only prevents blocking event loop

**Impact**:
- For 100 cases: ~200ms of CPU time
- With threading: still ~200ms (no speedup due to GIL)
- Without threading: would block event loop for 200ms

**Current benefit**: Prevents event loop blocking ✅

**Recommendation** (if profiling shows this is a bottleneck):
1. **Use ProcessPoolExecutor for true parallelism**:
```python
from concurrent.futures import ProcessPoolExecutor

# Create process pool (expensive, do once)
process_pool = ProcessPoolExecutor(max_workers=4)

# In build_citation_network_impl
tasks = [
    loop.run_in_executor(process_pool, classifier.classify_treatment, c_case, citation)
    for c_case in citing_cases[:max_nodes]
]
```

2. **Optimize the classification algorithm** (preferred):
   - Profile to find hotspots
   - Optimize regex patterns (already done via compilation)
   - Reduce context extraction overhead

**Priority**: 🟢 **LOW** - Current approach prevents blocking, optimization requires profiling to justify complexity.

---

## Summary of Recommendations

### Immediate Actions (High Priority)

1. ✅ **Parallelize full-text fetching in treatment analysis** (Issue #1)
   - **File**: `app/tools/treatment.py:176-236`
   - **Fix**: Use `asyncio.gather()` with semaphore for concurrency control
   - **Impact**: 10-25x speedup for treatment analysis

2. ✅ **Optimize fuzzy matching algorithm** (Issue #2)
   - **File**: `app/analysis/quote_matcher.py:158-241`
   - **Fix**: Increase step size, add early termination, consider RapidFuzz
   - **Impact**: 2-5x speedup for quote verification

3. ✅ **Parallelize batch quote verification** (Issue #3)
   - **File**: `app/tools/verification.py:360-387`
   - **Fix**: Use `asyncio.gather()` to process quotes concurrently
   - **Impact**: 5-10x speedup for batch operations

4. ✅ **Cache graph metrics computation** (Issue #4)
   - **File**: `app/tools/network.py:456-492`
   - **Fix**: Add LRU cache for expensive PageRank/eigenvector centrality
   - **Impact**: Eliminate 250-600ms of recomputation per repeated request

### Medium Priority Actions

5. ✅ **Review semantic search batching strategy** (Issue #5)
   - Verify if sequential batches are required for rate limits
   - If not, use semaphore for finer concurrency control

6. ✅ **Optimize cache key generation** (Issue #6)
   - Add fast path for simple parameter types
   - Consider faster hash function (xxhash vs SHA256)

7. ✅ **Combine regex patterns** (Issue #7)
   - Merge all negative/positive patterns into single alternation regex
   - Reduces regex searches from 23 to 2 per context

### Low Priority (Nice to Have)

8. Configure HTTP connection pooling explicitly
9. Consider `aiofiles` for truly async file I/O
10. Profile treatment classification for potential optimization

---

## Performance Testing Recommendations

To validate these findings and measure improvements:

1. **Create performance benchmarks**:
```python
# tests/performance/test_treatment_analysis_perf.py
import pytest
import time

@pytest.mark.performance
async def test_treatment_analysis_performance():
    """Measure treatment analysis with 50 citing cases."""
    start = time.time()
    result = await check_case_validity_impl("410 U.S. 113")
    duration = time.time() - start

    assert duration < 10.0, f"Treatment analysis took {duration}s, should be <10s"
    print(f"Treatment analysis: {duration:.2f}s")
```

2. **Profile hotspots**:
```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Run operation
await check_case_validity_impl("410 U.S. 113")

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 functions by cumulative time
```

3. **Load testing with realistic workload**:
   - Simulate 100 concurrent users
   - Measure throughput (requests/second)
   - Identify bottlenecks under load

4. **Monitor in production**:
   - Add timing metrics to logging
   - Track P50, P95, P99 latencies
   - Alert on performance regressions

---

## Conclusion

This codebase has a solid foundation with async/await patterns and caching in place. However, several performance anti-patterns limit scalability:

- **N+1 queries**: Sequential API calls that should be parallelized
- **Inefficient algorithms**: O(n²) fuzzy matching, unoptimized sliding windows
- **Missing parallelization**: Batch operations running sequentially
- **Redundant computation**: Expensive graph metrics recomputed without caching

**Estimated Overall Impact**: Implementing high-priority fixes could yield **5-10x performance improvement** on typical workloads, with even greater gains on large datasets or high-concurrency scenarios.

**Next Steps**:
1. Implement fixes for Issues #1-4 (high priority)
2. Add performance benchmarks to CI/CD
3. Profile in production to identify additional bottlenecks
4. Consider medium-priority optimizations based on usage patterns
