# Graceful Shutdown Guide

This document explains how the Legal Research Assistant MCP handles graceful shutdown to ensure zero data loss and minimal service disruption.

**Last Updated:** 2025-12-12
**Component:** FastAPI server (app/api.py)
**Related:** OPERATIONS.md

---

## Overview

Graceful shutdown is the process of stopping the application in a way that:
1. Stops accepting new requests
2. Allows in-flight requests to complete
3. Cleans up resources properly
4. Closes connections cleanly

This prevents:
- Lost requests
- Partial responses to clients
- Corrupted cache data
- Connection errors

---

## Shutdown Sequence

### Local/Docker

When SIGTERM or SIGINT is received:

```
1. Signal handler receives SIGTERM/SIGINT
   ↓
2. Log shutdown signal
   ↓
3. Enter lifespan shutdown handler
   ↓
4. Stop accepting new requests (automatic in Uvicorn)
   ↓
5. Wait for in-flight requests (15 seconds)
   ↓
6. Clean up resources (cache, connections)
   ↓
7. Exit cleanly (exit code 0)
```

### Kubernetes

When Kubernetes needs to terminate a pod:

```
1. kubectl sends SIGTERM to container
   ↓
2. App graceful shutdown (15 seconds to drain)
   ↓
3. Still running? After termination grace period (45 seconds):
   ↓
4. kubectl sends SIGKILL (force kill)
   ↓
5. Pod removed
```

**Configuration:**
- Drain timeout: 15 seconds (app/api.py line 89)
- Termination grace period: 45 seconds (k8s/deployment.yaml line 235)
- Safe margin: 30 seconds for cleanup

---

## Implementation Details

### Signal Handlers

The application registers handlers for two signals:

```python
signal.signal(signal.SIGTERM, _signal_handler)  # Clean shutdown (default)
signal.signal(signal.SIGINT, _signal_handler)   # Interrupt (Ctrl+C)
```

**SIGTERM:** Used by Kubernetes, orchestrators, init systems
**SIGINT:** Used when manually stopping with Ctrl+C

### Lifespan Context Manager

FastAPI's `lifespan` parameter handles startup and shutdown:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # STARTUP - runs when app starts
    # ... register signal handlers ...

    yield  # App runs here

    # SHUTDOWN - runs when app stops
    # ... cleanup and draining ...
```

### Connection Draining

After receiving shutdown signal:

1. **Stop accepting new requests** - Uvicorn stops accepting new connections
2. **Wait for in-flight requests** - 15-second drain window
   - Clients making requests get responses normally
   - New requests are rejected (TCP SYN dropped)
   - Clients should handle reconnection

3. **Force timeout** - After 15 seconds:
   - Any remaining connections forcefully closed
   - Prevents hanging requests from blocking shutdown

### Log Output During Shutdown

```json
{
  "timestamp": "2025-12-12T10:30:45.123456Z",
  "level": "INFO",
  "message": "Shutdown signal received",
  "signal": "SIGTERM",
  "event": "signal_received"
}

{
  "timestamp": "2025-12-12T10:30:45.234567Z",
  "level": "INFO",
  "message": "Application shutdown initiated",
  "event": "shutdown_start"
}

{
  "timestamp": "2025-12-12T10:30:45.345678Z",
  "level": "INFO",
  "message": "Draining connections (waiting 15s for in-flight requests)",
  "event": "draining",
  "timeout_seconds": 15
}

{
  "timestamp": "2025-12-12T10:30:60.456789Z",
  "level": "INFO",
  "message": "Shutdown complete",
  "event": "shutdown_complete"
}
```

---

## Testing Graceful Shutdown

### Local Testing

```bash
# Start server
docker-compose up

# In another terminal, send SIGTERM
docker-compose exec legal-research-mcp kill -TERM 1

# Check logs
docker-compose logs -f legal-research-mcp

# Expected: "Shutdown signal received" followed by cleanup logs
```

### Kubernetes Testing

```bash
# Watch pod during termination
kubectl get pods -n legal-research -w

# Delete a pod (triggers graceful shutdown)
kubectl delete pod -n legal-research legal-research-mcp-xxx

# Check logs during shutdown
kubectl logs -n legal-research legal-research-mcp-xxx --tail=20

# Expected: See "Shutdown signal received" and cleanup logs
```

### Load Testing During Shutdown

Test that in-flight requests are handled properly:

```bash
# Terminal 1: Start server
docker-compose up

# Terminal 2: Send requests in background
for i in {1..100}; do
  curl -X POST http://localhost:8000/herding/analyze \
    -H "Content-Type: application/json" \
    -d '{"citation": "410 U.S. 113"}' &
done

# Terminal 3: Send shutdown signal
docker kill -s SIGTERM <container_id>

# Check: All requests should complete or fail gracefully (not hang)
# Logs should show: "Draining connections..."
# Should not see: timeout errors, hung connections
```

---

## Client Behavior During Shutdown

### What Clients Should Do

1. **Implement retry logic**
   ```python
   # If connection closes, retry with exponential backoff
   import backoff

   @backoff.on_exception(
       backoff.expo,
       ConnectionError,
       max_time=60
   )
   def call_api():
       return requests.post(url, data)
   ```

2. **Set reasonable timeouts**
   ```python
   # Don't wait forever
   response = requests.post(url, timeout=30)
   ```

3. **Handle "Service Unavailable" (503)**
   ```python
   if response.status_code == 503:
       # Service shutting down, reconnect later
       time.sleep(5)
       retry()
   ```

### What Happens During Drain Window (15 seconds)

| Time | Status | Behavior |
|------|--------|----------|
| 0s | Shutdown signal received | App enters drain mode |
| 0-15s | Draining | **Active requests complete normally**, New requests rejected |
| 15s | Drain timeout | Force-close remaining connections |
| 15-45s | Cleanup | Resource cleanup, logs flushing |
| 45s | SIGKILL (K8s) | Pod forcefully terminated if still running |

### Failed Request Example

If client sends request during drain window AFTER active requests have completed:

```
Time: 8 seconds into drain window
Client: sends POST request
Server: TCP connection drops (new requests not accepted)
Client receives: Connection reset by peer
Client should: Retry to another pod or wait and reconnect
```

---

## Kubernetes Specific Details

### Pre-Stop Hook Alternative

The deployment uses a `preStop` lifecycle hook in addition to SIGTERM:

```yaml
lifecycle:
  preStop:
    exec:
      command: ["/bin/sh", "-c", "sleep 15"]
```

**What it does:**
1. Kubernetes sends SIGTERM to container
2. Container starts shutdown process
3. Kubernetes waits for `preStop` to complete (15 seconds)
4. If app still running after `preStop`, grace period continues until `terminationGracePeriodSeconds` (45 seconds total)

**Timeline:**
```
T=0s:  Termination initiated, SIGTERM sent, preStop sleep starts
T=15s: preStop sleep ends
T=15-45s: Application finishing shutdown (lifespan cleanup)
T=45s: SIGKILL sent if still running
```

### Pod Disruption Budget

The deployment has a Pod Disruption Budget (k8s/hpa.yaml):

```yaml
spec:
  minAvailable: 2  # At least 2 pods must be running
```

**Impact on shutdown:**
- Kubernetes tries to maintain 2 pods running during disruptions
- Graceful shutdown of one pod = temporary load increase on others
- HPA may scale up if needed

---

## Monitoring Graceful Shutdown

### Logs to Watch

```bash
# All shutdown events
kubectl logs -n legal-research deployment/legal-research-mcp | \
  jq 'select(.event | contains("shutdown"))'

# Shutdown timing (look for event timestamps)
kubectl logs -n legal-research deployment/legal-research-mcp | \
  jq 'select(.event | contains("shutdown") or contains("draining"))' | \
  jq '.timestamp'
```

### Metrics to Track

```bash
# Number of pods running
kubectl get pods -n legal-research --no-headers | wc -l

# Pod terminating status
kubectl get pods -n legal-research -o wide | grep Terminating

# Request latency during rollout (Prometheus)
# histogram_quantile(0.99, rate(mcp_tool_duration_seconds_bucket[1m]))
```

### Alerts to Set Up

```yaml
# Alert if pod takes too long to shutdown
- alert: PodSlowShutdown
  expr: time() - pod_started_at > 60  # Longer than expected
  for: 5m
  annotations:
    summary: "Pod {{ $labels.pod }} taking too long to shut down"

# Alert if requests failing during deployment
- alert: HighErrorRateDuringDeployment
  expr: rate(mcp_tool_calls_total{status="error"}[1m]) > 0.10  # >10% error rate
  for: 2m
  annotations:
    summary: "High error rate during deployment"
```

---

## Troubleshooting

### Pod Stuck in Terminating State

**Problem:** Pod shows "Terminating" but doesn't exit

**Diagnosis:**
```bash
# Check pod events
kubectl describe pod -n legal-research <pod-name>

# Check if app is writing logs (signs of life)
kubectl logs -n legal-research <pod-name> --tail=1 --follow

# Check if app has zombie processes
kubectl exec -n legal-research <pod-name> -- ps aux
```

**Solution:**
```bash
# If hung, manually terminate (use with caution)
kubectl delete pod --grace-period=5 -n legal-research <pod-name>

# Or delete immediately (may cause incomplete cleanup)
kubectl delete pod --grace-period=0 --force -n legal-research <pod-name>
```

### Requests Failing During Rollout

**Problem:** Clients getting connection errors during deployment

**Cause:** Drain window too short or clients not retrying

**Solution:**
```bash
# Increase drain timeout in app/api.py (line 89)
drain_timeout = 30  # increased from 15

# Ensure client has retry logic with exponential backoff
# Add load balancer session stickiness to keep clients on active pods
```

### High Error Rate During Rolling Update

**Problem:** Error rate spikes when pods restart

**Investigation:**
```bash
# Check if error rate correlates with pod restarts
kubectl get events -n legal-research --sort-by='.lastTimestamp' | tail -20

# Check logs during affected time window
kubectl logs -n legal-research deployment/legal-research-mcp \
  --since=5m --timestamps=true | grep ERROR
```

**Solutions:**
1. Increase HPA min replicas to spread load
2. Increase drain timeout for slower requests
3. Use Pod Disruption Budget to limit concurrent disruptions
4. Implement circuit breaker on client side

---

## Production Best Practices

### Before Production

- [ ] Test graceful shutdown with docker-compose locally
- [ ] Test with load generator (simulate in-flight requests)
- [ ] Verify client retry logic works
- [ ] Check logs for "Shutdown complete" message
- [ ] Verify termination grace period (45s) is appropriate
- [ ] Set alerts on shutdown errors

### During Production

- [ ] Monitor pod shutdown logs during deployments
- [ ] Track request error rate during rolling updates
- [ ] Verify no requests "stuck" in shutdown
- [ ] Monitor error logs for shutdown-related issues

### Ongoing

- [ ] Review shutdown logs weekly
- [ ] Test failover procedures quarterly
- [ ] Update drain timeout if needed based on typical request duration
- [ ] Document any custom shutdown logic

---

## Related Documentation

- [OPERATIONS.md](./OPERATIONS.md) - Operational procedures
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Deployment guide
- [k8s/deployment.yaml](./k8s/deployment.yaml) - Kubernetes configuration
- [k8s/README.md](./k8s/README.md) - Kubernetes guide

---

## Quick Reference

```bash
# Test graceful shutdown locally
docker run -it legal-research-mcp:latest &
sleep 5
kill -TERM $!  # or Ctrl+C

# Monitor during K8s rollout
kubectl rollout status deployment/legal-research-mcp -n legal-research -w
kubectl logs -n legal-research deployment/legal-research-mcp --follow

# Check shutdown events
kubectl logs -n legal-research deployment/legal-research-mcp | grep -i shutdown
```

---

**For operational procedures during production incidents, see [OPERATIONS.md](./OPERATIONS.md).**
