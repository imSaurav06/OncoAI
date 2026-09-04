# OncoAI Chemistry & Bioactivity Data Platform — Production Foundation v1

A scalable, API-first scientific data platform and ingestion engine designed for AI-driven oncology drug discovery.

---

## 🔬 System Architecture

The platform is designed around the core principle: **Store raw data once, process reproducibly, index intelligently, and expose only query results through APIs.**

```
                                  [ External Data Sources ]
                             ChEMBL | PubChem | Wet-Lab Experiments
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │            LAYER A: RAW DATA LAKE             │
                    │   Immutable Raw JSONL / Byte Payloads (S3)    │
                    └───────────────────────┬───────────────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │          RDKIT STANDARDIZATION ENGINE         │
                    │  9-Stage Deterministic Pipeline (v2024.03.5)  │
                    │   • Sanitization      • Metal Disconnection   │
                    │   • Salt Stripping    • Charge Neutralization │
                    │   • Tautomer Canonicalization (InChIKey)      │
                    └───────────┬───────────────────────┬───────────┘
                                │                       │
                                ▼                       ▼
┌────────────────────────────────────────┐     ┌────────────────────────────────────────┐
│     LAYER B: COLUMNAR ANALYTICS        │     │         LAYER C: SERVING STORE         │
│  Partitioned Parquet Lake (Warm Tier)  │     │   Relational Hot Tier (PostgreSQL)     │
│   • Vectorized Polars/DuckDB Scans     │     │   • B-tree InChIKey Lookups (<5ms)     │
│   • Precomputed Morgan Fingerprints    │     │   • Pre-filtered Bitwise Similarity    │
│   • Scalable Analytical Queries        │     │   • Joint Target/Assay Faceted Joins   │
└────────────────────────────────────────┘     └───────────────────┬────────────────────┘
                                                                   │
                                                                   ▼
                                                       ┌────────────────────────┐
                                                       │   FASTAPI SERVICE v1   │
                                                       │  Standardized Envelopes│
                                                       │  Token Authentication  │
                                                       └────────────────────────┘
```

---

## ⚡ Key Highlights & Benchmark Performance

Empirically validated on modern AMD64 hardware (`scripts/run_benchmarks.py`):

| Operation | Corpus Size | Throughput / Latency | Architectural Optimizations |
| :--- | :--- | :--- | :--- |
| **RDKit Standardization** | Single thread | **26.7 molecules/sec** (37.4 ms/mol) | Metal disconnect, salt stripping, charge neutralization, tautomer canonicalization |
| **Full Chemical Analysis** | Single thread | **20.4 molecules/sec** (49.0 ms/mol) | Lipinski & Veber descriptors, Murcko scaffold, 2048-bit Morgan FP |
| **Molecular Similarity Search** | 5,000 compounds | **Median: 6.81 ms** (P95: 10.05 ms) | Popcount-bounded pre-filtering + C++ vectorized `BulkTanimotoSimilarity` |
| **InChIKey Exact Lookup** | Database indexed | **Median: 3.84 ms** (P95: 38.74 ms) | Indexed relational B-tree direct hit |
| **Faceted Bioactivity Search** | Multi-table join | **Median: 17.75 ms** (P95: 32.89 ms)| Indexed compound + target + assay + cell-line joint query |

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.11+ or 3.12
- SQLite (default for local development) or PostgreSQL 15+

### 2. Environment Setup
```bash
# Clone repository
git clone https://github.com/your-org/oncoai-data-platform.git
cd oncoai-data-platform

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # Windows PowerShell
# or source .venv/bin/activate (Linux/macOS)

# Install pinned dependencies
pip install -r requirements.txt
```

### 3. Run Automated Tests
```bash
pytest -v
```
*Output: 24 tests passed across chemistry pipeline, bioactivity normalization, molecular similarity, and API endpoints.*

### 4. Seed Oncology Dataset
Populates validated oncology targets (EGFR, BRAF, KRAS, CDK4) and clinical inhibitors (Osimertinib, Gefitinib, Vemurafenib, Sotorasib, Palbociclib, Lapatinib) across ChEMBL, PubChem, and In-House screening lab adapters:
```bash
python scripts/seed_oncology_data.py
```

### 5. Launch the API Service
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Access the interactive OpenAPI Documentation at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Liveness Probe**: [http://localhost:8000/health](http://localhost:8000/health)
- **Readiness Probe**: [http://localhost:8000/ready](http://localhost:8000/ready)
- **Telemetry Metrics**: [http://localhost:8000/metrics](http://localhost:8000/metrics)

---

## 📡 API Reference Overview

All requests require authentication via the `X-API-Key` header (default development key: `oncoai_live_secret_key_v1`).

### Chemical Standardization
`POST /v1/compounds/standardize`
```json
{
  "smiles": "COc1cc(N(C)CCN(C)C)c(NC(=O)C=C)cc1Nc1nccc(n1)c1cn(C)c2ccccc12.CS(=O)(=O)O"
}
```
*Response highlights:*
```json
{
  "status": "success",
  "data": {
    "canonical_smiles": "C=CC(=O)Nc1cc(Nc2nccc(-c3cn(C)c4ccccc34)n2)c(OC)cc1N(C)CCN(C)C",
    "inchikey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
    "status": "valid",
    "was_modified": true,
    "salt_removed": true,
    "salt_fragment_smiles": "CS(=O)(=O)O"
  }
}
```

### Full Molecular Analysis
`POST /v1/compounds/analyze`
*Returns InChIKey, Murcko scaffold, Lipinski/Veber physicochemical descriptors, and 2048-bit Morgan fingerprint summary.*

### Molecular Similarity Search
`POST /v1/compounds/similarity`
```json
{
  "smiles": "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1",
  "threshold": 0.5,
  "limit": 10,
  "target_id": "TGT_EGFR",
  "activity_type": "IC50",
  "max_activity_nm": 100.0
}
```

### Faceted Bioactivity Search
`POST /v1/bioactivity/search`
```json
{
  "gene_symbol": "EGFR",
  "activity_type": "IC50",
  "max_normalized_value": 50.0,
  "is_experimental": false,
  "limit": 20
}
```

### Asynchronous Ingestion & Processing
`POST /v1/jobs`
```json
{
  "job_type": "INGESTION",
  "input_params": {
    "source_id": "SRC_CHEMBL",
    "dataset_name": "Kinase Inhibitors 2026",
    "dataset_version": "v1.0",
    "records": [...]
  }
}
```
*Response: 202 Accepted with `job_id`. Non-blocking background worker processes records, generates QC reports, and updates progress percentage.*

---

## 🛡️ Data Quality & Provenance (QC)

Every record processed generates an immutable provenance audit log tracking:
- RDKit engine version (`2024.03.5`)
- Pipeline transformation version (`chem-std-1.0.0`)
- Normalization rules applied
- Outlier warnings (e.g. suspicious activity values or extreme affinities)
- Explicit rejection reasons logged in `rejected_records` for transparent debugging.

---

## 📁 Repository Structure

```
OncoAI/
├── app/
│   ├── api/                 # FastAPI routes, routers, and request tracing middleware
│   │   ├── v1/              # Versioned API endpoints (compounds, bioactivity, sources, jobs)
│   ├── chemistry/           # RDKit standardization, descriptors, fingerprints, validators
│   ├── config/              # Pydantic settings and version constants
│   ├── deduplication/       # InChIKey entity resolver and identifier mapping
│   ├── indexing/            # Popcount-bounded Morgan similarity index and query planner
│   ├── ingestion/           # Source adapters (ChEMBL, PubChem, In-House Wet-Lab)
│   ├── jobs/                # Async job manager, queue executor, and background tasks
│   ├── models/              # SQLAlchemy canonical relational data models
│   ├── normalization/       # Bioactivity unit normalization & pActivity calculation
│   ├── quality/             # Automated QC auditor and provenance tracking
│   ├── schemas/             # Pydantic v2 API request/response envelopes
│   ├── security/            # API key authentication & service credentials
│   ├── storage/             # Tiered storage: Database (Hot), Parquet (Warm), S3 Lake (Cold)
│   └── main.py              # Application entrypoint and lifecycle events
├── data/storage/            # Local data lake root (raw/ and parquet/)
├── scripts/
│   ├── run_benchmarks.py    # Latency, throughput, and index performance benchmarking
│   └── seed_oncology_data.py# Realistic oncology target and clinical drug seeder
├── tests/                   # Pytest automated test suite (24 unit and integration tests)
├── .env.example             # Example environment variables
├── pyproject.toml           # Project packaging & pytest configuration
└── requirements.txt         # Strictly pinned production dependencies
```

---

## 📄 License
Commercial oncology discovery platform foundation. All rights reserved.
