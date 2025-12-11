## 2025-12-11 - Permissive CORS & Missing Security Headers
**Vulnerability:** The API was configured with `allow_origins=["*"]` AND `allow_credentials=True`, which causes Starlette/FastAPI to reflect the `Origin` header, effectively allowing any malicious site to make authenticated cross-origin requests (CSRF/Data Exfiltration) to the local tool.
**Learning:** Starlette's `CORSMiddleware` has a specific behavior where `*` + credentials results in reflection of the Origin, which is insecure. Additionally, standard security headers were missing.
**Prevention:** Never use `allow_origins=["*"]` with `allow_credentials=True`. Explicitly list allowed origins (e.g., localhost) for local tools. Use middleware to enforce security headers like `X-Frame-Options` and `X-Content-Type-Options`.
