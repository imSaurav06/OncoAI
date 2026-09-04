# System Architecture: OncoAI Data Platform

## 1. Architectural Philosophy
The OncoAI Chemistry & Bioactivity Data Platform follows the core principle:
> **Store raw data once, process reproducibly, index intelligently, and expose only query results through versioned APIs.**

The consuming AI drug-discovery SaaS application never downloads or loads the complete chemical or bioactivity corpus into application memory. Instead, all interaction is mediated through stable, version-pinned, contract-tested REST APIs backed by a three-tiered storage hierarchy and specialized chemistry query engines.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    OncoAI Drug Discovery SaaS / AI Models               │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ HTTPS / REST (OpenAPI 3.1)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Versioned API Gateway (/v1)                         │
│  - Request ID correlation (UUIDv4)     - Auth & Service Credentials     │
│  - Strict Pydantic Envelope            - High-Precision Latency Timing  │
└──────────────────┬─────────────────┬──────────────────┬─────────────────┘
                   │                 │                  │
                   ▼                 ▼                  ▼
      ┌────────────────────┐ ┌───────────────┐ ┌───────────────────┐
      │   Query Engine     │ │   Chemistry   │ │   Job System      │
      │  - Planner/Router  │ │    Engine     │ │  - Async Worker   │
      │  - InChIKey B-tree │ │ - RDKit       │ │  - Tasks (Ingest/ │
      │  - Popcount Filter │ │   2024.03.5   │ │    Standardize)   │
      │  - Tanimoto Top-K  │ │ - Salt Strip  │ │  - Idempotent Runs│
      │  - Faceted Filters │ │ - Descriptors │ │  - Rejection Logs │
      └─────────┬──────────┘ └───────┬───────┘ └─────────┬─────────┘
                │                    │                   │
                ▼                    ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Tiered Storage Hierarchy                          │
│                                                                         │
│  [LAYER C: HOT SERVING]                                                 │
│  - PostgreSQL / SQLite relational database with B-tree indexes          │
│  - Compound identity, InChIKeys, targets, assays, bioactivity, jobs     │
│                                                                         │
│  [LAYER B: WARM COLUMNAR ANALYTICS]                                     │
│  - Parquet data lake partitioned by ingestion year/month/source         │
│  - Snappy compressed, DuckDB/Arrow analytical query engine              │
│                                                                         │
│  [LAYER A: COLD RAW IMMUTABLE DATA LAKE]                                │
│  - S3-compatible Object Storage (MinIO / AWS S3 / Local Object Lake)    │
│  - Raw source payloads, SHA-256 integrity verification, manifests       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Storage Tiering Breakdown

### Layer A — Cold Raw Lake
- **Storage medium**: S3-compatible object storage (`s3://oncoai-lake/raw/` or `data/storage/raw/`).
- **Characteristics**: Immutable, write-once, never overwritten.
- **Integrity**: Every payload is digested with SHA-256. A sidecar `.meta.json` metadata manifest records source name, version, acquisition timestamp, content length, and hash.

### Layer B — Warm Columnar Analytics Lake
- **Storage medium**: Apache Parquet files (`data/storage/parquet/compounds/` and `data/storage/parquet/bioactivity/`).
- **Partitioning**: Partitioned by source and ingestion date (`source=chembl/year=2026/month=09/`).
- **Engine**: Apache Arrow and DuckDB for vectorized multi-column analytical scans and bulk descriptor extraction for machine learning feature matrices without touching the relational database.

### Layer C — Hot Relational Serving Store
- **Storage medium**: PostgreSQL (Production) / SQLite (Local development test mode).
- **Indexing**: B-tree indexes on `inchikey`, `compound_id`, `target_id`, `cell_line_id`, `activity_type`, `activity_value_nm`, `created_at`.
- **Purpose**: Low-latency candidate retrieval, relational joins (Compound -> Assay -> Target -> Bioactivity), and transactional job state transitions.

---

## 3. High-Scale Evolutionary Path

| Scale | Storage Mechanism | Query / Search Engine | Compute Layer |
| :--- | :--- | :--- | :--- |
| **10^4 - 10^5 (Current)** | SQLite/PostgreSQL + Local Object Store + Parquet | Popcount-bounded Morgan bit vectors in-memory + B-tree DB | Async background worker pool |
| **10^6 - 10^7** | Managed PostgreSQL (RDS/Aurora) + AWS S3 + Parquet | PostgreSQL `rdkit` cartridge (fps indexing) + DuckDB Lakehouse | Celery / Redis / AWS SQS workers |
| **10^8 - 10^9+** | Distributed Object Lake (Iceberg / Delta) + ClickHouse | Distributed inverted chemical index + FAISS / Milvus GPU similarity | Ray / Spark decoupled worker clusters |

*Crucial Design Guarantee*: The SaaS REST API contracts, Pydantic schemas, and canonical data models remain 100% constant across every scale transition.
