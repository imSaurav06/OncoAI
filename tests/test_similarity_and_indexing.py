"""
Unit Tests for Molecular Similarity Search and Fingerprint Indexing.
"""
from rdkit import Chem
from app.chemistry.fingerprints import generate_morgan_fingerprint, hex_to_fingerprint
from app.indexing.similarity import FingerprintIndex


def test_fingerprint_indexing_and_search():
    index = FingerprintIndex()

    # Create fingerprints for benzene, toluene, and ethanol
    mols = {
        "CMP_BENZENE": "c1ccccc1",
        "CMP_TOLUENE": "Cc1ccccc1",
        "CMP_ETHANOL": "CCO",
    }

    for cid, smi in mols.items():
        mol = Chem.MolFromSmiles(smi)
        _, hex_str, _ = generate_morgan_fingerprint(mol)
        index.index_compound(cid, hex_str)

    assert index.size() == 3

    # Query with benzene
    q_mol = Chem.MolFromSmiles("c1ccccc1")
    q_fp, _, _ = generate_morgan_fingerprint(q_mol)

    results = index.search_similar(q_fp, threshold=0.25, limit=10)
    assert len(results) >= 2

    # Benzene self-match must be highest (1.0)
    top_cid, top_score = results[0]
    assert top_cid == "CMP_BENZENE"
    assert top_score == 1.0

    # Toluene should have high similarity
    cids = [r[0] for r in results]
    assert "CMP_TOLUENE" in cids


def test_popcount_bounding_filters_distant_molecules():
    index = FingerprintIndex()

    # Small molecule (water/ethanol)
    mol_small = Chem.MolFromSmiles("CCO")
    _, hex_small, _ = generate_morgan_fingerprint(mol_small)
    index.index_compound("CMP_SMALL", hex_small)

    # Large complex natural product/macrocycle
    mol_large = Chem.MolFromSmiles("COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1")
    q_fp, _, _ = generate_morgan_fingerprint(mol_large)

    # High threshold (0.85) should immediately bound out the small molecule
    results = index.search_similar(q_fp, threshold=0.85)
    assert len(results) == 0
