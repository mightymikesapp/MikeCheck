# Bolt's Journal

## 2024-05-23 - [Blocking Cache I/O]
**Learning:** The `CacheManager` performs synchronous file I/O (json.load/dump) inside `async` API methods. This blocks the event loop, negating the benefits of `asyncio` for high-concurrency tasks like `find_citing_cases`.
**Action:** Offload file I/O to a thread pool using `loop.run_in_executor` to keep the event loop responsive.
