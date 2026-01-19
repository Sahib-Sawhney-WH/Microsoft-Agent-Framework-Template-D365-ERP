# Production Checklist

This checklist ensures your MSFT Agent Framework deployment is production-ready.

## Overview

Use this checklist before deploying to production. Each section covers a critical aspect of production readiness.

---

## Pre-Deployment Checklist

### Configuration

- [ ] **Configuration file validated** — `agent.toml` syntax verified
- [ ] **System prompt reviewed** — Appropriate for production use case
- [ ] **Log level set to INFO** — DEBUG disabled in production
- [ ] **Model deployment verified** — Azure OpenAI model is deployed and accessible
- [ ] **Tool configurations tested** — All enabled tools work correctly

### Secrets Management

- [ ] **No hardcoded secrets** — All credentials use environment variables or Key Vault
- [ ] **Service principal or managed identity configured** — Not using personal credentials
- [ ] **Key Vault integration verified** — Secrets accessible from deployment
- [ ] **Secret rotation plan** — Process for rotating credentials documented
- [ ] **`.env` files excluded from git** — `.gitignore` includes `.env*`

### Container Image

- [ ] **Image tagged with version** — Not using `latest` in production
- [ ] **Image scanned for vulnerabilities** — No critical/high CVEs
- [ ] **Base image updated** — Using recent Python 3.12-slim
- [ ] **Multi-stage build used** — Minimal final image size
- [ ] **Non-root user configured** — Container doesn't run as root

---

## Security Checklist

### Authentication & Authorization

- [ ] **Managed Identity enabled** — Using Azure AD for authentication
- [ ] **Least privilege applied** — Identity has only required permissions
- [ ] **API authentication configured** — If exposing API externally
- [ ] **Rate limiting enabled** — Protection against abuse
- [ ] **CORS configured** — `allowed_origins` restricted to known domains

### Network Security

- [ ] **HTTPS enforced** — All traffic encrypted in transit
- [ ] **TLS 1.2+ required** — Older protocols disabled
- [ ] **VNet integration considered** — Private endpoints for Azure services
- [ ] **Network policies applied** — Pod-to-pod communication restricted (K8s)
- [ ] **WAF/DDoS protection** — For internet-facing deployments

### Data Security

- [ ] **PII detection enabled** — `[agent.security.pii_detection]` configured
- [ ] **Input validation active** — `[agent.security.input_validation]` configured
- [ ] **Prompt injection detection** — Security middleware enabled
- [ ] **Chat history encryption** — Data encrypted at rest in Redis/ADLS
- [ ] **Retention policies defined** — Data lifecycle management configured

### Compliance

- [ ] **Data residency requirements met** — Resources in correct region
- [ ] **Audit logging enabled** — All access logged
- [ ] **Compliance certifications verified** — SOC2, HIPAA, etc. as required
- [ ] **Privacy policy updated** — Reflects AI assistant usage

---

## High Availability Checklist

### Redundancy

- [ ] **Multiple replicas deployed** — Minimum 2-3 instances
- [ ] **Replicas spread across zones** — Using topology spread constraints
- [ ] **Pod anti-affinity configured** — Replicas on different nodes
- [ ] **Load balancer health checks** — Only healthy instances receive traffic

### Resilience

- [ ] **Health probes configured** — Readiness and liveness probes defined
- [ ] **Startup probe added** — For slow-starting containers
- [ ] **Pod Disruption Budget set** — Maintains availability during updates
- [ ] **Graceful shutdown implemented** — SIGTERM handled correctly
- [ ] **Circuit breakers configured** — For external service calls

### Disaster Recovery

- [ ] **Backup strategy defined** — Redis snapshots, ADLS backup
- [ ] **Recovery procedures documented** — RTO/RPO defined
- [ ] **Multi-region deployment considered** — For critical workloads
- [ ] **Failover tested** — DR procedures validated

---

## Observability Checklist

### Logging

- [ ] **Structured logging enabled** — JSON format for log aggregation
- [ ] **Log level appropriate** — INFO for production, DEBUG for troubleshooting
- [ ] **Correlation IDs included** — Request tracing across services
- [ ] **PII scrubbing configured** — Sensitive data not logged
- [ ] **Log retention configured** — Appropriate retention period

### Metrics

- [ ] **Prometheus metrics exposed** — `/metrics` endpoint available
- [ ] **Key metrics identified**:
  - [ ] Request latency (p50, p95, p99)
  - [ ] Request rate
  - [ ] Error rate
  - [ ] Token usage
  - [ ] Health status
- [ ] **Dashboards created** — Grafana/Azure Monitor dashboards ready
- [ ] **Baseline established** — Normal performance documented

### Tracing

- [ ] **OpenTelemetry configured** — Distributed tracing enabled
- [ ] **Trace sampling configured** — Appropriate sampling rate for production
- [ ] **Trace context propagation** — W3C trace context headers
- [ ] **Backend configured** — Jaeger, Azure Monitor, or similar

### Alerting

- [ ] **Critical alerts defined**:
  - [ ] Service down (no healthy instances)
  - [ ] High error rate (>5%)
  - [ ] High latency (p99 > SLA)
  - [ ] Resource exhaustion (CPU/memory > 90%)
- [ ] **Warning alerts defined**:
  - [ ] Elevated error rate (>1%)
  - [ ] Increased latency (p99 > baseline)
  - [ ] Resource pressure (CPU/memory > 70%)
- [ ] **On-call rotation configured** — Alert recipients defined
- [ ] **Runbooks created** — Response procedures documented

---

## Performance Checklist

### Resource Allocation

- [ ] **CPU requests/limits set** — Based on load testing
- [ ] **Memory requests/limits set** — Based on load testing
- [ ] **Autoscaling configured** — HPA or Container Apps scaling rules
- [ ] **Scale limits defined** — Min/max replicas set

### Optimization

- [ ] **Connection pooling configured** — For Redis, HTTP clients
- [ ] **Caching strategy defined** — Response caching where appropriate
- [ ] **Timeout values set** — Appropriate timeouts for all external calls
- [ ] **Retry policies configured** — Exponential backoff for transient failures

### Load Testing

- [ ] **Load test executed** — Simulated production traffic
- [ ] **Performance baseline established** — Normal latency/throughput documented
- [ ] **Capacity limits identified** — Maximum sustainable load known
- [ ] **Bottlenecks addressed** — Performance issues resolved

---

## Operational Checklist

### Deployment

- [ ] **CI/CD pipeline configured** — Automated build and deploy
- [ ] **Rolling updates configured** — Zero-downtime deployments
- [ ] **Rollback procedure documented** — Quick rollback capability
- [ ] **Deployment slots used** — Blue/green or staging slots (App Service)
- [ ] **Canary deployments considered** — Gradual rollout for critical changes

### Documentation

- [ ] **Runbooks created** — Common operational procedures
- [ ] **Architecture documented** — System design and dependencies
- [ ] **API documentation available** — For consumers of the service
- [ ] **Incident response plan** — Escalation procedures defined

### Team Readiness

- [ ] **On-call schedule defined** — 24/7 coverage if required
- [ ] **Access provisioned** — Team has required permissions
- [ ] **Training completed** — Team familiar with system
- [ ] **Communication channels** — Slack/Teams channels for incidents

---

## Final Verification

### Smoke Tests

Run these tests after deployment:

```bash
# Health check
curl -f https://your-agent.example.com/health

# Readiness check
curl -f https://your-agent.example.com/health/ready

# Basic functionality (adjust for your API)
curl -X POST https://your-agent.example.com/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, test message"}'
```

### Verification Checklist

- [ ] **Health endpoint returns healthy** — All components operational
- [ ] **Basic request succeeds** — End-to-end flow works
- [ ] **Metrics being collected** — Data appearing in dashboards
- [ ] **Logs being aggregated** — Logs visible in log system
- [ ] **Alerts firing correctly** — Test alert received

---

## Post-Deployment

### First 24 Hours

- [ ] **Monitor error rates** — Watch for unexpected errors
- [ ] **Monitor latency** — Compare to baseline
- [ ] **Check resource usage** — Verify scaling behavior
- [ ] **Review logs** — Look for warnings or errors

### First Week

- [ ] **Analyze usage patterns** — Understand real traffic
- [ ] **Tune autoscaling** — Adjust based on actual load
- [ ] **Review costs** — Ensure within budget
- [ ] **Gather feedback** — From users and stakeholders

---

## Quick Reference

### Minimum Requirements

| Category | Requirement |
|----------|-------------|
| Replicas | 2+ for HA |
| Memory | 1GB+ per replica |
| CPU | 0.5+ cores per replica |
| Health Probes | Readiness + Liveness |
| Logging | Structured JSON |
| Secrets | Key Vault or env vars |

### Critical Alerts

| Alert | Threshold | Severity |
|-------|-----------|----------|
| Service Down | 0 healthy replicas | Critical |
| High Error Rate | >5% | Critical |
| High Latency | p99 > 10s | Critical |
| Memory Pressure | >95% | Critical |
| Elevated Errors | >1% | Warning |
| Increased Latency | p99 > 5s | Warning |

---

## Related Documentation

- [Deployment Overview](overview.md) — Deployment options
- [Docker Deployment](docker.md) — Container guide
- [Kubernetes Deployment](kubernetes.md) — K8s manifests
- [Azure Deployment](azure-deployment.md) — Azure services
- [Security](../security.md) — Security features
- [Observability](../observability.md) — Monitoring setup

---
*Last updated: 2026-01-17*
