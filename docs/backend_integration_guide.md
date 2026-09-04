# Backend & SaaS Integration Guide

## 1. Quick Integration Overview
The OncoAI Chemistry & Bioactivity Data Platform exposes a clean, versioned REST API (`/v1`) designed for zero-knowledge SaaS consumption. The SaaS frontend and AI backend never need direct database access, object store credentials, or chemical parsing libraries.

### Base Configuration
- **Base URL**: `http://localhost:8000/v1` (Production: `https://data.oncoai.internal/v1`)
- **Interactive OpenAPI Documentation**: `http://localhost:8000/docs`
- **OpenAPI JSON Contract**: `http://localhost:8000/openapi.json`
- **Authentication Header**: `X-API-Key: your_secure_service_token`

---

## 2. Standard Response Envelope
All endpoints return responses wrapped in a consistent Pydantic JSON envelope:

```json
{
  "schema_version": "1.0",
  "request_id": "7b79d2b2-6cb1-4475-ae90-c0be8399fe40",
  "data": { ... },
  "error": null,
  "meta": {
    "total_count": 1,
    "page": 1,
    "page_size": 50,
    "has_more": false,
    "execution_time_ms": 7.45
  }
}
```

---

## 3. Core Endpoint Recipes

### Recipe 1: Molecular Structure Standardization
Transform raw chemist or vendor input into canonical, salt-stripped representation:

```bash
curl -X POST "http://localhost:8000/v1/compounds/standardize" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: oncoai_dev_secret_key_change_in_prod" \
  -d '{"smiles": "CC(=O)Oc1ccccc1C(=O)O.CS(=O)(=O)O"}'
```

### Recipe 2: Chemical Similarity Search
Retrieve structurally similar oncology compounds using ECFP4 Tanimoto similarity:

```bash
curl -X POST "http://localhost:8000/v1/compounds/similarity" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: oncoai_dev_secret_key_change_in_prod" \
  -d '{
    "smiles": "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1",
    "threshold": 0.70,
    "limit": 25
  }'
```

### Recipe 3: Multi-Faceted Bioactivity Search
Find all nanomolar bioactivities for a specific target and activity type:

```bash
curl -X POST "http://localhost:8000/v1/bioactivity/search" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: oncoai_dev_secret_key_change_in_prod" \
  -d '{
    "target_name": "EGFR",
    "activity_type": "IC50",
    "max_activity_nm": 100.0,
    "page": 1,
    "page_size": 20
  }'
```

### Recipe 4: Asynchronous Job Lifecycle
For long-running ingestion or batch standardization:

1. Submit job:
```bash
POST /v1/jobs
{"job_type": "INGEST_CHEMBL", "parameters": {"target": "EGFR"}}
```
Response returns `{"job_id": "job_01h...", "status": "QUEUED"}`.

2. Poll status:
```bash
GET /v1/jobs/job_01h...
```
Returns current state (`QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`) and execution telemetry.
