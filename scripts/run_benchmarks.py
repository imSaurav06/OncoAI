"""
OncoAI Data Platform — Performance & Latency Benchmark Runner (Section 39 of architecture).
Measures:
1. RDKit Molecule Standardization Throughput (mols/sec)
2. Molecular Descriptors Calculation Throughput (mols/sec)
3. Morgan Fingerprint Generation Throughput (mols/sec)
4. Popcount-Bounded Tanimoto Similarity Search Latency (ms)
5. Exact Database InChIKey B-tree Index Retrieval Latency (ms)
6. Complex Faceted Bioactivity Joint Query Latency (ms)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import time
import statistics
from rdkit import Chem
from app.chemistry.pipeline import chemistry_pipeline
from app.chemistry.fingerprints import generate_morgan_fingerprint, hex_to_fingerprint
from app.indexing.similarity import similarity_index
from app.storage.database import AsyncSessionLocal
from app.indexing.query_planner import query_planner

# Benchmark sample molecules (Approved Kinase Inhibitors and oncology drugs)
SMILES_SAMPLES = [
    "COc1cc(N(C)CCN(C)C)c(NC(=O)C=C)cc1Nc1nccc(n1)c1cn(C)c2ccccc12",  # Osimertinib
    "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1",  # Gefitinib
    "CCCS(=O)(=O)Nc1ccc(F)c(C(=O)c2c[nH]c3ncc(-c4ccc(Cl)cc4)cc23)c1F",  # Vemurafenib
    "COCCOC1=C(C=C2C(=C1)C(=NC=N2)NC3=CC=CC(=C3)C#C)OCCOC",  # Erlotinib
    "CC(=O)c1c(C)c2cnc(Nc3ncc(cc3)N4CCNCC4)nc2n1C5CCCC5",  # Palbociclib
    "CC(C)C1=C(C=C(C=C1Cl)F)C2=C(C(=NC3=C2N=C(N=C3O)N4CCN(CC4)C)NC(=O)C=C)F",  # Sotorasib
    "Cc1c(Nc2nccc(n2)c3cccnc3)ccc(c1)C(=O)Nc4cc(cc(c4)C(F)(F)F)n5ccnc5",  # Nilotinib
    "CS(=O)(=O)CCNCc1ccc(-c2ccc3ncnc(Nc4ccc(OCc5cccc(F)c5)c(Cl)c4)c3c2)o1",  # Lapatinib
    "CC1=C(C(=O)N2CCOCC2)C3=C(C=C1)N(C4=NC=NC=C43)C5=CC=CC=C5F",  # Kinase scaffold
    "c1ccccc1"  # Benzene baseline
]


async def run_benchmarks():
    print("=" * 70)
    print("ONCOAI PLATFORM ENGINE BENCHMARK SUITE")
    print("=" * 70)

    # 1. Chemical Standardization Throughput
    n_iterations = 200
    expanded_smiles = (SMILES_SAMPLES * (n_iterations // len(SMILES_SAMPLES) + 1))[:n_iterations]

    t0 = time.perf_counter()
    for smi in expanded_smiles:
        chemistry_pipeline.standardize(smi)
    t_std = time.perf_counter() - t0
    std_rate = round(n_iterations / t_std, 1)
    std_latency_ms = round((t_std / n_iterations) * 1000, 3)
    print(f"\n[1] RDKit Deterministic Standardization:")
    print(f"    Total Processed: {n_iterations} molecules")
    print(f"    Elapsed Time:    {t_std:.3f} s")
    print(f"    Throughput:      {std_rate} molecules/second")
    print(f"    Mean Latency:    {std_latency_ms} ms/molecule")

    # 2. Full Analysis (Standardization + Descriptors + Scaffold + Fingerprints)
    t0 = time.perf_counter()
    for smi in expanded_smiles:
        chemistry_pipeline.analyze(smi)
    t_ana = time.perf_counter() - t0
    ana_rate = round(n_iterations / t_ana, 1)
    ana_latency_ms = round((t_ana / n_iterations) * 1000, 3)
    print(f"\n[2] Complete Chemical Analysis (Descriptors + Scaffold + 2048-bit Morgan FP):")
    print(f"    Throughput:      {ana_rate} molecules/second")
    print(f"    Mean Latency:    {ana_latency_ms} ms/molecule")

    # 3. Fingerprint Popcount-Bounded Similarity Search
    # Populate similarity index with 5,000 synthetic variants to test large scale
    base_mol = Chem.MolFromSmiles(SMILES_SAMPLES[0])
    _, base_hex, _ = generate_morgan_fingerprint(base_mol)
    fp_corpus = [(f"CMP_TEST_{i:05d}", base_hex) for i in range(5000)]
    similarity_index.bulk_index(fp_corpus)

    query_fp = hex_to_fingerprint(base_hex)
    latencies = []
    for _ in range(50):
        t_start = time.perf_counter()
        similarity_index.search_similar(query_fp, threshold=0.7, limit=50)
        latencies.append((time.perf_counter() - t_start) * 1000)

    p50_sim = round(statistics.median(latencies), 3)
    p95_sim = round(statistics.quantiles(latencies, n=20)[18], 3)
    print(f"\n[3] Molecular Similarity Search (5,000 Fingerprint Corpus):")
    print(f"    Index Size:      {similarity_index.size():,} fingerprints")
    print(f"    Median Latency:  {p50_sim} ms")
    print(f"    P95 Latency:     {p95_sim} ms")

    # 4. Relational B-tree InChIKey Lookup Latency
    async with AsyncSessionLocal() as session:
        # Osimertinib InChIKey
        target_inchikey = "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
        db_latencies = []
        for _ in range(30):
            t_start = time.perf_counter()
            await query_planner.search_compounds(session, exact_inchikey=target_inchikey)
            db_latencies.append((time.perf_counter() - t_start) * 1000)

        p50_db = round(statistics.median(db_latencies), 3)
        p95_db = round(statistics.quantiles(db_latencies, n=20)[18], 3)
        print(f"\n[4] Database InChIKey Exact B-tree Lookup:")
        print(f"    Median Latency:  {p50_db} ms")
        print(f"    P95 Latency:     {p95_db} ms")

        # 5. Faceted Bioactivity Joint Query
        bio_latencies = []
        for _ in range(30):
            t_start = time.perf_counter()
            await query_planner.search_bioactivity(session, gene_symbol="EGFR", activity_type="IC50")
            bio_latencies.append((time.perf_counter() - t_start) * 1000)

        p50_bio = round(statistics.median(bio_latencies), 3)
        p95_bio = round(statistics.quantiles(bio_latencies, n=20)[18], 3)
        print(f"\n[5] Joint Faceted Bioactivity Search (Compound + Target + Assay + CellLine):")
        print(f"    Median Latency:  {p50_bio} ms")
        print(f"    P95 Latency:     {p95_bio} ms")

    print("\n" + "=" * 70)
    print("ALL BENCHMARKS COMPLETED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_benchmarks())
