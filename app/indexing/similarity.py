"""
Fast Molecular Similarity Search Engine (Sections 12 & 13 of architecture).
Implements pre-filtered bitwise Tanimoto similarity over 2048-bit Morgan fingerprints
using popcount bounding and vectorized RDKit BulkTanimotoSimilarity.
"""
from typing import List, Tuple, Dict, Optional
import math
from rdkit import Chem
from rdkit.Chem import DataStructs

from app.chemistry.fingerprints import hex_to_fingerprint, bulk_tanimoto_similarity


class FingerprintIndex:
    """
    In-memory / Warm-tier Fingerprint Index for low-latency similarity queries.
    Maintains precomputed popcounts for candidate bounding.
    """

    def __init__(self):
        # Maps compound_id -> (ExplicitBitVect, popcount)
        self._index: Dict[str, Tuple[DataStructs.ExplicitBitVect, int]] = {}

    def index_compound(self, compound_id: str, fp_hex: str) -> None:
        """Adds a compound's precomputed fingerprint to the similarity index."""
        fp = hex_to_fingerprint(fp_hex)
        popcount = int(fp.GetNumOnBits())
        self._index[compound_id] = (fp, popcount)

    def bulk_index(self, records: List[Tuple[str, str]]) -> None:
        """Bulk loads (compound_id, fp_hex) tuples into the index."""
        for cid, hex_str in records:
            self.index_compound(cid, hex_str)

    def size(self) -> int:
        return len(self._index)

    def clear(self) -> None:
        self._index.clear()

    def search_similar(
        self,
        query_fp: DataStructs.ExplicitBitVect,
        threshold: float = 0.8,
        limit: int = 50,
        candidate_ids: Optional[set] = None
    ) -> List[Tuple[str, float]]:
        """
        Executes fast candidate-bounded similarity search.
        Uses popcount bounds:
          min_popcount = ceil(threshold * query_popcount)
          max_popcount = floor(query_popcount / threshold)
        """
        if not self._index:
            return []

        query_pop = int(query_fp.GetNumOnBits())
        if query_pop == 0:
            return []

        # Mathematical popcount bounds for Tanimoto >= threshold
        min_pop = int(math.ceil(threshold * query_pop))
        max_pop = int(math.floor(query_pop / threshold))

        # Filter candidates by popcount and optional pre-filter ID set
        filtered_cids: List[str] = []
        target_fps: List[DataStructs.ExplicitBitVect] = []

        for cid, (fp, pop) in self._index.items():
            if candidate_ids is not None and cid not in candidate_ids:
                continue
            if min_pop <= pop <= max_pop:
                filtered_cids.append(cid)
                target_fps.append(fp)

        if not target_fps:
            return []

        # Vectorized bulk Tanimoto computation in C++
        scores = bulk_tanimoto_similarity(query_fp, target_fps)

        # Pair results and filter by threshold
        results: List[Tuple[str, float]] = []
        for cid, score in zip(filtered_cids, scores):
            if score >= threshold:
                results.append((cid, round(score, 4)))

        # Sort descending by similarity score, take top-K
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]


# Global fingerprint index instance
similarity_index = FingerprintIndex()
