# Scaling Strategy: From 100K to 1 Billion Compounds

## 1. Empirical Capacity Benchmarks (Current Baseline)
Empirical tests conducted on local CPU baseline hardware yielded the following metrics:
- **RDKit Standardization Pipeline**: ~27 molecules/sec per single worker core (~37.4 ms/mol).
- **Full Physicochemical Analysis & Fingerprint Generation**: ~20 molecules/sec per core (~49 ms/mol).
- **Popcount-Bounded Similarity Search (5,000 corpus)**: **6.81 ms median latency**, **10.05 ms P95 latency**.
- **Exact B-tree InChIKey Lookup**: **3.84 ms median latency**, **38.74 ms P95 latency**.
- **Faceted 4-Table Joined Bioactivity Query**: **17.75 ms median latency**, **32.89 ms P95 latency**.

---

## 2. Bottleneck Analysis & Horizontal Evolution

### Scale Tier 1: 10^5 Compounds (100,000)
- **Bottlenecks**: Negligible. Memory footprint is under 200MB.
- **Serving**: Single PostgreSQL instance + local/S3 raw data lake.
- **Similarity**: In-memory popcount filtering + vectorized bitwise Tanimoto scan finishes in under 15 ms.

### Scale Tier 2: 10^6 - 10^7 Compounds (1M – 10M)
- **Bottlenecks**: Linear in-memory scanning of 10M Morgan bit vectors begins exceeding single-process RAM (~2.5 GB for raw binary fingerprints) and CPU cache bandwidth.
- **Evolution**:
  1. Enable PostgreSQL `rdkit` extension cartridge with Generalized Inverted Index (GIN) or Signature trees (`fps` indexing).
  2. Transition bulk analytical dataset queries to Apache Arrow/DuckDB querying partitioned Parquet files directly on S3.
  3. Distribute background ingestion across multi-core Celery or RQ worker pools.
- **API Impact**: Zero. REST endpoints and schemas remain completely unchanged.

### Scale Tier 3: 10^8 - 10^9+ Compounds (100M – 1 Billion)
- **Bottlenecks**: Relational databases cannot cost-effectively store 1 billion compound graphs and billions of bioactivity datapoints with low latency.
- **Evolution**:
  1. **Hot Tier**: Distributed key-value stores (e.g., Redis Cluster or DynamoDB) for instant InChIKey -> Compound metadata lookups.
  2. **Warm Tier**: Apache Iceberg or Delta Lake on AWS S3 with ClickHouse or DuckDB cluster for analytical queries.
  3. **Similarity Engine**: Distributed inverted index clusters (or GPU-accelerated FAISS / Milvus binary vector index) using Hierarchical Navigable Small World (HNSW) or coarse quantization inverted file (IVF) indexes.
- **API Impact**: Zero. All queries route through `app/indexing/query_planner.py` which abstracts the underlying search engine from the SaaS.
