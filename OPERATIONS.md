# Operations Guide - Legal Research Assistant MCP

This guide provides essential operational procedures for running and maintaining the Legal Research Assistant MCP in production.

**Last Updated:** 2025-12-12
**Target Audience:** SREs, DevOps engineers, operations teams

---

## Table of Contents

1. [Health Monitoring](#health-monitoring)
2. [Common Failure Modes](#common-failure-modes)
3. [Log Parsing & Analysis](#log-parsing--analysis)
4. [Performance Tuning](#performance-tuning)
5. [Capacity Planning](#capacity-planning)
6. [Backup & Recovery](#backup--recovery)
7. [Incident Response](#incident-response)
8. [Monitoring Best Practices](#monitoring-best-practices)
9. [Scaling Guidelines](#scaling-guidelines)
10. [Maintenance Windows](#maintenance-windows)

---

## Health Monitoring

### Health Check Endpoint

The application exposes a health check at `GET /health`:

```bash
curl http://localhost:8000/health
```

**Healthy response (200 OK):**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2025-12-12T10:30:45.123456Z",
  "checks": {
    "api_connectivity": "ok",
    "cache": "ok"
  }
}
```

**Degraded response (200 OK with warnings):**
```json
{
  "status": "degraded",
  "timestamp": "2025-12-12T10:30:45.123456Z",
  "checks": {
    "api_connectivity": "warning - circuit breaker open",
    "cache": "ok"
  },
  "message": "CourtListener API temporarily unavailable, using cache"
}
```

**Unhealthy response (503 Service Unavailable):**
```json
{
  "status": "unhealthy",
  "timestamp": "2025-12-12T10:30:45.123456Z",
  "checks": {
    "api_connectivity": "error - all retries exhausted",
    "cache": "error - disk full"
  },
  "message": "Critical dependencies unavailable"
}
```

### Probe Configuration (Kubernetes)

Three health check probes are configured:

#### Startup Probe
- **Purpose:** Detect slow-starting containers
- **Interval:** 5 seconds, max 60 seconds
- **Action:** If fails after 60s, kill container and restart

When to investigate:
- Startup probe failing consistently → Check logs for initialization errors
- Taking > 20 seconds to start → May need to increase memory/CPU

#### Readiness Probe
- **Purpose:** Determine if container is ready for traffic
- **Interval:** 5 seconds
- **Action:** Removes from load balancer if fails

When to investigate:
- Readiness probe failing → Pod is returning 503/unhealthy
- Causes: API rate limited, cache corrupted, disk full

#### Liveness Probe
- **Purpose:** Detect hung containers
- **Interval:** 10 seconds
- **Action:** Restart container if fails 3 times

When to investigate:
- Liveness probe failing → Container appears hung
- Causes: Deadlock, infinite loop, resource exhaustion

### Kubernetes Health Check Examples

```bash
# Check liveness probe status
kubectl describe pod -n legal-research <pod-name> | grep "Liveness"

# Check readiness probe status
kubectl describe pod -n legal-research <pod-name> | grep "Readiness"

# Manually test health endpoint
kubectl port-forward -n legal-research pod/<pod-name> 8000:8000
curl http://localhost:8000/health

# Check all pod statuses
kubectl get pods -n legal-research -o wide

# Show detailed pod conditions
kubectl get pods -n legal-research -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}'
```

---

## Common Failure Modes

### 1. Circuit Breaker Open (API Unavailable)

**Symptoms:**
- Error logs: `CircuitBreakerOpenError`
- Health check: `"api_connectivity": "warning - circuit breaker open"`
- Requests fail with 503

**Root Causes:**
- CourtListener API down or unreachable
- Network connectivity issues
- API rate limiting (429 responses)
- API authentication failure (401)

**Recovery Steps:**

```bash
# 1. Check application logs for API errors
docker logs legal-research-mcp | grep -E "CircuitBreakerOpen|429|401"

# 2. Check CourtListener API status
curl https://www.courtlistener.com/api/rest/v4/opinions/

# 3. Verify network connectivity
docker exec legal-research-mcp curl -i https://www.courtlistener.com/

# 4. Check API key validity
curl -H "Authorization: Token $COURTLISTENER_API_KEY" \
  https://www.courtlistener.com/api/rest/v4/opinions/

# 5. Monitor error rate
# Circuit breaker opens after 5 consecutive failures
# It automatically resets after 60 seconds
# If opening repeatedly:
#   - Check API rate limit (headers: X-RateLimit-Remaining)
#   - Reduce concurrent requests (scale down pods)
#   - Increase cache TTL to reduce API calls

# 6. Escalate if API is down
# Contact CourtListener support or check status page
```

**Prevention:**
- Monitor `X-RateLimit-Remaining` header
- Use "smart" fetch strategy (default) to reduce API calls
- Set cache TTL appropriately (see DEPLOYMENT.md)
- Implement request queuing for bursty traffic

---

### 2. Pod CrashLoopBackOff

**Symptoms:**
- Pod status: `CrashLoopBackOff`
- Container restarting repeatedly
- Logs show application error

**Investigation:**

```bash
# 1. Check pod events
kubectl describe pod -n legal-research <pod-name>

# 2. View logs from previous run
kubectl logs -n legal-research <pod-name> --previous

# 3. Common causes and solutions:

# Missing environment variable
# Error: "COURTLISTENER_API_KEY not set"
# Solution: Verify secret is created
kubectl get secret legal-research-secrets -n legal-research

# Invalid configuration
# Error: "Invalid value for MODE: heavy_mode"
# Solution: Check valid modes: light | standard | heavy

# Memory exhaustion
# Error: "Killed" in logs
# Solution: Increase memory limits in deployment.yaml

# Disk space full
# Error: "No space left on device"
# Solution: Check cache directory, clear old cache entries
```

**Recovery:**

```bash
# 1. Delete problematic pods (replacements will be created)
kubectl delete pod -n legal-research <pod-name>

# 2. Check if new pods start successfully
kubectl get pods -n legal-research -w

# 3. If still crashing, fix underlying issue and restart deployment
kubectl rollout restart deployment/legal-research-mcp -n legal-research
```

---

### 3. Memory Exhaustion (OOMKilled)

**Symptoms:**
- Pod status: `OOMKilled` (exit code 137)
- High memory usage: approaching container limit
- Performance degradation before crash

**Investigation:**

```bash
# 1. Check current memory usage
kubectl top pods -n legal-research

# 2. Check container memory limit
kubectl get deployment legal-research-mcp -n legal-research \
  -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}'

# 3. View memory trend (requires Prometheus)
# Query: container_memory_usage_bytes{pod="legal-research-mcp-*"}

# 4. Identify memory leak
# Check if memory grows linearly over time (leak) or stays constant (normal)
```

**Common Causes:**

1. **Cache growing too large**
   ```bash
   # Check cache directory size
   kubectl exec -n legal-research <pod-name> -- du -sh /app/.cache

   # Solution: Clear cache
   kubectl exec -n legal-research <pod-name> -- rm -rf /app/.cache/*
   ```

2. **Vector store (ChromaDB) storing too much**
   ```bash
   # Check vector store size
   kubectl exec -n legal-research <pod-name> -- du -sh /app/chroma_db

   # Solution: Clear old embeddings (requires manual cleanup)
   ```

3. **Memory leak in application**
   ```bash
   # Monitor memory over time
   kubectl exec -n legal-research <pod-name> -- python -c \
     "import psutil; import time; [print(f'{i}: {psutil.Process().memory_info().rss / 1e6:.1f}MB') for i in range(10)]"

   # Solution: File a bug or upgrade to patched version
   ```

**Resolution:**

```bash
# 1. Increase memory limit (temporary)
kubectl set resources deployment/legal-research-mcp \
  --limits=memory=4Gi \
  -n legal-research

# 2. Clear cache (if cache is the issue)
kubectl exec -n legal-research <pod-name> -- rm -rf /app/.cache/*

# 3. Monitor if memory usage improves
kubectl top pods -n legal-research -w

# 4. If issue persists, scale down to single pod for debugging
kubectl scale deployment legal-research-mcp --replicas=1 -n legal-research

# 5. Once fixed, scale back up
kubectl scale deployment legal-research-mcp --replicas=3 -n legal-research
```

---

### 4. High Error Rate (> 5%)

**Symptoms:**
- Alerts firing: "High error rate"
- Application logs showing exceptions
- Clients reporting failures

**Investigation:**

```bash
# 1. Check error logs (last 1 hour)
kubectl logs -n legal-research deployment/legal-research-mcp --since=1h | grep ERROR

# 2. Count errors by type
kubectl logs -n legal-research deployment/legal-research-mcp --since=1h | \
  grep ERROR | grep -oE '"(.*?)"' | sort | uniq -c | sort -rn

# 3. Check if errors are from specific tool
# Errors might be concentrated in one operation (e.g., quote_verify is failing)
kubectl logs -n legal-research deployment/legal-research-mcp --since=1h | \
  grep -E 'tool_name.*ERROR' | head -20

# 4. Check Prometheus metrics
# Query: rate(mcp_tool_calls_total{status="error"}[5m])
```

**Common Error Patterns:**

1. **API Errors (429, 401, 500)**
   - 429: Rate limited → reduce concurrent requests
   - 401: Invalid API key → check COURTLISTENER_API_KEY
   - 500: CourtListener API error → wait and retry

2. **Timeout Errors**
   - Increase timeout settings in CONFIG
   - Check network latency

3. **Quote Matching Failures**
   - Normal if quote not found in opinion
   - Check request parameters

**Recovery:**

```bash
# 1. If API rate limited, scale down temporarily
kubectl scale deployment legal-research-mcp --replicas=1 -n legal-research

# 2. Monitor error rate
kubectl logs -n legal-research deployment/legal-research-mcp -f | grep ERROR

# 3. Once error rate drops below threshold, scale back up
kubectl scale deployment legal-research-mcp --replicas=3 -n legal-research
```

---

### 5. Slow Response Times (p99 > 5s)

**Symptoms:**
- Alerts: "High latency"
- Clients report slow responses
- Prometheus: `histogram_quantile(0.99, mcp_tool_duration_seconds) > 5`

**Investigation:**

```bash
# 1. Check which tools are slow
# Query in Prometheus:
# histogram_quantile(0.99, rate(mcp_tool_duration_seconds_bucket[5m])) by (tool_name)

# 2. Check if specific operations are problematic
kubectl logs -n legal-research deployment/legal-research-mcp --since=1h | \
  grep "tool_name.*elapsed_ms" | grep "elapsed_ms.*[3-9][0-9]{3,}" | head -10

# 3. Check API response times
# Monitor CourtListener API latency

# 4. Check system resources
kubectl top pods -n legal-research
kubectl top nodes
```

**Common Causes & Solutions:**

1. **Slow CourtListener API**
   - Normal, especially for full-text fetches (500-1000ms each)
   - Solution: Use "smart" fetch strategy (default) to minimize API calls

2. **Citation Network Building (Slow)**
   - Network traversal takes time proportional to depth
   - Depth 1: ~1-2 seconds
   - Depth 2: ~2-4 seconds
   - Depth 3: ~4-8 seconds
   - Solution: Reduce max_network_depth for speed or accept longer times

3. **Quote Matching (Slow)**
   - O(n²) algorithm for large opinion text
   - Solution: Longer opinions take longer to match; use fuzzy matching threshold

4. **System Resource Contention**
   - Other pods using CPU/memory
   - Solution: Scale up cluster, increase pod resources

---

## Log Parsing & Analysis

### Log Format

Application logs are in JSON format (structured logging):

```json
{
  "timestamp": "2025-12-12T10:30:45.123456+00:00",
  "level": "INFO",
  "logger": "app.tools.treatment",
  "message": "Tool call completed",
  "correlation_id": "a1b2c3d4-e5f6-...",
  "tool_name": "check_case_validity",
  "elapsed_ms": 1250.5,
  "event": "tool_end"
}
```

### Extracting Useful Information

```bash
# Count requests by tool
docker logs legal-research-mcp | jq -r '.tool_name' | sort | uniq -c

# Find slow requests (> 2 seconds)
docker logs legal-research-mcp | jq 'select(.elapsed_ms > 2000)' | jq '.tool_name, .elapsed_ms'

# Find errors
docker logs legal-research-mcp | jq 'select(.level == "ERROR")'

# Count errors by type
docker logs legal-research-mcp | jq -r 'select(.level == "ERROR") | .message' | sort | uniq -c

# Trace specific request (by correlation ID)
CORR_ID="a1b2c3d4-e5f6-..."
docker logs legal-research-mcp | jq "select(.correlation_id == \"$CORR_ID\")"

# Check API call metrics
docker logs legal-research-mcp | jq 'select(.event == "api_call")' | \
  jq -r '[.timestamp, .status_code, .elapsed_ms] | @csv'
```

### Kubernetes Log Analysis

```bash
# View logs from all pods
kubectl logs -n legal-research deployment/legal-research-mcp -f

# View logs from specific pod
kubectl logs -n legal-research legal-research-mcp-xxx -f

# View logs with timestamps
kubectl logs -n legal-research deployment/legal-research-mcp --timestamps=true

# View last N lines
kubectl logs -n legal-research deployment/legal-research-mcp --tail=100

# View logs since specific time
kubectl logs -n legal-research deployment/legal-research-mcp --since=10m

# Save logs to file
kubectl logs -n legal-research deployment/legal-research-mcp > logs.json
```

### Log Aggregation (ELK, Splunk, DataDog)

If using log aggregation:

```bash
# Search for errors
{
  "query": {
    "bool": {
      "must": [
        {"match": {"level": "ERROR"}},
        {"match": {"namespace": "legal-research"}}
      ]
    }
  }
}

# Search for slow requests
{
  "query": {
    "range": {
      "elapsed_ms": {"gte": 5000}
    }
  }
}

# Search for specific tool failures
{
  "query": {
    "bool": {
      "must": [
        {"match": {"tool_name": "check_case_validity"}},
        {"match": {"status": "error"}}
      ]
    }
  }
}
```

---

## Performance Tuning

### Baseline Performance

Under standard load (single pod, standard mode):

| Operation | p50 | p99 | Notes |
|-----------|-----|-----|-------|
| Health check | <50ms | <100ms | Very fast |
| Case lookup | 800ms | 2000ms | Limited by API |
| Citation network (depth 2) | 2.5s | 4.5s | API bound |
| Quote verification | 1.5s | 3.5s | String matching |
| Batch quote verify (10) | 2.5s | 5.5s | Sequential fetches |

### Tuning Parameters

#### 1. Reduce API Calls (Most Impactful)

```bash
# Increase cache TTL
COURTLISTENER_TTL_METADATA=172800    # 2 days (default: 24h)
COURTLISTENER_TTL_TEXT=1209600       # 14 days (default: 7d)
COURTLISTENER_TTL_SEARCH=14400       # 4 hours (default: 1h)

# Switch to smart fetch strategy (default, already optimal)
FETCH_FULL_TEXT_STRATEGY=smart

# Reduce max network depth (less API calls, smaller graphs)
NETWORK_MAX_DEPTH=2    # Faster, less comprehensive (default: 3)

# Reduce max citing cases
MAX_CITING_CASES=50    # Faster analysis (default: 100)
```

**Expected improvement:** 10-30% faster, 20-50% fewer API calls

#### 2. Increase Parallelism

```bash
# Increase pod replicas (spreads load)
kubectl scale deployment legal-research-mcp --replicas=5 -n legal-research

# Or use HPA with lower thresholds
# Edit k8s/hpa.yaml:
# averageUtilization: 60  # Scale at 60% instead of 70%
```

**Expected improvement:** Handles more concurrent requests

#### 3. Optimize Resource Limits

```bash
# If pods frequently hitting CPU limit:
kubectl set resources deployment/legal-research-mcp \
  --limits=cpu=2000m --requests=cpu=500m \
  -n legal-research

# If memory usage is low, can reduce:
kubectl set resources deployment/legal-research-mcp \
  --limits=memory=1Gi --requests=memory=256Mi \
  -n legal-research
```

#### 4. Network Optimization

```bash
# If API calls are slow, check network:
kubectl exec -n legal-research <pod-name> -- \
  curl -w "@curl-format.txt" -o /dev/null -s https://www.courtlistener.com/

# Enable connection pooling (automatic in httpx)
# Reuse TCP connections across requests
```

### Measuring Performance Impact

```bash
# Before and after measurements
# 1. Record baseline latency
kubectl logs -n legal-research deployment/legal-research-mcp --since=30m | \
  jq -r '.elapsed_ms' | awk '{sum+=$1; n++} END {print sum/n" ms average"}'

# 2. Apply tuning change
kubectl set env deployment/legal-research-mcp \
  MAX_CITING_CASES=50 \
  -n legal-research

# 3. Wait for rollout
kubectl rollout status deployment/legal-research-mcp -n legal-research

# 4. Record new latency
kubectl logs -n legal-research deployment/legal-research-mcp --since=30m | \
  jq -r '.elapsed_ms' | awk '{sum+=$1; n++} END {print sum/n" ms average"}'

# 5. Compare results
```

---

## Capacity Planning

### Resource Sizing

**Per-Pod Resources:**

| Mode | CPU Request | Memory Request | CPU Limit | Memory Limit |
|------|-------------|----------------|-----------|--------------|
| Development | 100m | 128Mi | 500m | 512Mi |
| Light | 200m | 256Mi | 500m | 512Mi |
| Standard | 250m | 512Mi | 1000m | 2Gi |
| Heavy | 500m | 1Gi | 2000m | 4Gi |

**Scaling Recommendations:**

- **< 100 req/sec:** 2-3 pods (standard mode)
- **100-500 req/sec:** 5-10 pods (standard mode)
- **500-1000 req/sec:** 10-20 pods (consider Heavy mode)
- **> 1000 req/sec:** Multiple deployments or horizontal scaling

### Cost Estimation (AWS EKS)

Assuming `t3.medium` nodes ($0.0416/hour):

```
3 pods (standard): ~$30/month
10 pods (standard): ~$100/month
20 pods (heavy): ~$200/month
```

Add:
- Data transfer: ~$0.02/GB
- Storage: ~$0.10/GB/month for cache
- CourtListener API: Free tier (100 requests/day), paid tiers available

### Metrics to Monitor

```bash
# CPU utilization
kubectl top pods -n legal-research
# Target: 50-70% average, <80% peak

# Memory utilization
kubectl top pods -n legal-research
# Target: 50-75% of limit

# Request latency (p99)
# Prometheus: histogram_quantile(0.99, rate(mcp_tool_duration_seconds_bucket[5m]))
# Target: <5 seconds

# Error rate
# Prometheus: rate(mcp_tool_calls_total{status="error"}[5m])
# Target: <1%

# API call rate
# Prometheus: rate(api_calls_total[5m])
# Target: varies by subscription
```

---

## Backup & Recovery

### What to Back Up

1. **Configuration** (ConfigMap)
2. **Secrets** (API Key)
3. **Cache Data** (Optional, can be recreated)

### Backup Procedures

```bash
# 1. Backup ConfigMap
kubectl get configmap legal-research-config -n legal-research -o yaml > configmap-backup.yaml

# 2. Backup Secret (KEEP SECURE!)
kubectl get secret legal-research-secrets -n legal-research -o yaml > secret-backup.yaml
chmod 600 secret-backup.yaml

# 3. Backup all resources
kubectl get all -n legal-research -o yaml > full-backup.yaml

# 4. Store securely
# Use encrypted storage, version control (for configs, NOT secrets)
```

### Recovery Procedures

```bash
# 1. Restore ConfigMap
kubectl apply -f configmap-backup.yaml

# 2. Restore Secret
kubectl apply -f secret-backup.yaml

# 3. Verify restoration
kubectl get configmap,secret -n legal-research

# 4. Restart pods to pick up restored config
kubectl rollout restart deployment/legal-research-mcp -n legal-research
```

### Disaster Recovery

```bash
# Scenario: Lost all pod state, need to recreate

# 1. Ensure namespace exists
kubectl create namespace legal-research

# 2. Restore secrets (CRITICAL)
kubectl apply -f secret-backup.yaml

# 3. Restore configuration
kubectl apply -f configmap-backup.yaml

# 4. Restore RBAC
kubectl apply -f k8s/rbac.yaml

# 5. Restore deployment
kubectl apply -f k8s/deployment.yaml

# 6. Restore service
kubectl apply -f k8s/service.yaml

# 7. Restore autoscaling
kubectl apply -f k8s/hpa.yaml

# 8. Verify
kubectl get all -n legal-research
```

---

## Incident Response

### Incident Classification

| Severity | Response Time | Example |
|----------|---------------|---------|
| P1 (Critical) | 5 minutes | All pods down, no API access |
| P2 (High) | 15 minutes | 50%+ error rate, significant latency |
| P3 (Medium) | 1 hour | Single pod failing, cache issues |
| P4 (Low) | 4 hours | Minor performance degradation |

### Incident Response Playbook

#### P1: All Services Down

```bash
# 1. Immediate triage (< 1 minute)
kubectl get pods -n legal-research
kubectl get svc -n legal-research
docker ps  # If Docker-based

# 2. Check basic connectivity (< 2 minutes)
curl -i http://service-ip:8000/health

# 3. Check recent events
kubectl describe deployment -n legal-research legal-research-mcp | grep -A 20 "Events"

# 4. Check logs
kubectl logs -n legal-research deployment/legal-research-mcp --tail=100

# 5. If issue not obvious, take emergency action:
# Option A: Rollback to last known good version
kubectl rollout undo deployment/legal-research-mcp -n legal-research

# Option B: Scale down and scale back up (restart)
kubectl scale deployment legal-research-mcp --replicas=0 -n legal-research
sleep 5
kubectl scale deployment legal-research-mcp --replicas=3 -n legal-research

# 6. Monitor recovery
kubectl rollout status deployment/legal-research-mcp -n legal-research -w

# 7. Once recovered, investigate root cause
# See "Post-Incident Investigation" below
```

#### P2: Degraded Service

```bash
# 1. Check error rate and latency
kubectl logs -n legal-research deployment/legal-research-mcp --since=5m | \
  jq 'select(.level == "ERROR")' | wc -l

# 2. Scale up to handle load
kubectl scale deployment legal-research-mcp --replicas=10 -n legal-research

# 3. Monitor metrics
kubectl top pods -n legal-research -w

# 4. If still degraded, check API
curl -I https://www.courtlistener.com/api/rest/v4/

# 5. If API is down, communicate status to users
# Implement graceful degradation (responses from cache)

# 6. Once stable, investigate cause
```

### Post-Incident Investigation

```bash
# 1. Gather logs from incident window
START_TIME="2025-12-12T10:00:00Z"
END_TIME="2025-12-12T10:15:00Z"

kubectl logs -n legal-research deployment/legal-research-mcp \
  --since-time=$START_TIME --until-time=$END_TIME > incident-logs.json

# 2. Analyze error patterns
jq -r '.message' incident-logs.json | grep -i error | sort | uniq -c

# 3. Check system events
kubectl describe nodes  # Check for node issues
kubectl top nodes  # Check resource utilization

# 4. Document findings
# - Root cause
# - Timeline of events
# - Actions taken
# - Prevention for future

# 5. Create ticket for follow-up (if needed)
```

---

## Monitoring Best Practices

### Key Metrics to Monitor

```
Application Metrics:
- Request latency (p50, p95, p99)
- Error rate (errors per minute, error percentage)
- Request rate (requests per second)
- Cache hit ratio
- API call count

Infrastructure Metrics:
- CPU utilization (should stay < 80%)
- Memory utilization (should stay < 80%)
- Disk usage (cache directory)
- Network I/O
- Pod count

Dependency Metrics:
- CourtListener API response time
- API success rate (should be > 99%)
- Rate limit remaining
```

### Alert Thresholds

```yaml
Alerts:
  - Error rate > 5% for 5 minutes → Page on-call
  - Latency p99 > 5 seconds for 10 minutes → Page on-call
  - Pod memory > 90% for 5 minutes → Alert (scale up)
  - Pod CPU > 90% for 10 minutes → Alert (scale up)
  - Cache hit ratio < 70% for 30 minutes → Alert (check cache)
  - Circuit breaker open > 5 minutes → Alert (API issue)
  - Pod not ready for > 5 minutes → Alert (may be crashing)
```

### Grafana Dashboards (Recommended Panels)

```
Dashboard: Legal Research MCP Health
├─ Requests per second
├─ Error rate (%)
├─ Latency (p50, p95, p99)
├─ Pod count
├─ CPU utilization
├─ Memory utilization
├─ Cache hit ratio
└─ API call rate

Dashboard: Legal Research MCP Details
├─ Requests by tool
├─ Error rate by tool
├─ Latency by tool
├─ API response time
└─ Cache size
```

---

## Scaling Guidelines

### Horizontal Scaling (Adding Pods)

**When to scale up:**
- CPU utilization > 70%
- Memory utilization > 80%
- Request queue building up
- Error rate increasing

**How to scale:**

```bash
# Manual scaling
kubectl scale deployment legal-research-mcp --replicas=5 -n legal-research

# Automatic scaling (HPA - already configured)
# Scales automatically between 3-10 replicas based on CPU/memory
# Check HPA status:
kubectl get hpa -n legal-research
kubectl describe hpa legal-research-mcp-hpa -n legal-research
```

### Vertical Scaling (Increasing Pod Resources)

**When to scale up:**
- Single pod at max capacity
- Long-running operations needing more memory
- Need to reduce latency variance

**How to scale:**

```bash
# Increase resource requests/limits
kubectl set resources deployment/legal-research-mcp \
  --requests=cpu=500m,memory=1Gi \
  --limits=cpu=2000m,memory=4Gi \
  -n legal-research

# Requires rolling restart
kubectl rollout status deployment/legal-research-mcp -n legal-research -w
```

### Performance Optimization (Before Scaling)

Before adding more pods/resources, optimize:

1. **Reduce API calls**
   - Increase cache TTL
   - Use "smart" fetch strategy
   - Reduce network depth

2. **Reduce query complexity**
   - Limit citing cases analyzed
   - Use lighter mode

3. **Improve caching**
   - Pre-warm cache with popular cases
   - Monitor cache hit ratio
   - Clear expired cache

---

## Maintenance Windows

### Planned Maintenance

```bash
# Schedule: Sunday 2-3 AM UTC (low traffic)

# 1. Announce maintenance (send notification to users)
# "Scheduled maintenance: xxx service will have 5-10 min downtime"

# 2. Update deployment to new version
kubectl set image deployment/legal-research-mcp \
  api=legal-research-mcp:v0.2.0 \
  -n legal-research

# 3. Monitor rollout
kubectl rollout status deployment/legal-research-mcp -n legal-research -w

# 4. Verify health
curl http://service-ip:8000/health

# 5. Run smoke tests
# Call a few critical endpoints to ensure they work

# 6. Communicate completion to users
```

### Zero-Downtime Deployment

The current setup supports zero-downtime deployments:

```bash
# 1. Update image in deployment
kubectl set image deployment/legal-research-mcp \
  api=legal-research-mcp:v0.2.0 \
  -n legal-research

# 2. Rolling update automatically happens:
#    - Start new pod with new version
#    - Wait for readiness probe to pass
#    - Remove load from old pod (drain)
#    - Terminate old pod
#    - Repeat until all updated

# 3. In-flight requests are gracefully drained
# 4. No manual intervention needed
# 5. Instant rollback available if needed
```

### Configuration Updates

```bash
# Update ConfigMap
kubectl set env configmap/legal-research-config \
  MODE=heavy \
  MAX_CITING_CASES=150 \
  -n legal-research

# Rolling restart to pick up new config
kubectl rollout restart deployment/legal-research-mcp -n legal-research

# Verify
kubectl rollout status deployment/legal-research-mcp -n legal-research
```

---

## Emergency Procedures

### Kill All Traffic (Emergency Stop)

```bash
# If service is causing cascading failure:

# 1. Scale to zero (immediately stop all requests)
kubectl scale deployment legal-research-mcp --replicas=0 -n legal-research

# 2. Update DNS/routing to point elsewhere
# (Or drain load balancer)

# 3. Investigate root cause in logs
kubectl logs -n legal-research deployment/legal-research-mcp --previous

# 4. Fix issue and redeploy

# 5. Scale back up gradually
kubectl scale deployment legal-research-mcp --replicas=1 -n legal-research
sleep 2
kubectl scale deployment legal-research-mcp --replicas=3 -n legal-research
```

### Circuit Breaker Forced Reset

```bash
# If circuit breaker is stuck open but API is actually healthy:

# 1. Verify API is actually working
curl -I https://www.courtlistener.com/api/rest/v4/

# 2. Force pod restart (circuit breaker resets on restart)
kubectl delete pod -n legal-research <pod-name>

# 3. Pod will be replaced automatically

# 4. Verify circuit breaker is now closed
kubectl logs -n legal-research deployment/legal-research-mcp | grep -i circuit
```

---

## Support Escalation

**Level 1:** On-call engineer (responds to alerts)
- Check health endpoint
- Review recent logs
- Check CourtListener API status
- Can restart pods, scale up/down

**Level 2:** Site Reliability Engineer (P1 incidents)
- Deep dive into logs and metrics
- Investigate infrastructure issues
- Can rollback deployments, update secrets
- Contact CourtListener support if needed

**Level 3:** Platform/Architecture team
- Design changes for reliability
- Capacity planning
- Long-term optimization

---

## Quick Reference

### Most Common Commands

```bash
# Check health
kubectl get pods -n legal-research
curl http://service-ip:8000/health

# View logs
kubectl logs -n legal-research deployment/legal-research-mcp -f

# Scale up
kubectl scale deployment legal-research-mcp --replicas=5 -n legal-research

# Restart
kubectl rollout restart deployment/legal-research-mcp -n legal-research

# Rollback
kubectl rollout undo deployment/legal-research-mcp -n legal-research

# Update config
kubectl set env deployment/legal-research-mcp MODE=heavy -n legal-research
```

---

**See [DEPLOYMENT.md](./DEPLOYMENT.md) for deployment procedures and [k8s/README.md](./k8s/README.md) for Kubernetes-specific guides.**
