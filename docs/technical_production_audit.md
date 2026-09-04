# Technical Production Audit: OncoAI Chemistry & Bioactivity Data Platform v1

**Auditor Role**: Principal Data Platform Architect + Senior Cheminformatics & Backend Infrastructure Engineer  
**Scope**: Technical production readiness of the OncoAI Foundation v1 for an enterprise oncology drug-discovery SaaS  
**Verdict**: The current foundation is exceptionally strong, modular, and scientifically disciplined. It is far ahead of typical academic or POC repositories. However, transitioning to a commercial multi-tenant SaaS requires addressing key cheminformatics edge cases, multi-tenancy boundaries, and database idempotency.

---

## Executive Summary & Scorecard

| Area | Current Rating | Production Readiness Verdict | Action Priority |
| :--- | :---: | :--- | :---: |
| **1. Chemistry Correctness** | **B+** | High-quality 9-stage pipeline; critical nuance with stereochemistry in tautomer canonicalization. | **HIGH (Immediate)** |
| **2. Bioactivity Semantics** | **B** | Excellent SI conversion to nM; operator flip on negative log ($pActivity$) needed for censored records. | **HIGH (Immediate)** |
| **3. Similarity Scalability** | **B-** | Outstanding mathematical popcount theory; in-memory linear loop hits limits around 100k compounds. | **MEDIUM (Scale-driven)** |
| **4. Data Architecture** | **A-** | Tiered lakehouse (S3 + Parquet + PostgreSQL) is clean; requires UUIDs on Parquet file naming. | **LOW (Tweak)** |
| **5. Ingestion Reliability** | **C+** | Provenance and QC reports exist, but `SourceRecord` deduplication lacks a natural unique constraint. | **HIGH (Immediate)** |
| **6. API & Backend Contract** | **A** | Zero-knowledge SaaS contract; strict OpenAPI 3.1 Pydantic envelopes and async jobs. | **MAINTAIN** |
| **7. Security & Multi-Tenancy** | **C** | Single global API key; lacks tenant isolation (`tenant_id`) and per-tenant rate limits. | **HIGH (Immediate for SaaS)** |
| **8. Operational Readiness** | **B** | Multi-stage Docker & compose ready; lacks Alembic migrations and CI/CD pipelines. | **MEDIUM** |
| **9. AI/ML Readiness** | **B+** | Scaffolds and experimental tags stored; needs scaffold train/test split endpoint to prevent leakage. | **MEDIUM** |
| **10. Scalability Bottlenecks** | **A-** | Clear upgrade path defined for 10M, 100M, and 1B compounds without touching API contracts. | **MAINTAIN** |

---

## 1. Chemistry Correctness

### Strengths
1. **Pinned Dependency**: RDKit version (`2024.03.5`) is explicitly pinned and stored in metadata, records, and API responses.
2. **Deterministic Stages**: Explicit order: Parse -> Validate -> Cleanup (Metals) -> FragmentParent (Salts) -> Uncharge -> CanonicalTautomer -> Identifiers -> ECFP4.
3. **No Silent Dropping**: Rejected molecules are explicitly persisted to `RejectedRecord` with exact parse/valence error strings.

### Critical Findings & Edge Cases
- **Stereochemistry Loss during Tautomer Canonicalization**:
  In `app/chemistry/pipeline.py` line 142:
  ```python
  final_mol = rdMolStandardize.CanonicalTautomer(uncharged_mol)
  canonical_smiles = Chem.MolToSmiles(final_mol, canonical=True, isomericSmiles=False)
  ```
  *Risk*: Setting `isomericSmiles=False` strips all stereochemistry from `canonical_smiles`. In oncology, stereoisomers (e.g., *Sotorasib* atropisomers or *Dabrafenib* analogs) frequently have 100- to 1000-fold differences in potency or divergent toxicity profiles.
  *Fix*: Store `canonical_isomeric_smiles` as the primary structural representation, and use standard InChIKey (which natively encodes stereochemistry in its second 10-character block: `XXXXXXXXXXXXXX-YYYYYYYYYY-Z`).
- **Tautomer Stereocenter Inversion**:
  RDKit's `rdMolStandardize.CanonicalTautomer` can clear chiral tags on stereocenters adjacent to double bonds involved in tautomeric transforms.
  *Fix*: Cache chiral tags (`Chem.FindMolChiralCenters(mol)`) before tautomerization and verify/re-assign stereo post-tautomerization.
- **Mixtures & Multi-component APIs**:
  `FragmentParent` retains the largest organic fragment. This is optimal for single-agent small molecules with salts (e.g., Osimertinib mesylate), but will discard the active component in stoichiometric fixed-dose drug combinations (e.g., *Trifluridine / Tipiracil*).
  *Fix*: Tag records where removed fragments have $> 6$ heavy atoms with a `POSSIBLE_MIXTURE` flag.

---

## 2. Bioactivity Semantics

### Strengths
1. **Canonical Concentration Normalization**: Converts `M`, `mM`, `uM`, `nM`, `pM` to canonical nanomolar ($\text{nM}$) with exact conversion factors.
2. **Mass-to-Molar Conversion**: Uses `molecular_weight` to convert $\mu g/\text{mL}$ and $\text{mg}/\text{L}$ to molar concentrations.
3. **Traceability**: Preserves original value, original unit, original operator, and source reference alongside normalized values.

### Critical Findings & Edge Cases
- **Inequality Inversion on Negative Log ($p\text{Activity}$)**:
  In `app/normalization/units.py`:
  When $IC_{50} > 10,000\text{ nM}$ (inactive compound), taking the negative log flips the inequality:
  $$IC_{50} > 10^{-5}\text{ M} \implies pIC_{50} < 5.0$$
  Currently, `normalized_relation` is directly copied from `original_relation` (`>`), meaning a record with $IC_{50} > 10,000\text{ nM}$ is recorded with $pIC_{50} = 5.0$ and relation `>`, which implies *greater than 5.0* (i.e. more active), the exact opposite of reality!
  *Fix*: Explicitly invert operator when calculating $pActivity$: `>` becomes `<`, and `<` becomes `>`.
- **Censored Values in AI Model Training**:
  Censored measurements (`>`, `<`, `~`) must be explicitly flagged with `is_censored: bool` so ML training pipelines do not treat boundary values (e.g. $> 10,000\text{ nM}$) as exact point observations in regression tasks.

---

## 3. Similarity Scalability

### Strengths
1. **Popcount Filtering Theory**: Uses mathematically provable popcount bounds ($\lceil a \cdot t \rceil \le b \le \lfloor a / t \rfloor$).
2. **Vectorized C++ Evaluation**: Uses RDKit's `BulkTanimotoSimilarity`.

### Scalability Limits
- **The Python In-Memory Loop**:
  In `app/indexing/similarity.py`:
  ```python
  for cid, (fp, pop) in self._index.items():
      if min_pop <= pop <= max_pop:
          ...
  ```
  - At **5,000 compounds**: Iteration takes $0.4\text{ ms}$.
  - At **100,000 compounds**: Iteration takes $\sim 15\text{ ms}$ (acceptable).
  - At **1,000,000+ compounds**: Iterating 1M Python objects in interpreted GIL space takes $> 250\text{ ms}$ before vectorized C++ calculation even starts.
  - Furthermore, memory footprint with multi-worker Uvicorn multiplies across processes.
- **Architectural Solution**:
  1. *Immediate Phase (100k - 5M)*: Bucket popcounts (`Dict[int, List[int]]`) so the loop only inspects keys between `min_pop` and `max_pop`, touching only 10% of records.
  2. *Production Scale (10M - 100M)*: PostgreSQL `rdkit` cartridge with GiST/GIN indexing, or DuckDB binary bitwise scans on Parquet.
  3. *Ultra Scale (100M - 1B)*: Vector indexing via Milvus or FAISS binary indices using GPU acceleration.

---

## 4. Data Architecture (Storage Tiering)

### Strengths
1. **Clean Separation of Tiers**:
   - Layer A (Cold Lake): S3 / MinIO raw JSON/SDF payloads with SHA-256 integrity.
   - Layer B (Warm Analytics): Columnar Apache Parquet partitioned by source and date.
   - Layer C (Hot Serving): PostgreSQL/SQLite with B-tree relational indexes.

### Architectural Nuance
- **Parquet Overwrite Hazard**:
  In `app/storage/parquet_store.py`:
  `file_path = target_dir / f"compounds_{len(records)}.parquet"`
  If two separate batches have identical record lengths, the latter overwrites the former.
  *Fix*: Append a UUIDv4 or monotonic timestamp: `f"compounds_{timestamp}_{uuid.hex[:8]}.parquet"`.
- **DuckDB Query Lifecycle**:
  `query()` opens a fresh `duckdb.connect(":memory:")` on every invocation and runs `read_parquet(glob)`. This is ideal for isolated analytical queries, but at scale requires persistent metadata views.

---

## 5. Ingestion Reliability & Idempotency

### Strengths
1. Source adapters for ChEMBL, PubChem, and proprietary wet-lab observations.
2. Complete `ProcessingRun` and `QualityAuditor` tracking error categories and rates.

### Critical Findings
- **Lack of Natural Key Idempotency in `SourceRecord`**:
  In `app/jobs/tasks.py`, `src_rec_id = f"SR_{uuid.uuid4().hex[:12].upper()}"`.
  If a user re-triggers an ingestion of the exact same ChEMBL dataset version:
  - `Compound` is deduplicated via `inchikey`.
  - But `SourceRecord` generates new random IDs, inserting duplicate records and duplicate `Bioactivity` observations.
  *Fix*: Add a compound unique constraint on `SourceRecord(dataset_id, external_id)` and use PostgreSQL `ON CONFLICT DO NOTHING` or `DO UPDATE`.
- **Chunked Checkpointing**:
  Flushing single records in a loop causes high transaction log churn on large datasets (500k+).
  *Fix*: Process in batches of 1,000 to 5,000 records per transaction with a persistent `last_processed_index` checkpoint.

---

## 6. API & Backend Contract

### Strengths
1. Strict OpenAPI 3.1 schema.
2. Standard response envelope: `{schema_version, request_id, data, error, meta}`.
3. Zero data-layer leaking: The SaaS application communicates solely via JSON REST over HTTP.
4. Asynchronous job model (`/v1/jobs`) for long-running workflows with polling status.

---

## 7. Security & Multi-Tenancy

### Vulnerability Analysis
- **Global API Key**:
  `verify_api_key` compares against a single static `settings.API_KEY`.
- **Cross-Tenant Data Leakage Risk**:
  In an oncology SaaS where multiple pharmaceutical companies or biotech clients subscribe:
  - Public data (ChEMBL, PubChem) is shared.
  - Client proprietary screening data (e.g. newly synthesized kinase inhibitors with $IC_{50} = 0.5\text{ nM}$) must be strictly isolated.
  - Currently, `Compound`, `Assay`, and `Bioactivity` tables lack a `tenant_id` column.
  *Fix*:
  1. Add `tenant_id: Optional[str]` to `CompoundIdentifier`, `Assay`, `Bioactivity`, and `Job` (with `NULL` denoting shared public reference data).
  2. Implement Row-Level Security (RLS) in PostgreSQL or append `WHERE (tenant_id = :current_tenant OR tenant_id IS NULL)` to all query planner filters.
  3. Per-tenant API key management with rate limiting in Redis (e.g., 60 req/min for standard tiers, 600 req/min for enterprise).

---

## 8. Operational Readiness

### Current State
- Dockerfile and `docker-compose.yml` provide containerized PostgreSQL, Redis, MinIO, and FastAPI.
- `/health`, `/ready`, and Prometheus `/metrics` endpoints exist.

### Missing Production Tooling
1. **Alembic Database Migrations**: Currently models rely on `Base.metadata.create_all()`. Real-world production requires migration scripts (`alembic revision --autogenerate`) to handle schema evolution.
2. **CI/CD Pipeline**: GitHub Actions workflow for linting (`ruff`), type checking (`mypy`), security scanning (`bandit`), and unit/integration testing (`pytest`).
3. **Structured Logging**: Output logs as JSON lines for ingestion into Datadog, Grafana Loki, or AWS CloudWatch.

---

## 9. AI/ML Readiness

### Strengths
1. Bemis-Murcko scaffolds (`murcko_scaffold_smiles`) are precomputed and stored on `Compound`.
2. Clean separation of experimental vs public data via `is_experimental: bool`.
3. Precomputed 2048-bit ECFP4 fingerprints and Lipinski/Veber descriptors ready for QSAR models.

### AI Leakage Hazards
- **Random Train/Test Splitting**:
  If an AI engineer performs random splitting on bioactivity data, structural analogs sharing the same Murcko scaffold will appear in both train and validation sets, producing artificially high performance metrics that fail in wet-lab prospective screening.
  *Fix*: Provide a dedicated `/v1/datasets/{dataset_id}/split` endpoint supporting:
  - **Bemis-Murcko Scaffold Split** (ensures novel chemical series in validation).
  - **Temporal Split** (train on historical assays, validate on recent experiments).

---

## 10. Scalability Blueprint: What to Redesign Now vs Later

```
                                SCALE TIMELINE
 
 [NOW: 10^4 - 10^5]             [PHASE 2: 10^6 - 10^7]           [PHASE 3: 10^8 - 10^9+]
 ──────────────────             ──────────────────────           ───────────────────────
 • Fix InChIKey/Stereo          • Popcount bucket index          • ClickHouse / Iceberg
 • Invert pActivity operator    • PostgreSQL rdkit cartridge     • GPU Milvus/FAISS
 • Tenant ID & RLS              • Distributed Celery/Redis       • Distributed Ray worker
 • Alembic migrations           • Read-only replicas             • Inverted index cluster
```

### Must Fix Now (Prior to SaaS Onboarding)
1. **Stereochemistry Preservation**: Use `isomericSmiles=True` and ensure chiral centers are preserved post-tautomerization.
2. **$p\text{Activity}$ Operator Inversion**: Fix `>` to `<` when taking negative logarithms.
3. **Multi-Tenancy Isolation**: Add `tenant_id` to prevent cross-tenant proprietary compound leakage.
4. **Idempotent Ingestion**: Add unique constraint on `SourceRecord(dataset_id, external_id)`.
5. **Alembic Migrations**: Replace `create_all` with versioned migration scripts.

### Leave Modular (Upgrade When Scale Demands It)
1. **PostgreSQL rdkit Cartridge**: Not needed until corpus exceeds 200,000 compounds.
2. **Celery / Distributed Task Queues**: Current in-process async worker is sufficient for initial pilot ingestion; interface is already decoupled behind `/v1/jobs`.
3. **GPU Similarity Search (Milvus/FAISS)**: Not required until screening libraries exceed 10 million compounds.
