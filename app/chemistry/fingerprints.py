"""
Morgan / ECFP4 Fingerprint Generation and Bitwise Tanimoto Calculations.
Uses modern RDKit rdFingerprintGenerator (MorganGenerator).
"""
from typing import Tuple, List, Optional
from rdkit import Chem
from rdkit.Chem import DataStructs, rdFingerprintGenerator

DEFAULT_RADIUS = 2
DEFAULT_NBITS = 2048

# Reusable modern generator
_morgan_generator = rdFingerprintGenerator.GetMorganGenerator(radius=DEFAULT_RADIUS, fpSize=DEFAULT_NBITS)


def generate_morgan_fingerprint(
    mol: Chem.Mol, radius: int = DEFAULT_RADIUS, n_bits: int = DEFAULT_NBITS
) -> Tuple[DataStructs.ExplicitBitVect, str, int]:
    """
    Generates a fixed-length Morgan fingerprint (ECFP4 equivalent).
    Returns: (bit_vector, hex_encoded_string, on_bits_count)
    """
    if radius == DEFAULT_RADIUS and n_bits == DEFAULT_NBITS:
        fp = _morgan_generator.GetFingerprint(mol)
    else:
        gen = rdFingerprintGenerator.GetMorganGenerator(radius=radius, fpSize=n_bits)
        fp = gen.GetFingerprint(mol)

    fp_bytes = DataStructs.BitVectToBinaryText(fp)
    fp_hex = fp_bytes.hex()
    on_bits = int(fp.GetNumOnBits())
    return fp, fp_hex, on_bits


def hex_to_fingerprint(fp_hex: str) -> DataStructs.ExplicitBitVect:
    """Converts stored hex string back into RDKit ExplicitBitVect."""
    fp_bytes = bytes.fromhex(fp_hex)
    return DataStructs.CreateFromBinaryText(fp_bytes)


def calculate_tanimoto_similarity(fp1: DataStructs.ExplicitBitVect, fp2: DataStructs.ExplicitBitVect) -> float:
    """Calculates Tanimoto similarity coefficient between two fingerprints."""
    return float(DataStructs.TanimotoSimilarity(fp1, fp2))


def bulk_tanimoto_similarity(query_fp: DataStructs.ExplicitBitVect, target_fps: List[DataStructs.ExplicitBitVect]) -> List[float]:
    """Calculates bulk Tanimoto similarity scores using optimized RDKit C++ implementation."""
    return [float(s) for s in DataStructs.BulkTanimotoSimilarity(query_fp, target_fps)]
