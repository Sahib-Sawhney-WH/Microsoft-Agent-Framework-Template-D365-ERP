# Kubernetes Deployment

This guide covers deploying the MSFT Agent Framework on Kubernetes clusters for production environments.

## Overview

Kubernetes deployment provides:
- **High Availability** — Multiple replicas across nodes
- **Auto-scaling** — Scale based on demand
- **Rolling Updates** — Zero-downtime deployments
- **Self-healing** — Automatic container restart on failure
- **Resource Management** — CPU/memory limits and requests

## Prerequisites

- Kubernetes cluster (1.25+)
- `kubectl` configured with cluster access
- Container image pushed to a registry (ACR, Docker Hub, etc.)
- Azure credentials (service principal or workload identity)

## Quick Start

Deploy the agent with these manifests:

```bash
# Apply all manifests
kubectl apply -f k8s/

# Or apply individually
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
```

## Kubernetes Manifests

### Namespace

Create a dedicated namespace:

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: msft-agent
  labels:
    app.kubernetes.io/name: msft-agent-framework
    app.kubernetes.io/component: ai-agent
```

### ConfigMap

Store non-sensitive configuration:

```yaml
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: msft-agent-config
  namespace: msft-agent
data:
  agent.toml: |
    [agent]
    system_prompt = "config/system_prompt.txt"
    log_level = "INFO"
    default_model = "azure_openai"

    [[agent.models]]
    name = "azure_openai"
    provider = "azure_openai"
    deployment = "gpt-4o"
    api_version = "2024-10-01-preview"

    [agent.memory.cache]
    enabled = true
    host = "redis-master.redis.svc.cluster.local"
    port = 6379
    ssl = false
    ttl = 300
    prefix = "chat:"

  system_prompt.txt: |
    You are a helpful AI assistant powered by the MSFT Agent Framework.
    Provide accurate, helpful responses to user queries.
```

### Secret

Store sensitive credentials:

```yaml
# k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: msft-agent-secrets
  namespace: msft-agent
type: Opaque
stringData:
  AZURE_OPENAI_ENDPOINT: "https://your-resource.openai.azure.com/"
  AZURE_TENANT_ID: "your-tenant-id"
  AZURE_CLIENT_ID: "your-client-id"
  AZURE_CLIENT_SECRET: "your-client-secret"
```

**Important:** For production, use:
- **External Secrets Operator** with Azure Key Vault
- **Azure Workload Identity** instead of client secrets
- **Sealed Secrets** for GitOps workflows

### Deployment

Main workload deployment:

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: msft-agent
  namespace: msft-agent
  labels:
    app.kubernetes.io/name: msft-agent-framework
    app.kubernetes.io/component: api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: msft-agent
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: msft-agent
        app.kubernetes.io/name: msft-agent-framework
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9090"
    spec:
      serviceAccountName: msft-agent
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
        - name: agent
          image: myregistry.azurecr.io/msft-agent-framework:1.0.0
          imagePullPolicy: Always
          ports:
            - name: http
              containerPort: 8000
              protocol: TCP
            - name: metrics
              containerPort: 9090
              protocol: TCP
          env:
            - name: AZURE_OPENAI_ENDPOINT
              valueFrom:
                secretKeyRef:
                  name: msft-agent-secrets
                  key: AZURE_OPENAI_ENDPOINT
            - name: AZURE_TENANT_ID
              valueFrom:
                secretKeyRef:
                  name: msft-agent-secrets
                  key: AZURE_TENANT_ID
            - name: AZURE_CLIENT_ID
              valueFrom:
                secretKeyRef:
                  name: msft-agent-secrets
                  key: AZURE_CLIENT_ID
            - name: AZURE_CLIENT_SECRET
              valueFrom:
                secretKeyRef:
                  name: msft-agent-secrets
                  key: AZURE_CLIENT_SECRET
            - name: LOG_LEVEL
              value: "INFO"
          volumeMounts:
            - name: config
              mountPath: /app/config/agent.toml
              subPath: agent.toml
            - name: config
              mountPath: /app/config/system_prompt.txt
              subPath: system_prompt.txt
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2000m"
              memory: "2Gi"
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            initialDelaySeconds: 10
            periodSeconds: 10
            timeoutSeconds: 5
            successThreshold: 1
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            initialDelaySeconds: 15
            periodSeconds: 20
            timeoutSeconds: 5
            successThreshold: 1
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /health/live
              port: http
            initialDelaySeconds: 5
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 30
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
      volumes:
        - name: config
          configMap:
            name: msft-agent-config
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: msft-agent
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: msft-agent
                topologyKey: kubernetes.io/hostname
```

### Service

Expose the deployment:

```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: msft-agent
  namespace: msft-agent
  labels:
    app.kubernetes.io/name: msft-agent-framework
spec:
  type: ClusterIP
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
    - name: metrics
      port: 9090
      targetPort: metrics
      protocol: TCP
  selector:
    app: msft-agent
```

### Ingress

External access with TLS:

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: msft-agent
  namespace: msft-agent
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
spec:
  tls:
    - hosts:
        - agent.example.com
      secretName: msft-agent-tls
  rules:
    - host: agent.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: msft-agent
                port:
                  name: http
```

### ServiceAccount

For workload identity:

```yaml
# k8s/serviceaccount.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: msft-agent
  namespace: msft-agent
  annotations:
    # For Azure Workload Identity
    azure.workload.identity/client-id: "your-managed-identity-client-id"
```

## Health Probes

The framework provides three health endpoints:

| Probe | Endpoint | Purpose |
|-------|----------|---------|
| Startup | `/health/live` | Wait for app initialization |
| Readiness | `/health/ready` | Accept traffic only when ready |
| Liveness | `/health/live` | Restart if unresponsive |

### Probe Behavior

- **Startup Probe**: Allows 150 seconds (30 failures x 5s) for slow starts
- **Readiness Probe**: Removes pod from service after 3 failures
- **Liveness Probe**: Restarts pod after 3 failures

### Health Check Response

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0",
  "uptime_seconds": 3600.5,
  "components": [
    {"name": "azure_openai", "status": "healthy", "latency_ms": 45.2},
    {"name": "redis", "status": "healthy", "latency_ms": 2.1},
    {"name": "mcp", "status": "healthy", "latency_ms": 0.5, "details": {"tool_count": 5}}
  ]
}
```

## Horizontal Pod Autoscaler

Scale based on CPU/memory or custom metrics:

```yaml
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: msft-agent
  namespace: msft-agent
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: msft-agent
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15
        - type: Pods
          value: 4
          periodSeconds: 15
      selectPolicy: Max
```

## Pod Disruption Budget

Maintain availability during maintenance:

```yaml
# k8s/pdb.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: msft-agent
  namespace: msft-agent
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: msft-agent
```

## Network Policy

Restrict pod communication:

```yaml
# k8s/networkpolicy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: msft-agent
  namespace: msft-agent
spec:
  podSelector:
    matchLabels:
      app: msft-agent
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - protocol: TCP
          port: 8000
  egress:
    # Allow DNS
    - to:
        - namespaceSelector: {}
      ports:
        - protocol: UDP
          port: 53
    # Allow Azure services (adjust for your network)
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
      ports:
        - protocol: TCP
          port: 443
```

## Azure Key Vault Integration

### Using External Secrets Operator

Install the operator:

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace
```

Create a SecretStore:

```yaml
# k8s/secretstore.yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: azure-keyvault
  namespace: msft-agent
spec:
  provider:
    azurekv:
      authType: WorkloadIdentity
      vaultUrl: "https://your-keyvault.vault.azure.net"
      serviceAccountRef:
        name: msft-agent
```

Create an ExternalSecret:

```yaml
# k8s/externalsecret.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: msft-agent-secrets
  namespace: msft-agent
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: azure-keyvault
    kind: SecretStore
  target:
    name: msft-agent-secrets
    creationPolicy: Owner
  data:
    - secretKey: AZURE_OPENAI_ENDPOINT
      remoteRef:
        key: azure-openai-endpoint
    - secretKey: AZURE_CLIENT_SECRET
      remoteRef:
        key: agent-client-secret
```

## Monitoring

### Prometheus ServiceMonitor

```yaml
# k8s/servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: msft-agent
  namespace: msft-agent
  labels:
    release: prometheus
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: msft-agent-framework
  endpoints:
    - port: metrics
      interval: 30s
      path: /metrics
```

### Grafana Dashboard

Import the provided dashboard or create custom panels for:
- Request latency (p50, p95, p99)
- Request rate
- Error rate
- Token usage
- Health status

## AKS-Specific Configuration

### Azure Workload Identity

Enable workload identity for secure Azure authentication:

```bash
# Enable on cluster
az aks update -g myResourceGroup -n myAKSCluster --enable-oidc-issuer --enable-workload-identity

# Create managed identity
az identity create --name msft-agent-identity --resource-group myResourceGroup

# Create federated credential
az identity federated-credential create \
  --name msft-agent-federated \
  --identity-name msft-agent-identity \
  --resource-group myResourceGroup \
  --issuer "$(az aks show -g myResourceGroup -n myAKSCluster --query oidcIssuerProfile.issuerUrl -o tsv)" \
  --subject system:serviceaccount:msft-agent:msft-agent
```

Update deployment:

```yaml
spec:
  template:
    metadata:
      labels:
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: msft-agent
```

### Azure CNI Networking

For VNet integration:

```yaml
# Pod can access private endpoints
spec:
  template:
    spec:
      dnsPolicy: ClusterFirst
      dnsConfig:
        options:
          - name: ndots
            value: "5"
```

## Troubleshooting

### Common Issues

**Pods not starting:**
```bash
kubectl describe pod -n msft-agent -l app=msft-agent
kubectl logs -n msft-agent -l app=msft-agent --previous
```

**Health check failures:**
```bash
kubectl exec -n msft-agent -it deploy/msft-agent -- curl localhost:8000/health
```

**Network connectivity:**
```bash
kubectl exec -n msft-agent -it deploy/msft-agent -- curl -v https://your-resource.openai.azure.com/
```

**Resource issues:**
```bash
kubectl top pods -n msft-agent
kubectl describe node
```

### Debug Pod

Deploy a debug pod:

```bash
kubectl run debug --rm -it --image=curlimages/curl -n msft-agent -- sh
# Then: curl msft-agent/health
```

## Related Documentation

- [Deployment Overview](overview.md) — Compare deployment options
- [Docker Deployment](docker.md) — Container basics
- [Azure Deployment](azure-deployment.md) — Azure PaaS options
- [Production Checklist](production-checklist.md) — Pre-deployment verification
- [Observability](../observability.md) — Monitoring setup

---
*Last updated: 2026-01-17*
