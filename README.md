# 🛡️ SESIS-FEDERATION

> **Plataforma Unificada de Gobierno Digital Militar**
>
> *Fusión de SESIS · AEGIS-IMINT · Atalaya · Global-Intelligence · SpyManager*
> *en un solo sistema C4ISR soberano.*

<p align="center">
  <img src="https://img.shields.io/badge/Status-Active%20Development-success?style=for-the-badge&amp;logo=shield" alt="Status">
  <img src="https://img.shields.io/badge/Security-Zero%20Trust-red?style=for-the-badge&amp;logo=lock" alt="Zero Trust">
  <img src="https://img.shields.io/badge/LLM-fsociety-blue?style=for-the-badge&amp;logo=openai" alt="fsociety">
  <img src="https://img.shields.io/badge/Architecture-C4ISR-purple?style=for-the-badge&amp;logo=apachekafka" alt="C4ISR">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License">
</p>

---

## Architecture

```
                        SESIS-FEDERATION
         Plataforma Unificada de Gobierno Digital Militar

  +-------------+  +--------------+  +-------------------+
  | AEGIS-IMINT |  |   Atalaya    |  | Global-Intelligence|
  | (SAT INTEL) |  | (Multi-INT)  |  |    (Analysis)     |
  +------+------+  +------+-------+  +---------+---------+
         |                |                     |
         +----------------+---------------------+
                          |
          +------------------------------------------+
          |           Fusion Engine (Core)            |
          |  + SESIS C4ISR Orchestrator              |
          |  + Ares/fsociety LLM (cerebro unico)     |
          |  + ABAC/RLS multi-nivel unificado        |
          |  + Audit chain inmutable (SHA-256)       |
          +------------------------------------------+
         |                |                     |
         v                v                     v
  +-------------+  +--------------+  +-------------------+
  | SpyManager  |  |  SESIS C2    |  | Mobile / Wearable |
  | (Agents)    |  | (Dashboard)  |  |    (Flutter)      |
  +-------------+  +--------------+  +-------------------+
```

## Modules

| Module | Source | Function | Status |
|--------|--------|----------|--------|
| **sesis-core** | Fusion | Config, auth, classification, audit chain, event bus | Building |
| **sesis-c2** | SESIS | Tactical dashboard, C2, alerts, assets, timeline | Building |
| **sesis-satellite** | AEGIS-IMINT | Sentinel-2, YOLOv8, change detection, IMINT reports | Building |
| **sesis-osint** | Atalaya | 8 multi-INT disciplines, OSINT providers, STANAG 4774/4778 | Building |
| **sesis-intel** | Global-Intelligence | Analysis, reports, multi-level classification, RAG | Building |
| **sesis-agents** | SpyManager | Field agents, mesh, steganography, Neo4j link analysis | Building |
| **sesis-mobile** | SpyManager | Flutter app + Wear OS, ghost mode, duress PIN | Building |
| **sesis-ml** | SESIS + AEGIS | Isolation forest, YOLOv8, anomaly detection | Building |

## LLM Unificado: fsociety

All modules use **fsociety** (Qwen2.5-Coder-1.5B-Instruct fine-tuned) as unified brain:

```bash
ollama run fsociety
```

Operates air-gapped within the trust perimeter. No external API dependency.

## Quick Start

```bash
git clone https://github.com/murdok1982/SESIS-FEDERATION.git
cd SESIS-FEDERATION
cp .env.example .env
# Edit .env with your configuration
docker compose up -d
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Celery + Redis + NATS |
| Database | PostgreSQL 15 + pgvector + Neo4j |
| LLM | fsociety (Qwen2.5) + Ollama |
| Web Frontend | Next.js 14 + Tailwind + shadcn/ui |
| Mobile | Flutter + Wear OS |
| Vector DB | pgvector |
| Messaging | NATS (C2/telemetry) |
| Monitoring | Prometheus + Grafana |
| Containers | Docker Compose + K8s |

## License

MIT License — see [LICENSE](LICENSE).
