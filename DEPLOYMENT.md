# Deployment Guide - Legal Research Assistant MCP

This guide provides step-by-step instructions for deploying the Legal Research Assistant MCP to various environments.

**Last Updated:** 2025-12-12
**Supported Platforms:** Docker, Kubernetes, AWS ECS (planned), Google Cloud Run (planned)

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development](#local-development)
3. [Docker Deployment](#docker-deployment)
4. [Kubernetes Deployment](#kubernetes-deployment)
5. [Environment Configuration](#environment-configuration)
6. [Secrets Management](#secrets-management)
7. [Verification & Testing](#verification--testing)
8. [Rollback Procedures](#rollback-procedures)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required

- **Docker** 20.10+ (for container-based deployments)
  - Install: https://docs.docker.com/get-docker/

- **Git** (to clone the repository)
  - Install: https://git-scm.com/downloads

- **CourtListener API Key** (free, required for API access)
  - Get your key: https://www.courtlistener.com/api/rest/v4/
  - Sign up: https://www.courtlistener.com/signup/?next=/profile/api/

### Optional

- **kubectl** (for Kubernetes deployments)
  - Install: https://kubernetes.io/docs/tasks/tools/

- **Docker Compose** (already included with Docker Desktop)
  - Standalone install: https://docs.docker.com/compose/install/

- **Helm** (for Helm chart deployments)
  - Install: https://helm.sh/docs/intro/install/

---

## Local Development

### Quick Start (5 minutes)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/mightymikesapp/MikeCheck.git
   cd MikeCheck
   ```

2. **Set up environment:**
   ```bash
   cp .env.example .env
   # Edit .env and set COURTLISTENER_API_KEY=your_key_here
   nano .env
   ```

3. **Start with Docker Compose:**
   ```bash
   docker-compose up
   ```

4. **Verify it's working:**
   ```bash
   # In another terminal
   curl http://localhost:8000/health
   ```

### Development with Code Changes

For iterative development, mount source code:

```bash
# Edit docker-compose.yml, uncomment the volumes line:
# - ./app:/app/app

docker-compose up --build
```

Any changes to Python files will be reflected immediately (if using auto-reload).

### Debugging

```bash
# View real-time logs
docker-compose logs -f legal-research-mcp

# Execute commands in running container
docker-compose exec legal-research-mcp python -c "..."

# Get a shell
docker-compose exec legal-research-mcp /bin/bash

# Check resource usage
docker stats legal-research-mcp
```

---

## Docker Deployment

### Build Docker Image

```bash
# Build for current platform
docker build -t legal-research-mcp:latest .

# Build for multiple platforms (requires buildx)
docker buildx build --platform linux/amd64,linux/arm64 \
  -t legal-research-mcp:latest .
```

### Push to Registry

#### Docker Hub

```bash
# Login
docker login

# Tag image
docker tag legal-research-mcp:latest yourusername/legal-research-mcp:latest

# Push
docker push yourusername/legal-research-mcp:latest
```

#### GitHub Container Registry (GHCR)

```bash
# Login (requires GitHub CLI or personal access token)
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Tag image
docker tag legal-research-mcp:latest ghcr.io/mightymikesapp/legal-research-mcp:latest

# Push
docker push ghcr.io/mightymikesapp/legal-research-mcp:latest
```

#### AWS Elastic Container Registry (ECR)

```bash
# Get login token
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com

# Tag image
docker tag legal-research-mcp:latest \
  123456789.dkr.ecr.us-east-1.amazonaws.com/legal-research-mcp:latest

# Push
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/legal-research-mcp:latest

# Create repository if not exists
aws ecr create-repository --repository-name legal-research-mcp --region us-east-1
```

### Run Docker Container

```bash
# Basic (development)
docker run -p 8000:8000 \
  -e COURTLISTENER_API_KEY=$YOUR_KEY \
  legal-research-mcp:latest

# Production with health checks
docker run -d \
  --name legal-research-mcp \
  --restart unless-stopped \
  -p 8000:8000 \
  -e COURTLISTENER_API_KEY=$YOUR_KEY \
  -e MODE=standard \
  -e LOG_LEVEL=INFO \
  -v legal-research-cache:/app/.cache \
  -v legal-research-networks:/app/citation_networks \
  --health-cmd='curl -f http://localhost:8000/health' \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  legal-research-mcp:latest

# Check container status
docker ps
docker logs legal-research-mcp
docker stats legal-research-mcp

# Stop container
docker stop legal-research-mcp
docker rm legal-research-mcp

# View health status
docker inspect --format='{{json .State.Health}}' legal-research-mcp | jq
```

### Volume Management

```bash
# Create named volumes for persistence
docker volume create legal-research-cache
docker volume create legal-research-networks

# Inspect volume
docker volume inspect legal-research-cache

# Clean up unused volumes
docker volume prune
```

---

## Kubernetes Deployment

### Prerequisites

- Kubernetes cluster 1.20+ (EKS, GKE, AKS, minikube, etc.)
- `kubectl` configured with cluster access
- Docker image pushed to a registry accessible from the cluster

### Step 1: Prepare Kubernetes Configuration

```bash
# Create a working directory
mkdir -p k8s-deployment
cd k8s-deployment

# Copy manifests from repository
cp -r ../MikeCheck/k8s .
```

### Step 2: Create Namespace and ConfigMap

```bash
# Create namespace
kubectl apply -f k8s/namespace.yaml

# Verify namespace created
kubectl get namespace legal-research

# Create configuration
kubectl apply -f k8s/configmap.yaml

# Verify ConfigMap
kubectl get configmap -n legal-research
```

### Step 3: Set Up Secrets

Choose one approach based on your security requirements:

#### Option A: Simple kubectl Secrets (Development Only)

⚠️ **Not recommended for production** - secrets stored in etcd unencrypted

```bash
# Create secret
kubectl create secret generic legal-research-secrets \
  --from-literal=COURTLISTENER_API_KEY=$YOUR_API_KEY \
  -n legal-research

# Verify (WARNING: shows value in plain text!)
kubectl get secret legal-research-secrets -n legal-research -o yaml
```

#### Option B: Sealed Secrets (GitOps-Friendly, Recommended)

```bash
# Install Sealed Secrets controller (one-time setup)
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.18.0/controller.yaml

# Wait for controller to be ready
kubectl rollout status -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.18.0/controller.yaml -n kube-system

# Create sealed secret
echo -n $YOUR_API_KEY | kubectl create secret generic legal-research-secrets \
  --dry-run=client \
  --from-file=COURTLISTENER_API_KEY=/dev/stdin \
  -o yaml -n legal-research | \
  kubeseal -o yaml > k8s/secret-sealed.yaml

# Apply sealed secret (safe to commit to git!)
kubectl apply -f k8s/secret-sealed.yaml

# Verify
kubectl get sealedsecrets -n legal-research
```

#### Option C: External Secrets Operator (AWS/Vault)

```bash
# Install External Secrets Operator
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets-system --create-namespace

# Create SecretStore (points to AWS Secrets Manager)
cat <<EOF | kubectl apply -f -
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: legal-research-secrets
  namespace: legal-research
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        jwt:
          serviceAccountRef:
            name: legal-research
EOF

# Create ExternalSecret (pulls from AWS)
cat <<EOF | kubectl apply -f -
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: legal-research-secrets
  namespace: legal-research
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: legal-research-secrets
    kind: SecretStore
  target:
    name: legal-research-secrets
    creationPolicy: Owner
  data:
  - secretKey: COURTLISTENER_API_KEY
    remoteRef:
      key: legal-research/courtlistener-api-key
EOF
```

### Step 4: Deploy Application

```bash
# Create RBAC resources
kubectl apply -f k8s/rbac.yaml

# Deploy application
kubectl apply -f k8s/deployment.yaml

# Create service
kubectl apply -f k8s/service.yaml

# Enable auto-scaling
kubectl apply -f k8s/hpa.yaml

# Verify deployment
kubectl get deployment -n legal-research
kubectl get pods -n legal-research
kubectl get svc -n legal-research
```

### Step 5: Verify Deployment

```bash
# Wait for rollout to complete
kubectl rollout status deployment/legal-research-mcp -n legal-research

# Check pod status
kubectl get pods -n legal-research -o wide

# View recent logs
kubectl logs -n legal-research deployment/legal-research-mcp --tail=50

# Test health endpoint (port-forward)
kubectl port-forward -n legal-research svc/legal-research-api 8000:80

# In another terminal
curl http://localhost:8000/health
```

### Using Kustomize (Simplified)

```bash
# Deploy all resources at once
kubectl apply -k k8s/

# Dry-run to preview changes
kubectl apply -k k8s/ --dry-run=client -o yaml

# View what will be deployed
kubectl kustomize k8s/
```

---

## Environment Configuration

### Configuration Profiles

Three preset configurations are available for different use cases:

#### Light Mode (Development/Testing)
```bash
MODE=light
# Max 25 citing cases, 3 full-text fetches
# Timeout: 15s connect, 30s read
# Cache: 1h metadata, 1d text
```

Usage:
```bash
docker run -e MODE=light legal-research-mcp:latest
# OR
kubectl set env deployment/legal-research-mcp MODE=light -n legal-research
```

#### Standard Mode (Production Default)
```bash
MODE=standard
# Max 100 citing cases, 10 full-text fetches
# Timeout: 10s connect, 60s read
# Cache: 24h metadata, 7d text
```

#### Heavy Mode (Deep Analysis)
```bash
MODE=heavy
# Max 200 citing cases, 25 full-text fetches
# Timeout: 15s connect, 120s read
# Cache: 2d metadata, 14d text
```

### Custom Configuration

For specific requirements, override individual variables:

```bash
# Docker
docker run -e MODE=standard -e MAX_CITING_CASES=150 -e LOG_LEVEL=DEBUG \
  legal-research-mcp:latest

# Kubernetes
kubectl set env deployment/legal-research-mcp \
  MODE=standard \
  MAX_CITING_CASES=150 \
  LOG_LEVEL=DEBUG \
  -n legal-research
```

See `.env.example` for all available configuration options.

---

## Secrets Management

### Best Practices

1. **Never commit secrets to git** - Use `.gitignore` or secret managers
2. **Use environment variables** - Loaded from secrets, not config files
3. **Rotate regularly** - Change API keys every 90 days minimum
4. **Audit access** - Monitor who accessed the API key
5. **Use least privilege** - CourtListener API key should have minimal permissions

### Updating Secrets

#### Docker

```bash
docker run -e COURTLISTENER_API_KEY=$NEW_KEY \
  legal-research-mcp:latest
```

#### Kubernetes

```bash
# Delete old secret
kubectl delete secret legal-research-secrets -n legal-research

# Create new secret
kubectl create secret generic legal-research-secrets \
  --from-literal=COURTLISTENER_API_KEY=$NEW_KEY \
  -n legal-research

# Rolling restart to pick up new secret
kubectl rollout restart deployment/legal-research-mcp -n legal-research

# Monitor rollout
kubectl rollout status deployment/legal-research-mcp -n legal-research
```

### Secret Rotation Procedure

1. Generate new CourtListener API key
2. Deploy new secret to system
3. Monitor error rates for 5 minutes (should remain normal)
4. Delete old API key from CourtListener dashboard
5. Document rotation in audit log

---

## Verification & Testing

### Health Check

```bash
# HTTP health check endpoint
curl -i http://localhost:8000/health

# Expected response (200 OK):
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2025-12-12T10:30:45.123456Z"
}
```

### API Endpoint Tests

```bash
# Test case lookup
curl -X POST http://localhost:8000/verify-quote \
  -H "Content-Type: application/json" \
  -d '{
    "quote": "the right to privacy",
    "citation": "410 U.S. 113"
  }'

# Test citation network
curl -X POST http://localhost:8000/build-citation-network \
  -H "Content-Type: application/json" \
  -d '{
    "citation": "410 U.S. 113",
    "depth": 2
  }'
```

### Performance Benchmarks

Baseline performance (standard mode, single pod):
- Health check: <50ms
- Case lookup: 500-2000ms (depends on API response time)
- Citation network: 2-5 seconds (3-depth, 50-100 nodes)
- Quote verification: 1-3 seconds per quote

### Load Testing

```bash
# Simple load test (requires Apache Bench)
ab -n 100 -c 10 http://localhost:8000/health

# More realistic test with hey
go install github.com/rakyll/hey@latest
hey -n 1000 -c 50 http://localhost:8000/health
```

---

## Rollback Procedures

### Docker Rolling Back

```bash
# If using Docker Compose
docker-compose down
docker image rm legal-research-mcp:latest
docker pull yourusername/legal-research-mcp:previous-tag
docker tag yourusername/legal-research-mcp:previous-tag legal-research-mcp:latest
docker-compose up -d

# If using Docker daemon directly
docker stop legal-research-mcp
docker rm legal-research-mcp
docker run -d --name legal-research-mcp \
  -p 8000:8000 \
  -e COURTLISTENER_API_KEY=$KEY \
  yourusername/legal-research-mcp:previous-tag
```

### Kubernetes Rolling Back

```bash
# View rollout history
kubectl rollout history deployment/legal-research-mcp -n legal-research

# Rollback to previous version
kubectl rollout undo deployment/legal-research-mcp -n legal-research

# Rollback to specific revision
kubectl rollout undo deployment/legal-research-mcp --to-revision=2 -n legal-research

# Monitor rollback progress
kubectl rollout status deployment/legal-research-mcp -n legal-research -w

# View the change that was rolled back
kubectl describe deployment legal-research-mcp -n legal-research | grep -A 20 "Conditions"
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs legal-research-mcp

# Common issues:
# 1. Missing environment variable
#    Error: "COURTLISTENER_API_KEY not set"
#    Solution: docker run -e COURTLISTENER_API_KEY=$KEY ...

# 2. Port already in use
#    Error: "bind: address already in use"
#    Solution: docker run -p 8001:8000 ...  (use different port)

# 3. Insufficient memory
#    Error: "Killed" or "OOMKilled"
#    Solution: docker run -m 2g ...  (increase memory limit)
```

### Pod Won't Start (Kubernetes)

```bash
# Check pod events
kubectl describe pod -n legal-research <pod-name>

# View logs
kubectl logs -n legal-research <pod-name>
kubectl logs -n legal-research <pod-name> --previous  # if crashed

# Common issues:
# 1. ImagePullBackOff
#    Cause: Image not found in registry
#    Solution: Verify image name, push to registry, update image in deployment

# 2. CrashLoopBackOff
#    Cause: Application crashes on startup
#    Solution: Check logs, verify environment variables

# 3. Pending
#    Cause: No available nodes or insufficient resources
#    Solution: Check node capacity (kubectl top nodes), increase cluster size
```

### Health Check Failing

```bash
# Check health endpoint directly
curl -v http://localhost:8000/health

# If 500 error, check application logs
docker logs legal-research-mcp

# Common causes:
# - API key invalid: Update COURTLISTENER_API_KEY
# - API rate limited: Wait 15 minutes for rate limit to reset
# - Network connectivity: Check firewall, DNS
# - Disk space: Check available disk space (df -h)
```

### High Memory Usage

```bash
# Check current usage
docker stats legal-research-mcp

# View Python memory usage
docker exec legal-research-mcp python -c "import psutil; print(psutil.Process().memory_info())"

# Kubernetes
kubectl top pods -n legal-research

# If consistently high:
# 1. Check cache directory size
docker exec legal-research-mcp du -sh /app/.cache

# 2. Clear cache
docker exec legal-research-mcp rm -rf /app/.cache/*

# 3. Increase container limits
docker run -m 4g ...  (Docker)
kubectl set resources deployment/legal-research-mcp --limits=memory=4Gi -n legal-research  (K8s)
```

### API Rate Limiting

```bash
# Check error logs for 429 (Too Many Requests)
docker logs legal-research-mcp | grep 429

# Check current rate limit status
curl -i https://www.courtlistener.com/api/rest/v4/opinions/ \
  -H "Authorization: Token $COURTLISTENER_API_KEY"

# Look for X-RateLimit-* headers in response

# Solutions:
# 1. Reduce concurrent requests (scale down replicas)
# 2. Increase cache TTL to reduce API calls
# 3. Switch to heavy mode with higher cache TTL
# 4. Contact CourtListener for higher rate limit
```

---

## Production Checklist

Before deploying to production:

- [ ] API key tested and working
- [ ] Environment configuration validated
- [ ] Docker image built and pushed to registry
- [ ] Kubernetes manifests reviewed and customized
- [ ] Secrets manager set up (Sealed Secrets, External Secrets, etc.)
- [ ] Health checks configured
- [ ] Monitoring and alerting enabled (Prometheus, etc.)
- [ ] Backup and recovery plan documented
- [ ] Runbooks reviewed and accessible
- [ ] Team trained on deployment and operations
- [ ] Load testing completed
- [ ] Security audit passed
- [ ] Disaster recovery tested

---

## Support

For issues or questions:

1. Check [OPERATIONS.md](./OPERATIONS.md) for common issues
2. Review [CLAUDE.md](./CLAUDE.md) for architecture details
3. Check [k8s/README.md](./k8s/README.md) for Kubernetes-specific help
4. Review application logs for error details
5. Check CourtListener API status: https://www.courtlistener.com/help/api/

---

**See [OPERATIONS.md](./OPERATIONS.md) for operational guidance, monitoring, and troubleshooting.**
