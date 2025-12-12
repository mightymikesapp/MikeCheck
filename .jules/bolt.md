# Bolt's Journal

## 2024-05-23 - [Blocking Cache I/O]
**Learning:** The `CacheManager` performs synchronous file I/O (json.load/dump) inside `async` API methods. This blocks the event loop, negating the benefits of `asyncio` for high-concurrency tasks like `find_citing_cases`.
**Action:** Offload file I/O to a thread pool using `loop.run_in_executor` to keep the event loop responsive.

## 2024-05-24 - [Regex Optimization & Broken Tests]
**Learning:** Optimizing regex matching from O(N*M) to O(M) using a single combined pattern significantly improves text analysis throughput. However, pre-existing tests may rely on specific logic (e.g., "is_good_law" threshold) that was previously untested due to syntax errors.
**Action:** When fixing broken code, trust the tests as the "spec" for behavior, even if it requires adjusting logic thresholds (e.g., `> 1` to `> 0` negative cases). Always verify full file content when replacing code to ensure initialization of optimization structures (like pre-compiled regexes).
