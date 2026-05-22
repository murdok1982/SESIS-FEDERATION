# SESIS-FEDERATION Architecture

## Overview
Monorepo unifying 5 military-grade intelligence platforms.

## Directory Structure
```
backend/         - FastAPI + Celery workers
frontend/        - Next.js 14 dashboard
mobile/          - Flutter + Wear OS
ml/              - Anomaly detection, vision
scripts/         - Deployment utilities
infra/           - Nginx, Prometheus, Grafana, K8s
docs/            - Architecture, API, SOPs
compliance/      - STANAG, ENS, NIST matrices
```

## Core Services
1. **Fusion Engine** — central orchestrator
2. **fsociety LLM** — unified AI brain
3. **Event Bus (NATS)** — C2/telemetry
4. **Audit Chain** — immutable SHA-256
5. **ABAC** — attribute-based access control
