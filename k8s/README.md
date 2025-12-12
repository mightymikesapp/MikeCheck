# Kubernetes Deployment for Legal Research Assistant MCP

This directory contains Kubernetes manifests for deploying the Legal Research Assistant MCP to production environments.

## Quick Start

### Prerequisites

- Kubernetes cluster (1.20+)
- `kubectl` configured to access your cluster
- Docker image pushed to a registry (e.g., ghcr.io, Docker Hub, ECR)
- CourtListener API key

### Step 1: Create the Namespace and ConfigMap

```bash
# Create namespace
kubectl apply -f namespace.yaml

# Create configuration
kubectl apply -f configmap.yaml

# Create RBAC resources
kubectl apply -f rbac.yaml
```

### Step 2: Create the Secret (API Key)

Choose one of the following approaches:

#### Option A: Create Secret via kubectl (Simple)

```bash
# Create the secret
kubectl create secret generic legal-research-secrets \
  --from-literal=COURTLISTENER_API_KEY=$YOUR_API_KEY \
  -n legal-research

# Verify
kubectl get secret legal-research-secrets -n legal-research
```

#### Option B: Use Sealed Secrets (Recommended for GitOps)

Install Sealed Secrets:
```bash
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.18.0/controller.yaml
```

Create sealed secret:
```bash
echo -n $YOUR_API_KEY | kubectl create secret generic legal-research-secrets \
  --dry-run=client --from-file=COURTLISTENER_API_KEY=/dev/stdin -o yaml | \
  kubeseal -o yaml > k8s/secret-sealed.yaml

# Apply sealed secret
kubectl apply -f k8s/secret-sealed.yaml
```

#### Option C: Use External Secrets Operator

Follow the [External Secrets Operator documentation](https://external-secrets.io/) to configure secrets from AWS Secrets Manager, HashiCorp Vault, etc.

### Step 3: Deploy the Application

```bash
# Apply deployment
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f hpa.yaml

# Verify deployment
kubectl get pods -n legal-research
kubectl get svc -n legal-research
```

### Step 4 (Optional): Enable Prometheus Monitoring

If you have Prometheus Operator installed:

```bash
kubectl apply -f servicemonitor.yaml
```

## Using Kustomize (Recommended)

For easier management and environment-specific overrides:

```bash
# Deploy all resources
kubectl apply -k .

# Check what will be deployed
kubectl kustomize .

# Dry-run to see changes
kubectl apply -k . --dry-run=client
```

## Deployment Verification

```bash
# Check pod status
kubectl get pods -n legal-research -w

# Check logs
kubectl logs -n legal-research deployment/legal-research-mcp --tail=100 -f

# Check events
kubectl describe pod -n legal-research -l app.kubernetes.io/name=legal-research-mcp

# Test the service (port-forward)
kubectl port-forward -n legal-research svc/legal-research-api 8000:80
curl http://localhost:8000/health
```

## Configuration Management

### Updating Environment Variables

Update `configmap.yaml` and apply:

```bash
kubectl apply -f configmap.yaml

# Rolling restart to pick up changes
kubectl rollout restart deployment/legal-research-mcp -n legal-research
```

### Updating the Docker Image

```bash
# Option 1: Update kustomization.yaml and apply
# Edit k8s/kustomization.yaml, change newTag
kubectl apply -k .

# Option 2: Direct patch
kubectl set image deployment/legal-research-mcp \
  api=ghcr.io/mightymikesapp/legal-research-mcp:v0.2.0 \
  -n legal-research
```

## Scaling

### Manual Scaling

```bash
kubectl scale deployment legal-research-mcp --replicas=5 -n legal-research
```

### Automatic Scaling

The HPA (Horizontal Pod Autoscaler) automatically scales based on:
- CPU: 70% average utilization
- Memory: 80% average utilization
- Min replicas: 3
- Max replicas: 10

Check HPA status:
```bash
kubectl get hpa -n legal-research -w
kubectl describe hpa legal-research-mcp-hpa -n legal-research
```

## Monitoring & Logging

### View Logs

```bash
# Recent logs
kubectl logs -n legal-research deployment/legal-research-mcp

# Follow logs
kubectl logs -n legal-research deployment/legal-research-mcp -f

# Logs from specific pod
kubectl logs -n legal-research legal-research-mcp-xxxx
```

### Health Check

```bash
# Direct health check
kubectl exec -n legal-research legal-research-mcp-xxxx -- curl http://localhost:8000/health

# Port-forward and test
kubectl port-forward -n legal-research svc/legal-research-api 8000:80
curl http://localhost:8000/health
```

### Prometheus Metrics (if monitoring enabled)

Access metrics at: `http://service-ip:8000/metrics`

Default alerts are configured in `servicemonitor.yaml`:
- Pod not ready
- High error rate (> 5%)
- High latency (p99 > 5s)
- API authentication errors
- Low cache hit rate (< 70%)

## Rolling Updates

The deployment uses a rolling update strategy to ensure zero downtime:

```bash
# Check current strategy
kubectl get deployment legal-research-mcp -n legal-research -o jsonpath='{.spec.strategy}'

# Monitor rollout
kubectl rollout status deployment/legal-research-mcp -n legal-research -w

# Rollback if needed
kubectl rollout undo deployment/legal-research-mcp -n legal-research
```

## Troubleshooting

### Pod Won't Start

```bash
# Check pod events
kubectl describe pod -n legal-research <pod-name>

# Check logs
kubectl logs -n legal-research <pod-name>

# Common issues:
# 1. API key not set: Check secret exists
#    kubectl get secret legal-research-secrets -n legal-research -o yaml
#
# 2. Image not found: Verify registry access
#    kubectl describe pod -n legal-research <pod-name> | grep -A5 "Events"
#
# 3. Insufficient resources: Check node capacity
#    kubectl top nodes
#    kubectl top pods -n legal-research
```

### Service Not Accessible

```bash
# Check service endpoints
kubectl get endpoints -n legal-research legal-research-api

# Port-forward to test
kubectl port-forward -n legal-research svc/legal-research-api 8000:80
curl http://localhost:8000/health

# Check network policies
kubectl get networkpolicies -n legal-research
```

### High Memory Usage

```bash
# Check current usage
kubectl top pods -n legal-research

# Check container limits
kubectl get deployment legal-research-mcp -n legal-research -o jsonpath='{.spec.template.spec.containers[0].resources}'

# Increase limits if needed
kubectl set resources deployment legal-research-mcp \
  --limits=memory=4Gi,cpu=2000m \
  -n legal-research
```

## Environment-Specific Deployments

For dev/staging/prod variants, create overlays:

```
k8s/
├── kustomization.yaml          # Base configuration
├── configmap.yaml
├── deployment.yaml
├── service.yaml
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml  # Override: 1 replica, debug logging
    │   └── patch.yaml
    ├── staging/
    │   ├── kustomization.yaml  # Override: 2 replicas, info logging
    │   └── patch.yaml
    └── prod/
        ├── kustomization.yaml  # Override: 3+ replicas, warn logging
        └── patch.yaml
```

Deploy specific environment:
```bash
kubectl apply -k k8s/overlays/prod
```

## Backup & Restore

### Backup Configuration

```bash
# Backup all resources
kubectl get all -n legal-research -o yaml > backup.yaml

# Backup specific resources
kubectl get configmap,secret -n legal-research -o yaml > config-backup.yaml
```

### Restore

```bash
kubectl apply -f backup.yaml
```

## Security Considerations

1. **Never commit secrets to git** - Use Sealed Secrets or External Secrets
2. **Use RBAC** - ServiceAccount has minimal permissions (metrics reader only)
3. **Network policies** - Pod-to-pod and ingress rules defined
4. **Security context** - Non-root user (1000), read-only filesystem, no privilege escalation
5. **Resource limits** - Prevent resource exhaustion
6. **Health checks** - Automatic pod replacement on failure

## Advanced Configuration

### Custom Domains

Add Ingress resource:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: legal-research-ingress
  namespace: legal-research
spec:
  rules:
  - host: legal-research.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: legal-research-api
            port:
              number: 80
```

### TLS/SSL

Use cert-manager:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: legal-research-cert
  namespace: legal-research
spec:
  secretName: legal-research-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
  - legal-research.example.com
```

## Support & Issues

For issues with the deployment manifests, please refer to:
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Main Project README](../README.md)
- [CLAUDE.md Development Guide](../CLAUDE.md)

For application-specific issues, check the main project documentation.
