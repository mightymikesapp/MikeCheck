# Secrets Management Guide

This document explains how to securely manage API keys and other secrets in the Legal Research Assistant MCP.

**Last Updated:** 2025-12-12
**Scope:** CourtListener API keys, service credentials, encryption keys

---

## Table of Contents

1. [Security Principles](#security-principles)
2. [Secret Types](#secret-types)
3. [Storage & Management Strategies](#storage--management-strategies)
4. [Rotation Procedures](#rotation-procedures)
5. [Access Control](#access-control)
6. [Compliance & Auditing](#compliance--auditing)
7. [Emergency Procedures](#emergency-procedures)

---

## Security Principles

### Core Rules

1. **Never commit secrets to version control**
   - Use `.gitignore` to exclude secret files
   - Use secret managers, not config files
   - Rotate any accidentally exposed secrets immediately

2. **Least privilege access**
   - Services/users only have access to secrets they need
   - Restrict who can read, rotate, delete secrets
   - Audit all secret access

3. **Encryption at rest & in transit**
   - Secrets encrypted in storage
   - TLS for all network communication
   - Use HTTPS only, never HTTP

4. **Regular rotation**
   - Rotate keys at least every 90 days
   - Rotate immediately if compromised
   - Automate rotation where possible

5. **Audit everything**
   - Log all access to secrets
   - Log all rotations
   - Alert on unusual access patterns
   - Keep audit trail for compliance

---

## Secret Types

### Primary Secret: CourtListener API Key

**Type:** API key
**Length:** ~40 characters (hex string)
**Sensitivity:** HIGH - grants access to legal case data
**Source:** https://www.courtlistener.com/profile/api/
**Usage:** Authentication to CourtListener API endpoints

**Exposure Impact:**
- Attacker can make unlimited API requests on your quota
- Can access any public legal case data (not sensitive by default)
- May deplete rate limits, causing service outages
- Could incur costs if using paid tier

### Secondary Secrets (Optional)

- **Service-to-service API keys** (for inter-service communication)
- **Encryption keys** (if adding end-to-end encryption)
- **Database passwords** (if using external database for cache)
- **Cloud credentials** (AWS, GCP, Azure access keys)

---

## Storage & Management Strategies

Choose based on your deployment environment:

### Strategy 1: Environment Variables (Simple, Development Only)

**Best for:** Local development, Docker Compose
**Security Level:** Low - Not suitable for production
**Ease of Use:** Very Easy

```bash
# Set in shell (lost when terminal closes)
export COURTLISTENER_API_KEY="your-key-here"
python -m app.server

# Set in .env file (local development only)
# .env file - NEVER commit to git!
COURTLISTENER_API_KEY=your-key-here

# Docker
docker run -e COURTLISTENER_API_KEY=$KEY legal-research-mcp:latest
```

**Risks:**
- Visible in process list: `ps aux | grep python`
- Visible in shell history: `.bash_history`
- Visible in Docker inspect: `docker inspect <container>`
- Not encrypted, stored in plain text

**Mitigations:**
- Only use for local development
- Use `.env` with strict permissions: `chmod 600 .env`
- Clear shell history before logging out
- Never use in production

---

### Strategy 2: Docker Secrets (Good, for Docker Swarm)

**Best for:** Docker Swarm deployments
**Security Level:** Medium - Encrypted in transit and at rest
**Ease of Use:** Medium

```bash
# Create secret (one-time)
echo "your-api-key" | docker secret create cl_api_key -

# Use in service definition
docker service create \
  --secret cl_api_key \
  -e COURTLISTENER_API_KEY_FILE=/run/secrets/cl_api_key \
  legal-research-mcp:latest

# In application, read from file
COURTLISTENER_API_KEY=$(cat /run/secrets/cl_api_key)
```

**Advantages:**
- Encrypted in Docker secret storage
- Secrets only mounted in memory to containers that need them
- Automatic secret rotation support
- Built into Docker

**Disadvantages:**
- Only works with Docker Swarm (not plain Docker, not Kubernetes)
- Requires Docker Swarm mode enabled
- Limited rotation capabilities

---

### Strategy 3: Kubernetes Secrets (Good, for Kubernetes)

**Best for:** Kubernetes deployments
**Security Level:** Medium - Encrypted if etcd encryption enabled
**Ease of Use:** Medium

#### 3a. Encrypted Kubernetes Secrets (Recommended)

```bash
# Create secret
kubectl create secret generic legal-research-secrets \
  --from-literal=COURTLISTENER_API_KEY=your-key \
  -n legal-research

# Use in deployment (automatic - already in k8s/deployment.yaml)
envFrom:
  - secretRef:
      name: legal-research-secrets

# Verify (WARNING: shows value!)
kubectl get secret legal-research-secrets -n legal-research -o jsonpath='{.data.COURTLISTENER_API_KEY}' | base64 -d
```

**Advantages:**
- Built into Kubernetes
- Easy to manage with kubectl
- Can be encrypted in etcd (optional)
- Automatically mounted into pods

**Disadvantages:**
- Secrets stored in etcd (base64 encoded, not encrypted by default)
- Need to enable etcd encryption for actual security
- Requires Kubernetes cluster access

#### 3b. Sealed Secrets (Strongly Recommended)

Uses asymmetric encryption - safe to commit to git!

```bash
# Install Sealed Secrets (one-time)
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.33.1/controller.yaml

# Create sealed secret
echo -n 'your-api-key' | kubectl create secret generic legal-research-secrets \
  --dry-run=client \
  --from-file=COURTLISTENER_API_KEY=/dev/stdin \
  -o yaml -n legal-research | \
  kubeseal -o yaml > k8s/secret-sealed.yaml

# Apply sealed secret (SAFE TO COMMIT - encrypted!)
kubectl apply -f k8s/secret-sealed.yaml

# Sealed Secrets controller automatically decrypts when deploying
```

**Advantages:**
- Secrets are encrypted with private key (only on cluster)
- Safe to commit sealed secrets to git
- GitOps-friendly workflow
- Automatic decryption on cluster
- Works across namespaces (optional)

**Disadvantages:**
- Requires Sealed Secrets operator on cluster
- Need to backup sealing key or can't decrypt secrets on new cluster
- One sealing key per cluster

**Setup Sealed Secrets:**

```bash
# 1. Install controller
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.18.0/controller.yaml

# 2. Verify controller is running
kubectl get pods -n kube-system -l app.kubernetes.io/name=sealed-secrets

# 3. Get sealing key (backup this!)
kubectl get secret -n kube-system \
  -l sealedsecrets.bitnami.com/status=active \
  -o jsonpath='{.items[0].data.tls\.crt}' | base64 -d > sealing-key.crt

# 4. Store sealing key securely (offline backup)
# This key is needed if recreating the cluster

# 5. Create sealed secrets for all your secrets
```

---

### Strategy 4: External Secrets Operator (Best, for Enterprise)

**Best for:** AWS, Google Cloud, HashiCorp Vault, Azure Key Vault
**Security Level:** High - Secrets stored in external secure system
**Ease of Use:** Medium-High

#### 4a. AWS Secrets Manager

```bash
# Install External Secrets Operator
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets-system --create-namespace

# Store secret in AWS
aws secretsmanager create-secret \
  --name legal-research/courtlistener-api-key \
  --secret-string "your-api-key"

# Create SecretStore (how to access AWS)
cat <<EOF | kubectl apply -f -
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: legal-research-aws-secrets
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

# Create ExternalSecret (pulls from AWS periodically)
cat <<EOF | kubectl apply -f -
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: legal-research-secrets
  namespace: legal-research
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: legal-research-aws-secrets
    kind: SecretStore
  target:
    name: legal-research-secrets
    creationPolicy: Owner
  data:
  - secretKey: COURTLISTENER_API_KEY
    remoteRef:
      key: legal-research/courtlistener-api-key
EOF

# External Secrets Operator pulls from AWS and creates K8s secret automatically
```

**Advantages:**
- Secrets stored in AWS Secrets Manager (enterprise-grade)
- No secrets stored in Kubernetes cluster
- Automatic rotation possible
- Audit trail in AWS CloudTrail
- Works with AWS, Google Cloud, Azure, Vault, etc.
- Highly scalable for enterprises

**Disadvantages:**
- Requires External Secrets Operator on cluster
- Additional complexity
- Costs for AWS Secrets Manager ($0.40/secret/month)
- More moving parts to manage

#### 4b. HashiCorp Vault

```bash
# Store secret in Vault
vault kv put secret/legal-research/courtlistener api_key="your-key"

# Create SecretStore (pointing to Vault)
cat <<EOF | kubectl apply -f -
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: legal-research-vault
  namespace: legal-research
spec:
  provider:
    vault:
      server: "https://vault.example.com:8200"
      path: "secret"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "legal-research"
EOF

# Create ExternalSecret
cat <<EOF | kubectl apply -f -
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: legal-research-secrets
  namespace: legal-research
spec:
  secretStoreRef:
    name: legal-research-vault
    kind: SecretStore
  target:
    name: legal-research-secrets
  data:
  - secretKey: COURTLISTENER_API_KEY
    remoteRef:
      key: "secret/legal-research/courtlistener"
      property: "api_key"
EOF
```

---

## Rotation Procedures

### Manual Rotation

**Step 1: Generate new key**
```bash
# Log into CourtListener dashboard
# https://www.courtlistener.com/profile/api/
# Click "Generate new key"
# Copy new key
NEW_KEY="..."
```

**Step 2: Update secret**

```bash
# Environment variable / Docker
export COURTLISTENER_API_KEY=$NEW_KEY
docker run -e COURTLISTENER_API_KEY=$NEW_KEY legal-research-mcp:latest

# Kubernetes Secrets
kubectl create secret generic legal-research-secrets \
  --from-literal=COURTLISTENER_API_KEY=$NEW_KEY \
  --dry-run=client -o yaml | kubectl apply -f -

# Sealed Secrets
echo -n $NEW_KEY | kubectl create secret generic legal-research-secrets \
  --dry-run=client --from-file=COURTLISTENER_API_KEY=/dev/stdin -o yaml | \
  kubeseal -o yaml > k8s/secret-sealed.yaml
kubectl apply -f k8s/secret-sealed.yaml
```

**Step 3: Restart pods (to pick up new secret)**
```bash
kubectl rollout restart deployment/legal-research-mcp -n legal-research
kubectl rollout status deployment/legal-research-mcp -n legal-research -w
```

**Step 4: Monitor (error rate should stay normal)**
```bash
kubectl logs -n legal-research deployment/legal-research-mcp -f | grep -E "401|authentication"
```

**Step 5: Revoke old key**
```bash
# Log into CourtListener dashboard
# Delete the old API key
```

**Step 6: Document rotation**
```
Date: 2025-12-12 14:30 UTC
Action: Rotated COURTLISTENER_API_KEY
Reason: Scheduled 90-day rotation
Old key: Deleted from CourtListener dashboard
New key: Deployed and verified working
Status: ✅ Completed successfully
```

### Automated Rotation (AWS Secrets Manager + Lambda)

```python
# Lambda function for automatic rotation
import boto3
import requests

def lambda_handler(event, context):
    """Rotate CourtListener API key."""
    secretsmanager = boto3.client('secretsmanager')

    # Get secret
    secret = secretsmanager.get_secret_value(
        SecretId='legal-research/courtlistener-api-key'
    )
    old_key = secret['SecretString']

    # Generate new key via CourtListener API
    # (CourtListener doesn't have automated key generation API yet)
    # For now, manual rotation required

    # When new key is available:
    secretsmanager.update_secret(
        SecretId='legal-research/courtlistener-api-key',
        SecretString=new_key
    )

    return {
        'statusCode': 200,
        'body': 'Key rotated successfully'
    }

# Set up scheduled Lambda invocation:
# - EventBridge rule: cron(0 0 * * ? *)  (daily check)
# - Triggers Lambda function
# - Lambda rotates key if needed
```

---

## Access Control

### Least Privilege Access

```bash
# 1. Create service account with minimal permissions
kubectl create serviceaccount legal-research -n legal-research

# 2. Create role with only needed permissions
kubectl create role secret-reader \
  --verb=get,list \
  --resource=secrets \
  -n legal-research

# 3. Bind role to service account
kubectl create rolebinding secret-reader-binding \
  --clusterrole=secret-reader \
  --serviceaccount=legal-research:legal-research \
  -n legal-research

# 4. Verify (only this pod can read secrets)
kubectl auth can-i get secrets --as=system:serviceaccount:legal-research:legal-research -n legal-research
```

### Audit Secret Access

```bash
# Kubernetes audit log
# Look for events with:
# - verb: get, list, watch
# - objectRef.kind: Secret
# - severity: Metadata

# AWS CloudTrail
# Look for API calls:
# - secretsmanager:GetSecretValue
# - secretsmanager:UpdateSecret

# Example query for unusual access:
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetSecretValue \
  --start-time 2025-12-01 \
  --end-time 2025-12-31
```

---

## Compliance & Auditing

### Audit Checklist

- [ ] API key changed in last 90 days
- [ ] Old API keys revoked
- [ ] Secret access logged and monitored
- [ ] Secret rotation documented
- [ ] No secrets in git history
- [ ] No secrets in container images
- [ ] Secrets encrypted in storage
- [ ] Secrets transmitted over TLS only
- [ ] Least privilege access implemented
- [ ] Incident response plan documented

### Compliance Standards

**SOC 2 Type II:**
- Secrets encrypted at rest and in transit ✅
- Access control implemented ✅
- Audit trail maintained ✅
- Regular rotation schedule ✅

**PCI DSS (if handling payment data):**
- Secrets not logged ✅
- Encryption of cardholder data ✅
- Secure deletion procedures ✅

**GDPR (if handling EU data):**
- Data minimization ✅
- Encryption ✅
- Access controls ✅
- Audit trail ✅

---

## Emergency Procedures

### Suspected Key Compromise

**Immediate actions (< 5 minutes):**

1. Revoke the key immediately
   ```bash
   # Log into CourtListener dashboard
   # Delete the API key
   ```

2. Rotate to backup key (if available)
   ```bash
   # Switch to backup API key temporarily
   kubectl set env deployment/legal-research-mcp \
     COURTLISTENER_API_KEY=$BACKUP_KEY \
     -n legal-research

   kubectl rollout restart deployment/legal-research-mcp -n legal-research
   ```

3. Check logs for unauthorized access
   ```bash
   kubectl logs -n legal-research deployment/legal-research-mcp \
     --since=24h | grep -i error
   ```

4. Notify security team / on-call engineer

**Within 1 hour:**

5. Generate new key
   ```bash
   # Create new key in CourtListener dashboard
   ```

6. Deploy new key
   ```bash
   kubectl create secret generic legal-research-secrets \
     --from-literal=COURTLISTENER_API_KEY=$NEW_KEY \
     --dry-run=client -o yaml | kubectl apply -f -

   kubectl rollout restart deployment/legal-research-mcp -n legal-research
   ```

7. Verify no unauthorized API usage
   ```bash
   # Check CourtListener API logs (if available)
   # Check request counts from your account
   ```

8. Document incident
   ```
   Date: 2025-12-12 15:45 UTC
   Issue: Suspected API key compromise
   Actions taken:
     - Revoked compromised key
     - Deployed backup key
     - Generated new key
     - Verified no unauthorized access
     - Redeployed new key
   Status: ✅ Resolved
   ```

### Bulk Key Rotation (Security Incident)

If all keys potentially compromised:

```bash
# 1. Scale down service (prevent leakage of old key)
kubectl scale deployment legal-research-mcp --replicas=0 -n legal-research

# 2. Generate new keys for all services
# Process: Contact CourtListener, request emergency key rotation

# 3. Update all secrets
for secret in legal-research-secrets legal-research-backup-secrets; do
  kubectl create secret generic $secret \
    --from-literal=COURTLISTENER_API_KEY=$NEW_KEY \
    --dry-run=client -o yaml | kubectl apply -f -
done

# 4. Verify no old keys in memory
# (Pods were scaled to 0, so no old key in memory)

# 5. Scale service back up with new keys
kubectl scale deployment legal-research-mcp --replicas=3 -n legal-research

# 6. Verify connectivity
kubectl logs -n legal-research deployment/legal-research-mcp | grep -i "api\|error"
```

---

## Recommended Approach by Environment

| Environment | Recommended | Reason |
|-------------|------------|--------|
| **Local Dev** | Environment variables | Simple, easy to manage locally |
| **Docker Compose** | .env file | Local development, simple setup |
| **Docker Swarm** | Docker Secrets | Built-in, encrypted, purpose-built |
| **Kubernetes** | Sealed Secrets | Safe for GitOps, encrypted, automatic |
| **AWS/Cloud** | AWS Secrets Manager + External Secrets | Enterprise-grade, audit trail, managed |
| **Enterprise** | HashiCorp Vault | Central management, audit, compliance |

---

## Quick Reference

### Create Secret (Kubernetes)
```bash
kubectl create secret generic legal-research-secrets \
  --from-literal=COURTLISTENER_API_KEY=$KEY \
  -n legal-research
```

### Update Secret
```bash
kubectl create secret generic legal-research-secrets \
  --from-literal=COURTLISTENER_API_KEY=$NEW_KEY \
  --dry-run=client -o yaml | kubectl apply -f -
```

### View Secret (with value)
```bash
kubectl get secret legal-research-secrets -n legal-research -o jsonpath='{.data.COURTLISTENER_API_KEY}' | base64 -d
```

### Rotate Key & Restart
```bash
kubectl create secret generic legal-research-secrets \
  --from-literal=COURTLISTENER_API_KEY=$NEW_KEY \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl rollout restart deployment/legal-research-mcp -n legal-research
```

---

## Further Reading

- [Kubernetes Secrets Documentation](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Sealed Secrets GitHub](https://github.com/bitnami-labs/sealed-secrets)
- [External Secrets Operator](https://external-secrets.io/)
- [HashiCorp Vault](https://www.vaultproject.io/)
- [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/)
- [OWASP - Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)

---

**See [DEPLOYMENT.md](./DEPLOYMENT.md) and [OPERATIONS.md](./OPERATIONS.md) for integration with deployment procedures.**
