"""
Unit Tests for RDKit Chemistry Pipeline (Determinism, Standardization, Descriptors, Fingerprints).
"""
import pytest
from app.chemistry.pipeline import (
    chemistry_pipeline,
    InvalidStructureError,
    SanitizationError,
)
from app.chemistry.fingerprints import hex_to_fingerprint, calculate_tanimoto_similarity


def test_standardize_basic_molecule():
    res = chemistry_pipeline.standardize("CCO")
    assert res.canonical_smiles == "CCO"
    assert res.inchikey == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
    assert not res.salt_removed
    assert not res.charge_neutralized


def test_salt_stripping_osimertinib_mesylate():
    # Osimertinib + Methanesulfonic acid (mesylate salt)
    smiles_with_salt = "COc1cc(N(C)CCN(C)C)c(NC(=O)C=C)cc1Nc1nccc(n1)c1cn(C)c2ccccc12.CS(=O)(=O)O"
    res = chemistry_pipeline.standardize(smiles_with_salt)
    assert res.salt_removed is True
    assert res.salt_fragment_smiles == "CS(=O)(=O)O"
    assert "CS(=O)(=O)O" not in res.canonical_smiles


def test_charge_neutralization():
    # Acetate anion -> Acetic acid
    acetate_smiles = "CC(=O)[O-]"
    res = chemistry_pipeline.standardize(acetate_smiles)
    assert res.canonical_smiles == "CC(=O)O"
    assert res.charge_neutralized is True


def test_analyze_descriptors_and_fingerprints():
    res = chemistry_pipeline.analyze("c1ccccc1O")  # Phenol
    desc = res.descriptors
    assert desc["molecular_formula"] == "C6H6O"
    assert desc["heavy_atom_count"] == 7
    assert desc["num_aromatic_rings"] == 1
    assert desc["hbd"] == 1
    assert desc["hba"] == 1
    assert res.fingerprint_hex is not None
    assert res.fingerprint_on_bits > 0


def test_invalid_smiles_error_handling():
    with pytest.raises(InvalidStructureError):
        chemistry_pipeline.standardize("INVALID_NOT_A_SMILES_STRING")


def test_empty_smiles_error_handling():
    with pytest.raises(InvalidStructureError):
        chemistry_pipeline.standardize("")


def test_fingerprint_tanimoto_self_similarity():
    res = chemistry_pipeline.analyze("CCO")
    fp1 = hex_to_fingerprint(res.fingerprint_hex)
    fp2 = hex_to_fingerprint(res.fingerprint_hex)
    similarity = calculate_tanimoto_similarity(fp1, fp2)
    assert similarity == 1.0


def test_stereochemistry_preservation_enantiomers():
    """Verify that enantiomers retain their distinct stereocenters, isomeric SMILES, and InChIKeys."""
    l_alanine = "C[C@@H](N)C(=O)O"
    d_alanine = "C[C@H](N)C(=O)O"
    
    l_res = chemistry_pipeline.standardize(l_alanine)
    d_res = chemistry_pipeline.standardize(d_alanine)
    
    # Stereochemistry is preserved in canonical_smiles
    assert "@" in l_res.canonical_smiles
    assert "@" in d_res.canonical_smiles
    assert l_res.canonical_smiles != d_res.canonical_smiles
    
    # Stereochemistry flags are true
    assert l_res.has_stereochemistry is True
    assert d_res.has_stereochemistry is True
    
    # InChIKeys distinguish enantiomers in the second block
    assert l_res.inchikey != d_res.inchikey
    assert l_res.inchikey == "QNAYBMKLOCPYGJ-UWTATZPHSA-N"
    assert d_res.inchikey == "QNAYBMKLOCPYGJ-REOHCLBHSA-N"
    
    # Achiral compound should have has_stereochemistry=False
    achiral_res = chemistry_pipeline.standardize("CCO")
    assert achiral_res.has_stereochemistry is False
