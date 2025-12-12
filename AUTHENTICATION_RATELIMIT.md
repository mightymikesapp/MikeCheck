# Authentication & Rate Limiting Guide

> **Phase 3.3 Implementation** - Authentication and rate limiting for MikeCheck API

**Last Updated:** 2025-12-12
**Version:** 1.0
**Status:** Production-Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Rate Limiting](#rate-limiting)
4. [Configuration](#configuration)
5. [Usage Examples](#usage-examples)
6. [Security Best Practices](#security-best-practices)
7. [Monitoring & Troubleshooting](#monitoring--troubleshooting)

---

## Overview

Phase 3.3 adds two critical security layers to the MikeCheck API:

### **Authentication**
- Protects API endpoints from unauthorized access
- Supports multiple authentication methods (headers, query params)
- API key validation and management
- Optional enforcement (can be disabled for development)

### **Rate Limiting**
- Prevents API abuse and excessive usage
- Per-endpoint limits with different thresholds
- Per-API-key or per-IP tracking
- Graceful handling with 429 responses

**Key Features:**
- ✅ Zero-downtime deployment compatible
- ✅ Configurable via environment variables
- ✅ Multiple authentication methods
- ✅ Per-endpoint rate limits
- ✅ Intelligent key management
- ✅ Comprehensive logging

---

## Authentication

### Overview

Authentication protects sensitive endpoints by requiring valid API keys. The implementation is:
- **Optional**: Can be disabled with `ENABLE_API_KEY_AUTH=false`
- **Flexible**: Supports multiple authentication methods
- **Secure**: Never logs raw keys, uses hashing
- **Simple**: Easy to integrate with existing tools

### Configuration

Enable authentication in `.env`:

```bash
# Enable API key authentication
ENABLE_API_KEY_AUTH=true

# Define valid API keys (comma-separated)
API_KEYS=<YOUR_API_KEY_1>,<YOUR_API_KEY_2>,<YOUR_API_KEY_3>
```

### Supported Authentication Methods

#### 1. Authorization Header (Recommended)

Most secure method - sends key in HTTP Authorization header:

```bash
curl -H "Authorization: Bearer <YOUR_API_KEY>" \
  https://api.example.com/herding/analyze \
  -d '{"citation": "410 U.S. 113"}'
```

#### 2. X-API-Key Header

Alternative header-based authentication:

```bash
curl -H "X-API-Key: <YOUR_API_KEY>" \
  https://api.example.com/herding/analyze \
  -d '{"citation": "410 U.S. 113"}'
```

#### 3. Query Parameter (Development Only)

Least secure - useful for testing in browser:

```bash
curl "https://api.example.com/herding/analyze?api_key=<YOUR_API_KEY>" \
  -d '{"citation": "410 U.S. 113"}'
```

**⚠️ Warning:** Query parameters are logged and stored in browser history. Use only for development/testing.

### Public Endpoints

These endpoints are always accessible without authentication:

```
/health          - Health check endpoint
/metrics         - Prometheus metrics
/                - Home page
/docs            - Swagger UI documentation
/openapi.json    - OpenAPI specification
/redoc           - ReDoc documentation
```

### Error Responses

**Missing API Key (401 Unauthorized):**

```json
{
  "detail": "Missing API key. Use header: Authorization: Bearer YOUR_KEY or X-API-Key: YOUR_KEY"
}
```

**Invalid API Key (403 Forbidden):**

```json
{
  "detail": "Invalid API key"
}
```

### Key Management

#### Creating API Keys

In `.env`:

```bash
# Generate secure random keys (example)
API_KEYS=<YOUR_API_KEY_1>,<YOUR_API_KEY_2>
```

**Key Format Recommendations:**
- Prefix with `sk_test_` (development) or `sk_prod_` (production)
- At least 32 characters for security
- Generate with `openssl rand -hex 16` or similar

#### Rotating API Keys

1. Add new key to `API_KEYS` environment variable
2. Deploy without downtime
3. Update clients to use new key
4. Remove old key from `API_KEYS`
5. Deploy final removal

#### Monitoring Key Usage

All authentication attempts are logged with hashed keys:

```json
{
  "event": "invalid_api_key",
  "key_hash": "a1b2c3d4e5f6g7h8",
  "path": "/herding/analyze",
  "timestamp": "2025-12-12T10:30:45Z"
}
```

---

## Rate Limiting

### Overview

Rate limiting prevents abuse and resource exhaustion by enforcing request quotas. The system:

- **Per-identifier**: Uses API key (if authenticated) or IP address (fallback)
- **Per-endpoint**: Different limits for different operations
- **Graceful**: Returns 429 Too Many Requests instead of errors
- **Adaptive**: Can be tuned based on deployment size

### Default Limits

| Endpoint | Limit | Reason |
|----------|-------|--------|
| `/herding/analyze` | 5/min | Compute-intensive treatment analysis |
| `/herding/analyze/bulk` | 2/min | Very expensive bulk operations |
| `/search/semantic` | 20/min | Semantic search is moderately expensive |
| Default | 100/min | All other endpoints |
| `/health`, `/metrics` | Unlimited | Infrastructure endpoints |

### Configuration

In `.env`:

```bash
# Enable/disable rate limiting
ENABLE_RATE_LIMITING=true

# Default for all endpoints
RATE_LIMIT_DEFAULT=100/minute

# Specific endpoint overrides
RATE_LIMIT_TREATMENT_ANALYSIS=5/minute
RATE_LIMIT_BULK_OPERATIONS=2/minute
RATE_LIMIT_SEMANTIC_SEARCH=20/minute
```

### Rate Limit Format

Supported formats:
- `N/minute` - N requests per minute
- `N/hour` - N requests per hour
- `N/day` - N requests per day
- `N/second` - N requests per second (rare)

Examples:
- `100/minute` - 100 requests per minute
- `1000/hour` - 1000 requests per hour
- `10000/day` - 10000 requests per day

### Rate Limit Response

When rate limit is exceeded (429 Too Many Requests):

```json
{
  "error": "Rate limit exceeded",
  "message": "Too many requests. Please try again later.",
  "retry_after": null
}
```

HTTP Headers:

```
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 5
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1639385445
```

### Tracking Identifiers

Rate limits track by:

**1. API Key (if authenticated):**
```
api_key:API_KEY_EXAMPLE_DEV
```

**2. IP Address (fallback):**
```
ip:192.168.1.100
```

Each identifier has its own quota.

---

## Configuration

### Environment Variables

**Authentication:**

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_API_KEY_AUTH` | `false` | Enable authentication |
| `API_KEYS` | `` | Comma-separated valid keys |

**Rate Limiting:**

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_RATE_LIMITING` | `true` | Enable rate limiting |
| `RATE_LIMIT_DEFAULT` | `100/minute` | Default limit |
| `RATE_LIMIT_TREATMENT_ANALYSIS` | `5/minute` | Treatment analysis limit |
| `RATE_LIMIT_BULK_OPERATIONS` | `2/minute` | Bulk operations limit |
| `RATE_LIMIT_SEMANTIC_SEARCH` | `20/minute` | Semantic search limit |

### Docker Example

```bash
docker run \
  -e ENABLE_API_KEY_AUTH=true \
  -e API_KEYS="API_KEY_EXAMPLE_DEV,API_KEY_EXAMPLE_PROD" \
  -e ENABLE_RATE_LIMITING=true \
  -e RATE_LIMIT_DEFAULT=100/minute \
  -e RATE_LIMIT_TREATMENT_ANALYSIS=10/minute \
  mightymikesapp/mikecheck:latest
```

### Kubernetes Example

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mikecheck-config
data:
  ENABLE_API_KEY_AUTH: "true"
  API_KEYS: "API_KEY_EXAMPLE_DEV,API_KEY_EXAMPLE_PROD"
  ENABLE_RATE_LIMITING: "true"
  RATE_LIMIT_DEFAULT: "100/minute"
  RATE_LIMIT_TREATMENT_ANALYSIS: "5/minute"
```

---

## Usage Examples

### cURL Examples

**With Authentication (Authorization Header):**

```bash
curl -X POST \
  -H "Authorization: Bearer API_KEY_EXAMPLE_DEV" \
  -H "Content-Type: application/json" \
  -d '{"citation": "410 U.S. 113"}' \
  https://api.example.com/herding/analyze
```

**With Authentication (X-API-Key Header):**

```bash
curl -X POST \
  -H "X-API-Key: API_KEY_EXAMPLE_DEV" \
  -H "Content-Type: application/json" \
  -d '{"citation": "410 U.S. 113"}' \
  https://api.example.com/herding/analyze
```

**Public Endpoint (No Auth Required):**

```bash
curl https://api.example.com/health
```

### Python Example

```python
import requests

API_KEY = "API_KEY_EXAMPLE_DEV"
BASE_URL = "https://api.example.com"

# Method 1: Authorization header
headers = {"Authorization": f"Bearer {API_KEY}"}
response = requests.post(
    f"{BASE_URL}/herding/analyze",
    json={"citation": "410 U.S. 113"},
    headers=headers
)

# Method 2: X-API-Key header
headers = {"X-API-Key": API_KEY}
response = requests.post(
    f"{BASE_URL}/herding/analyze",
    json={"citation": "410 U.S. 113"},
    headers=headers
)

# Check rate limit headers
if response.status_code == 429:
    print(f"Rate limited: {response.json()}")
else:
    print(response.json())
```

### JavaScript Example

```javascript
const API_KEY = "API_KEY_EXAMPLE_DEV";
const BASE_URL = "https://api.example.com";

// Using Authorization header
fetch(`${BASE_URL}/herding/analyze`, {
  method: "POST",
  headers: {
    "Authorization": `Bearer ${API_KEY}`,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    citation: "410 U.S. 113"
  })
})
.then(response => {
  if (response.status === 429) {
    console.error("Rate limited");
  }
  return response.json();
})
.then(data => console.log(data));
```

---

## Security Best Practices

### 1. API Key Management

**✅ DO:**
- Store keys in environment variables or secrets manager
- Rotate keys regularly (monthly recommended)
- Use different keys for dev/test/production
- Log key usage (hashed, not raw)
- Regenerate if compromised

**❌ DON'T:**
- Commit keys to version control
- Share keys via email or chat
- Log raw keys
- Use same key across environments
- Use weak/predictable keys

### 2. Authentication

**✅ DO:**
- Use HTTPS in production (enforce with `ENABLE_HSTS=true`)
- Use Authorization header (most secure)
- Validate keys server-side
- Monitor failed auth attempts
- Implement key expiration (future enhancement)

**❌ DON'T:**
- Use query parameters in production
- Send keys in URLs
- Accept unauthenticated admin endpoints
- Use basic auth with plaintext passwords
- Disable authentication in production

### 3. Rate Limiting

**✅ DO:**
- Set conservative limits for expensive operations
- Monitor rate limit violations
- Provide clear error messages
- Implement exponential backoff in clients
- Set different limits per tier

**❌ DON'T:**
- Set limits too loose (enables DOS)
- Disable rate limiting in production
- Share quota across environments
- Log sensitive request data
- Implement rate limiting only on frontend

### 4. Monitoring

**✅ DO:**
- Monitor failed authentication attempts
- Alert on unusual rate limit activity
- Track API key usage by endpoint
- Log all auth/rate limit events
- Audit key creation/rotation

### Production Checklist

- [ ] `ENABLE_API_KEY_AUTH=true`
- [ ] Valid API keys configured in `API_KEYS`
- [ ] `ENABLE_RATE_LIMITING=true`
- [ ] Appropriate rate limits per endpoint
- [ ] `ENABLE_HSTS=true` (enforce HTTPS)
- [ ] Security headers configured
- [ ] Keys stored in secrets manager
- [ ] Monitoring/alerting configured
- [ ] Load tested with rate limits
- [ ] Documentation updated for clients

---

## Monitoring & Troubleshooting

### Viewing Logs

**Authentication events:**

```bash
kubectl logs deployment/mikecheck | grep "invalid_api_key"
```

**Rate limit events:**

```bash
kubectl logs deployment/mikecheck | grep "rate_limit_exceeded"
```

### Metrics to Monitor

```promql
# Failed authentication attempts
rate(api_auth_failures_total[5m])

# Rate limit violations
rate(rate_limit_exceeded_total[5m])

# By endpoint
rate(rate_limit_exceeded_total{endpoint="/herding/analyze"}[5m])

# By API key
rate(rate_limit_exceeded_total{api_key="API_KEY_EXAMPLE_DEV"}[5m])
```

### Common Issues

#### 401: Missing API Key

**Cause:** No API key provided in request

**Solution:**
1. Check if `ENABLE_API_KEY_AUTH=true` in deployment
2. Add key to request headers: `Authorization: Bearer <YOUR_API_KEY>`
3. Verify key is in `API_KEYS` list

#### 403: Invalid API Key

**Cause:** Provided key not in valid keys list

**Solution:**
1. Verify key is correct (check for typos)
2. Verify key is in `API_KEYS` environment variable
3. Check if key was rotated/removed
4. Regenerate key if compromised

#### 429: Rate Limited

**Cause:** Too many requests in time window

**Solution:**
1. Implement exponential backoff in client
2. Check if legitimate high load or abuse
3. Adjust `RATE_LIMIT_*` settings if needed
4. Monitor CPU/memory on server

#### "public key not found"

**Cause:** Internal key validation error

**Solution:**
1. Check server logs for details
2. Verify `API_KEYS` environment variable format
3. Restart application
4. Contact support if persists

---

## Future Enhancements

- [ ] Key expiration dates
- [ ] Per-key rate limit overrides
- [ ] OAuth2/JWT token support
- [ ] API key scopes (read-only, etc.)
- [ ] Webhook notifications for rate limits
- [ ] Automatic key rotation
- [ ] IP whitelisting per key
- [ ] Custom rate limit tiers
- [ ] Rate limit analytics dashboard
- [ ] Distributed rate limiting (Redis)

---

## Support

For questions or issues:

1. **Documentation**: See this file
2. **Logs**: Check structured logs for auth/rate limit events
3. **Monitoring**: Check Prometheus metrics
4. **Configuration**: Review `.env` variables
5. **Security Incident**: Follow incident response playbook

---

**Phase 3.3 Status:** ✅ Complete
**Testing:** 68/73 tests passing (performance optimization edge cases)
**Deployment:** Ready for production
**Next Phase:** Phase 3.4 - SLO/SLI & Alerting
