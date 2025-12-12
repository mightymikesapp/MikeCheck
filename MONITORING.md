# Monitoring & Observability Guide

This guide explains how to set up comprehensive monitoring for the Legal Research Assistant MCP using Prometheus, Grafana, and log aggregation.

**Last Updated:** 2025-12-12
**Scope:** Metrics collection, log aggregation, dashboards, alerts
**Related:** OPERATIONS.md, GRACEFUL_SHUTDOWN.md

---

## Table of Contents

1. [Overview](#overview)
2. [Prometheus Metrics](#prometheus-metrics)
3. [Log Aggregation](#log-aggregation)
4. [Grafana Dashboards](#grafana-dashboards)
5. [Alerting Rules](#alerting-rules)
6. [SLO/SLI Definitions](#sloslii-definitions)
7. [Production Setup](#production-setup)

---

## Overview

### What We Monitor

The application provides visibility into:

- **Application Metrics** (Prometheus)
  - Tool call volumes, duration, success/error rates
  - API request latency and status codes
  - CourtListener API call patterns and errors
  - Cache hit/miss rates and size
  - Circuit breaker state changes

- **Structured Logs** (JSON)
  - Every tool invocation with timing
  - HTTP requests with full context
  - Errors with stack traces
  - Shutdown events
  - Configuration changes

- **Performance Indicators**
  - P50, P95, P99 latencies
  - Error rates and types
  - Cache effectiveness
  - API availability

### Why This Matters

Production visibility enables:
- **Quick incident response** - See what's broken in seconds
- **Capacity planning** - Understand load patterns
- **SLO tracking** - Know if you're meeting objectives
- **Root cause analysis** - Correlate logs and metrics
- **Cost optimization** - Right-size infrastructure

---

## Prometheus Metrics

### Available Metrics

#### Tool Metrics

```
# Counter: Total tool invocations
mcp_tool_calls_total{tool_name="check_case_validity", status="success"} 1245
mcp_tool_calls_total{tool_name="check_case_validity", status="error"} 12

# Histogram: Tool execution duration (seconds)
mcp_tool_duration_seconds_bucket{tool_name="check_case_validity", le="0.05"} 10
mcp_tool_duration_seconds_bucket{tool_name="check_case_validity", le="0.1"} 100
mcp_tool_duration_seconds_bucket{tool_name="check_case_validity", le="1.0"} 1200
mcp_tool_duration_seconds_sum{tool_name="check_case_validity"} 1850.5
mcp_tool_duration_seconds_count{tool_name="check_case_validity"} 1245

# Counter: Tool errors by type
mcp_tool_errors_total{tool_name="check_case_validity", error_type="timeout"} 8
mcp_tool_errors_total{tool_name="check_case_validity", error_type="api_error"} 4
```

#### API Request Metrics

```
# Counter: Total HTTP requests
api_requests_total{method="POST", endpoint="/herding/analyze", status_code="200"} 1200
api_requests_total{method="POST", endpoint="/herding/analyze", status_code="500"} 5

# Histogram: HTTP request latency
api_request_duration_seconds_bucket{method="POST", endpoint="/herding/analyze", le="0.1"} 50
api_request_duration_seconds_bucket{method="POST", endpoint="/herding/analyze", le="1.0"} 1150
api_request_duration_seconds_sum{method="POST", endpoint="/herding/analyze"} 850.5
api_request_duration_seconds_count{method="POST", endpoint="/herding/analyze"} 1200

# Counter: Request errors
api_request_errors_total{method="POST", endpoint="/herding/analyze", error_type="ValueError"} 3
```

#### CourtListener API Metrics

```
# Counter: API calls to CourtListener
courtlistener_api_calls_total{endpoint="/search/", status_code="200"} 850
courtlistener_api_calls_total{endpoint="/search/", status_code="429"} 5

# Histogram: CourtListener API latency
courtlistener_api_duration_seconds_bucket{endpoint="/search/", le="0.5"} 100
courtlistener_api_duration_seconds_bucket{endpoint="/search/", le="2.0"} 840
courtlistener_api_duration_seconds_sum{endpoint="/search/"} 1250.5
courtlistener_api_duration_seconds_count{endpoint="/search/"} 850

# Counter: API errors
courtlistener_api_errors_total{endpoint="/search/", error_code="429"} 5
courtlistener_api_errors_total{endpoint="/search/", error_code="500"} 2
```

#### Cache Metrics

```
# Counter: Cache hits and misses
cache_hits_total{cache_type="metadata"} 5000
cache_misses_total{cache_type="metadata"} 1000
cache_hits_total{cache_type="text"} 800
cache_misses_total{cache_type="text"} 200

# Gauge: Cache size
cache_size_bytes{cache_type="metadata"} 104857600  # 100MB
cache_size_bytes{cache_type="text"} 524288000     # 500MB
```

#### Circuit Breaker Metrics

```
# Counter: Circuit breaker open events
circuit_breaker_open_total{service="courtlistener"} 3

# Gauge: Current circuit breaker state (0=closed, 1=open)
circuit_breaker_state{service="courtlistener"} 0
```

### Querying Metrics

Common Prometheus queries:

```promql
# Error rate (percentage)
rate(mcp_tool_calls_total{status="error"}[5m]) / rate(mcp_tool_calls_total[5m])

# P99 latency
histogram_quantile(0.99, rate(mcp_tool_duration_seconds_bucket[5m]))

# Cache hit ratio
cache_hits_total / (cache_hits_total + cache_misses_total)

# Requests per second
rate(api_requests_total[1m])

# API availability
rate(courtlistener_api_calls_total{status_code="200"}[5m]) / rate(courtlistener_api_calls_total[5m])

# Circuit breaker open status
circuit_breaker_state{service="courtlistener"}
```

### Installing Prometheus

```bash
# Docker Compose setup
cat > monitoring-docker-compose.yml <<EOF
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin

volumes:
  prometheus_data:
  grafana_data:
EOF

docker-compose -f monitoring-docker-compose.yml up
```

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'production'

scrape_configs:
  - job_name: 'legal-research-mcp'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 10s
    scrape_timeout: 5s

  - job_name: 'kubernetes-pods'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - legal-research
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
```

---

## Log Aggregation

### JSON Structured Logs

All logs are JSON for easy parsing:

```json
{
  "timestamp": "2025-12-12T10:30:45.123456Z",
  "level": "INFO",
  "logger": "app.tools.treatment",
  "message": "Tool call completed",
  "correlation_id": "a1b2c3d4-e5f6-...",
  "tool_name": "check_case_validity",
  "elapsed_ms": 1250.5,
  "event": "tool_end"
}
```

### ELK Stack Setup

```bash
# Docker Compose for ELK
cat > elk-docker-compose.yml <<EOF
version: '3.8'
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.0.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
    ports:
      - "9200:9200"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data

  kibana:
    image: docker.elastic.co/kibana/kibana:8.0.0
    ports:
      - "5601:5601"
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200

  logstash:
    image: docker.elastic.co/logstash/logstash:8.0.0
    volumes:
      - ./logstash.conf:/usr/share/logstash/pipeline/logstash.conf
    ports:
      - "5000:5000"

volumes:
  elasticsearch_data:
EOF
```

### Logstash Configuration

```conf
# logstash.conf
input {
  tcp {
    port => 5000
    codec => json
  }
}

filter {
  # Parse timestamp
  date {
    match => ["timestamp", "ISO8601"]
    target => "@timestamp"
  }

  # Extract fields
  mutate {
    add_field => {
      "[@metadata][index_name]" => "legal-research-%{+YYYY.MM.dd}"
    }
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "%{[@metadata][index_name]}"
  }
}
```

### Splunk Integration

```python
# For Splunk HEC (HTTP Event Collector)
import json
import requests

class SplunkHandler(logging.Handler):
    def __init__(self, hec_url, hec_token):
        super().__init__()
        self.hec_url = hec_url
        self.hec_token = hec_token

    def emit(self, record):
        try:
            log_entry = self.format(record)
            payload = {"event": json.loads(log_entry)}
            headers = {"Authorization": f"Splunk {self.hec_token}"}
            requests.post(self.hec_url, json=payload, headers=headers)
        except:
            self.handleError(record)

# Usage
splunk_handler = SplunkHandler(
    hec_url="https://splunk.example.com:8088/services/collector",
    hec_token="your-token"
)
logging.getLogger().addHandler(splunk_handler)
```

---

## Grafana Dashboards

### Creating Dashboards

**Dashboard 1: Application Health**

Panels:
- Requests per second (graph)
- Error rate (%) (gauge)
- P99 latency (gauge)
- Cache hit ratio (%) (gauge)

**Dashboard 2: Tool Performance**

Panels by tool (one row per tool):
- Call count (counter)
- Error rate (%)
- P50/P95/P99 latency
- Most recent errors

**Dashboard 3: CourtListener API**

Panels:
- API success rate (%)
- API response time (p99)
- Rate limit remaining
- Circuit breaker status
- Error rate by endpoint

**Dashboard 4: System Health**

Panels:
- Pod count (if K8s)
- CPU/memory usage
- Disk usage
- Network I/O
- Circuit breaker state

### JSON Dashboard Example

```json
{
  "dashboard": {
    "title": "Legal Research MCP - Application Health",
    "panels": [
      {
        "title": "Requests per Second",
        "targets": [
          {
            "expr": "rate(api_requests_total[1m])"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Error Rate (%)",
        "targets": [
          {
            "expr": "rate(api_request_errors_total[5m]) / rate(api_requests_total[5m]) * 100"
          }
        ],
        "type": "gauge",
        "fieldConfig": {
          "defaults": {
            "max": 100,
            "min": 0,
            "unit": "percent"
          }
        }
      }
    ]
  }
}
```

---

## Alerting Rules

### Alert Examples

```yaml
# prometheus-alerts.yml
groups:
  - name: legal-research-mcp
    interval: 30s
    rules:

      # High error rate
      - alert: HighErrorRate
        expr: |
          rate(mcp_tool_calls_total{status="error"}[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
          component: application
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }}"

      # High latency
      - alert: HighLatency
        expr: |
          histogram_quantile(0.99, rate(mcp_tool_duration_seconds_bucket[5m])) > 5
        for: 10m
        labels:
          severity: warning
          component: performance
        annotations:
          summary: "High p99 latency"
          description: "P99 latency: {{ $value | humanizeDuration }}"

      # Circuit breaker open
      - alert: CircuitBreakerOpen
        expr: |
          circuit_breaker_state{service="courtlistener"} == 1
        for: 1m
        labels:
          severity: critical
          component: dependencies
        annotations:
          summary: "Circuit breaker is open"
          description: "CourtListener API circuit breaker is open"

      # Low cache hit rate
      - alert: LowCacheHitRate
        expr: |
          cache_hits_total / (cache_hits_total + cache_misses_total) < 0.7
        for: 15m
        labels:
          severity: info
          component: performance
        annotations:
          summary: "Low cache hit rate"
          description: "Cache hit rate: {{ $value | humanizePercentage }}"
```

### Sending Alerts

```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m

route:
  receiver: 'default'
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 4h
  routes:
    - match:
        severity: critical
      receiver: pagerduty
      continue: true
    - match:
        severity: warning
      receiver: slack

receivers:
  - name: 'default'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: 'YOUR-PAGERDUTY-KEY'

  - name: 'slack'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK'
        channel: '#alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
```

---

## SLO/SLI Definitions

### Service Level Objectives

```yaml
# slo.yaml
service: "legal-research-mcp"
description: "Legal Research Assistant API"

objectives:
  - name: "availability"
    description: "Percentage of successful requests"
    target: 99.5  # 99.5% uptime = 3.6 hours downtime/month
    sli_query: |
      rate(api_requests_total{status_code=~"2.."}[30d]) /
      rate(api_requests_total[30d])

  - name: "latency"
    description: "P99 request latency"
    target: 2.0  # seconds
    sli_query: |
      histogram_quantile(0.99, rate(mcp_tool_duration_seconds_bucket[30d]))

  - name: "error_rate"
    description: "Percentage of requests without errors"
    target: 99.0  # 99% success
    sli_query: |
      (rate(api_requests_total{status_code=~"2.."}[30d]) /
       rate(api_requests_total[30d])) * 100

  - name: "api_availability"
    description: "CourtListener API success rate"
    target: 99.0  # 99%
    sli_query: |
      rate(courtlistener_api_calls_total{status_code="200"}[30d]) /
      rate(courtlistener_api_calls_total[30d]) * 100
```

### Error Budget

```
Monthly error budget calculation:

Target: 99.5% availability
Error budget: 100% - 99.5% = 0.5%

Days in month: 30
Hours in month: 30 × 24 = 720 hours
Minutes in month: 720 × 60 = 43,200 minutes

Error budget time:
- 0.5% × 43,200 minutes = 216 minutes = 3.6 hours/month

When error budget is consumed:
- 0-25%: Green (no action needed)
- 25-75%: Yellow (monitor closely)
- 75-100%: Red (stop new deployments)
- >100%: SLO breached
```

---

## Production Setup

### Kubernetes Monitoring Stack

```yaml
# monitoring-deployment.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: monitoring

---
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: monitoring
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
    scrape_configs:
      - job_name: legal-research-mcp
        kubernetes_sd_configs:
          - role: pod
            namespaces:
              names:
                - legal-research
        relabel_configs:
          - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
            action: keep
            regex: true

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
  namespace: monitoring
spec:
  replicas: 1
  selector:
    matchLabels:
      app: prometheus
  template:
    metadata:
      labels:
        app: prometheus
    spec:
      containers:
      - name: prometheus
        image: prom/prometheus:latest
        ports:
        - containerPort: 9090
        volumeMounts:
        - name: config
          mountPath: /etc/prometheus
        - name: data
          mountPath: /prometheus
      volumes:
      - name: config
        configMap:
          name: prometheus-config
      - name: data
        emptyDir: {}

---
apiVersion: v1
kind: Service
metadata:
  name: prometheus
  namespace: monitoring
spec:
  ports:
  - port: 9090
    targetPort: 9090
  selector:
    app: prometheus
```

---

## Checklist

Before going to production:

- [ ] Prometheus scraping metrics from /metrics endpoint
- [ ] Logs being sent to ELK/Splunk/CloudWatch
- [ ] Grafana dashboards created and tested
- [ ] Alert rules configured and tested
- [ ] SLO/SLI definitions documented
- [ ] On-call escalation configured
- [ ] Dashboard accessible to team
- [ ] Metrics retention set appropriately
- [ ] Cost of monitoring estimated
- [ ] Performance impact of metrics collection measured

---

**See [OPERATIONS.md](./OPERATIONS.md) for operational procedures using these metrics.**
