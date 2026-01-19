# Deployment Overview

This guide covers the deployment options for the MSFT Agent Framework, helping you choose the right approach for your environment.

## Overview

The MSFT Agent Framework can be deployed in multiple ways depending on your infrastructure requirements, scale, and operational preferences.

## Prerequisites

Before deploying, ensure you have:

- **Azure OpenAI Resource** — With a deployed model (e.g., gpt-4o)
- **Azure Identity** — Service principal or managed identity configured
- **Network Access** — Connectivity to Azure services (OpenAI, Redis, ADLS if used)

## Deployment Options Comparison

| Option | Best For | Complexity | Scale | Management |
|--------|----------|------------|-------|------------|
| [Docker](docker.md) | Development, small deployments | Low | Single instance | Manual |
| [Kubernetes](kubernetes.md) | Production, high availability | Medium | Horizontal | Automated |
| [Azure Container Apps](azure-deployment.md#azure-container-apps) | Serverless containers | Low | Auto-scale | Managed |
| [Azure App Service](azure-deployment.md#azure-app-service) | Simple web hosting | Low | Vertical + slots | Managed |
| [Azure Kubernetes Service](azure-deployment.md#azure-kubernetes-service) | Enterprise, full control | High | Horizontal | Semi-managed |

## Architecture Diagrams

### Single Instance Deployment (Docker)

```mermaid
flowchart LR
    subgraph Client
        A[User/Application]
    end

    subgraph Docker Host
        B[MSFT Agent Container]
    end

    subgraph Azure Services
        C[Azure OpenAI]
        D[Azure Cache for Redis]
        E[Azure Blob Storage]
    end

    A -->|HTTP| B
    B -->|API Calls| C
    B -->|Cache| D
    B -->|Persistence| E

    style B fill:#0078d4,color:#fff
    style C fill:#50e6ff,color:#000
    style D fill:#50e6ff,color:#000
    style E fill:#50e6ff,color:#000
```

### Kubernetes Deployment (High Availability)

```mermaid
flowchart TB
    subgraph Internet
        A[Users]
    end

    subgraph Kubernetes Cluster
        subgraph Ingress
            B[Ingress Controller]
        end

        subgraph Workloads
            C1[Agent Pod 1]
            C2[Agent Pod 2]
            C3[Agent Pod N]
        end

        subgraph Config
            D[ConfigMap]
            E[Secrets]
        end
    end

    subgraph Azure Services
        F[Azure OpenAI]
        G[Azure Cache for Redis]
        H[Azure Blob Storage]
        I[Azure Key Vault]
    end

    A --> B
    B --> C1
    B --> C2
    B --> C3
    C1 --> F
    C2 --> G
    C3 --> H
    E -.->|Sync| I

    style C1 fill:#0078d4,color:#fff
    style C2 fill:#0078d4,color:#fff
    style C3 fill:#0078d4,color:#fff
```

### Azure PaaS Deployment

```mermaid
flowchart TB
    subgraph Internet
        A[Users]
    end

    subgraph Azure["Azure Platform"]
        subgraph Networking
            B[Application Gateway / Front Door]
        end

        subgraph Compute
            C[Container Apps / App Service]
        end

        subgraph Data
            D[Azure Cache for Redis]
            E[Azure Blob Storage]
        end

        subgraph AI
            F[Azure OpenAI]
        end

        subgraph Security
            G[Key Vault]
            H[Managed Identity]
        end

        subgraph Monitoring
            I[Application Insights]
        end
    end

    A --> B
    B --> C
    C --> D
    C --> E
    C --> F
    C -.->|Secrets| G
    C -.->|Auth| H
    C -.->|Telemetry| I

    style C fill:#0078d4,color:#fff
    style F fill:#50e6ff,color:#000
```

## Deployment Decision Tree

Use this decision tree to choose the right deployment option:

```mermaid
flowchart TD
    A[Start] --> B{Production?}
    B -->|No| C[Docker]
    B -->|Yes| D{Managed Infrastructure?}
    D -->|Yes| E{Serverless?}
    D -->|No| F[Kubernetes]
    E -->|Yes| G[Azure Container Apps]
    E -->|No| H{Full PaaS?}
    H -->|Yes| I[Azure App Service]
    H -->|No| J[Azure Kubernetes Service]

    style C fill:#107c10,color:#fff
    style F fill:#107c10,color:#fff
    style G fill:#107c10,color:#fff
    style I fill:#107c10,color:#fff
    style J fill:#107c10,color:#fff
```

## Environment Configuration

All deployment options require the same core environment variables:

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | `https://myresource.openai.azure.com/` |
| `AZURE_OPENAI_DEPLOYMENT` | Model deployment name | `gpt-4o` |

### Authentication Variables

For **Managed Identity** (recommended for Azure deployments):

| Variable | Description |
|----------|-------------|
| `AZURE_CLIENT_ID` | Managed identity client ID (user-assigned only) |

For **Service Principal**:

| Variable | Description |
|----------|-------------|
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | Application (client) ID |
| `AZURE_CLIENT_SECRET` | Client secret |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_HOST` | Redis host (overrides config) | From `agent.toml` |
| `REDIS_PORT` | Redis port | `6380` |
| `ADLS_ACCOUNT_NAME` | Storage account name | From `agent.toml` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Health Endpoints

All deployments expose the same health check endpoints:

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `/health` | Full health check | `{"status": "healthy", "components": [...]}` |
| `/health/ready` | Readiness probe | `200 OK` or `503 Service Unavailable` |
| `/health/live` | Liveness probe | `200 OK` |

Use these endpoints for:
- **Kubernetes probes** — Configure readinessProbe and livenessProbe
- **Load balancer health** — Route traffic only to healthy instances
- **Monitoring alerts** — Trigger alerts on degraded status

## Security Considerations

Regardless of deployment option:

1. **Never expose credentials in code** — Use environment variables or Key Vault
2. **Use Managed Identity** — Eliminates credential management for Azure resources
3. **Network isolation** — Deploy in VNet with private endpoints where possible
4. **TLS everywhere** — Encrypt all traffic in transit
5. **Least privilege** — Grant only required permissions to identity

## Next Steps

Choose your deployment guide:

- **[Docker Deployment](docker.md)** — Local development and simple deployments
- **[Kubernetes Deployment](kubernetes.md)** — Production Kubernetes clusters
- **[Azure Deployment](azure-deployment.md)** — Azure PaaS options (Container Apps, App Service, AKS)
- **[Production Checklist](production-checklist.md)** — Pre-deployment verification

## Related Documentation

- [Architecture](../architecture.md) — System architecture and component overview
- [Security](../security.md) — Security features and best practices
- [Observability](../observability.md) — Monitoring and tracing setup

---
*Last updated: 2026-01-17*
