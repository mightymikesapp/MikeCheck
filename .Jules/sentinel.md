## 2025-12-13 - [Rate Limiting Implementation Nuances]
**Vulnerability:** Missing rate limiting on sensitive endpoints allowed potential DoS.
**Learning:** `slowapi` library requires explicit `storage_uri="memory://"` (with scheme) and explicit `request: Request` parameter in all decorated endpoints. Failing to provide `request` causes obscure errors. Tests hitting these endpoints will fail with 429 unless rate limiting is explicitly disabled (`app.state.limiter.enabled = False`).
**Prevention:** Always verify `slowapi` configuration with scheme. Always add `request` dependency to rate-limited endpoints. Patch the limiter in tests.
