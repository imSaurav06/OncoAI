# Indexing & Query Strategy

## 1. Multi-Tiered Index Architecture

Chemistry queries require different data structures than standard text or relational searches:

| Query Type | Query Objective | Index Mechanism | Target Latency |
| :--- | :--- | :--- | :--- |
| **Exact Compound Match** | Lookup by InChIKey or Canonical SMILES | PostgreSQL / SQLite B-tree index on `inchikey` | < 5 ms |
| **Faceted Bioactivity Filter** | Find inhibitors of target X in cell line Y with $IC_{50} < 100\text{ nM}$ | Multi-column B-tree indexes + join optimization | < 25 ms |
| **Molecular Similarity** | Find analogs with Tanimoto similarity $\ge T$ | Popcount Bounds Filter + C++ Vectorized Tanimoto Scan | < 15 ms (up to 100k) |
| **Substructure Search** | Find molecules containing functional warhead | Fingerprint screen (screen-out filter) + RDKit subgraph isomorphism | < 50 ms |

---

## 2. Popcount-Bounded Chemical Similarity Filtering

Standard molecular similarity searches compute the Jaccard/Tanimoto coefficient between query fingerprint $Q$ and corpus fingerprint $C$:

$$T(A, B) = \frac{|A \cap B|}{|A \cup B|} = \frac{|A \cap B|}{|A| + |B| - |A \cap B|}$$

Because $|A \cap B| \le \min(|A|, |B|)$, a mathematical upper bound exists for the maximum possible Tanimoto similarity between any two bit-vectors based solely on their respective popcounts (the number of set bits):

$$T_{\max} = \frac{\min(|A|, |B|)}{\max(|A|, |B|)}$$

For a query molecule with popcount $a$ and a desired similarity threshold $t \in (0, 1]$, any candidate molecule with popcount $b$ must strictly satisfy:

$$\lceil a \cdot t \rceil \le b \le \lfloor a / t \rfloor$$

### Computational Impact:
- If a query molecule has $a = 60$ bits set, and $t = 0.85$:
  - $b_{\min} = \lceil 60 \times 0.85 \rceil = 51$
  - $b_{\max} = \lfloor 60 / 0.85 \rfloor = 70$
- **Result**: The index instantly prunes away **85% to 95%** of the database candidates using a fast integer B-tree range scan on `popcount BETWEEN 51 AND 70` before running any bitwise similarity calculations.
- Only the surviving 5-15% of candidates undergo the C++ vectorized bitwise AND popcount calculation.

---

## 3. Query Planner & Candidate Selection
The `QueryPlanner` (`app/indexing/query_planner.py`) coordinates multi-stage execution:
1. **Filter Planning**: Inspects query criteria (target, cell line, activity cutoff, popcount bounds).
2. **Candidate Retrieval**: Executes index-accelerated candidate retrieval in the hot serving store.
3. **Refinement**: Performs exact RDKit substructure matching or Tanimoto scoring on candidate set.
4. **Top-K Ranking**: Ranks by similarity or pActivity and paginates response.
