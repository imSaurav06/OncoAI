# Scientific Provenance & Traceability Specification

## 1. Traceability Mandate
In oncology drug discovery and pharmaceutical AI development, black-box data pipelines are scientifically unacceptable. Every scientific measurement, compound structure, and bioactivity endpoint must answer:
> **"Where did this number come from, which version of RDKit normalized it, what was the original text in the source literature, and was it an experimental or public observation?"**

---

## 2. Provenance Chain Architecture

```
Raw Provider / Literature / Notebook
  │
  ▼
[Source Record]
  ├── source: 'ChEMBL' / 'In-House Wet Lab'
  ├── source_record_id: 'CHEMBL3988824'
  ├── raw_payload_hash: '3f7a8b... (SHA-256)'
  ├── acquisition_date: '2026-09-04'
  │
  ▼
[Processing Run]
  ├── pipeline_version: 'chem-pipeline-1.0'
  ├── rdkit_version: '2024.03.5'
  ├── normalization_version: 'units-norm-1.0'
  ├── execution_timestamp: '2026-09-04T11:15:30Z'
  │
  ▼
[Provenance Entity]
  ├── source_record_id -> SourceRecord
  ├── processing_run_id -> ProcessingRun
  ├── normalization_notes: 'Multiplied uM by 1000 to reach canonical nM'
  │
  ▼
[Bioactivity & Compound Records]
  ├── original_value: 0.0008, original_unit: 'uM'
  ├── activity_value_nm: 0.8, pactivity: 9.097
  ├── provenance_id: UUID
```

---

## 3. Separation of Public Observations and Experimental Measurements
The data platform explicitly tags assays and bioactivity measurements with `is_experimental: bool`:
- **`is_experimental = False`**: Public data extracted from ChEMBL, PubChem, BindingDB, patents, or scientific literature.
- **`is_experimental = True`**: Proprietary in-house screening measurements produced in the wet-lab.

This ensures machine learning training datasets can cleanly filter or weigh internal observations versus heterogeneous public data points.
