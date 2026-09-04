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
    assert l_res.inchikey.split("-")[0] == d_res.inchikey.split("-")[0]  # Identical connectivity
    assert l_res.inchikey.split("-")[1] != d_res.inchikey.split("-")[1]  # Distinct stereo layer
    assert l_res.inchikey == "QNAYBMKLOCPYGJ-UWTATZPHSA-N"
    assert d_res.inchikey == "QNAYBMKLOCPYGJ-REOHCLBHSA-N"
    
    # Achiral compound should have has_stereochemistry=False
    achiral_res = chemistry_pipeline.standardize("CCO")
    assert achiral_res.has_stereochemistry is False


def test_stereochemistry_rs_drug_examples():
    """Verify chiral drug pairs (Thalidomide R/S and Ibuprofen S/R) retain stereochemistry."""
    thalidomide_s = "O=C1CC[C@@H](N2C(=O)c3ccccc3C2=O)C(=O)N1"
    thalidomide_r = "O=C1CC[C@H](N2C(=O)c3ccccc3C2=O)C(=O)N1"
    
    t_s_res = chemistry_pipeline.standardize(thalidomide_s)
    t_r_res = chemistry_pipeline.standardize(thalidomide_r)
    
    assert t_s_res.canonical_smiles != t_r_res.canonical_smiles
    assert t_s_res.has_stereochemistry is True
    assert t_r_res.has_stereochemistry is True
    assert t_s_res.inchikey.split("-")[0] == t_r_res.inchikey.split("-")[0]
    assert t_s_res.inchikey.split("-")[1] != t_r_res.inchikey.split("-")[1]
    
    ibuprofen_s = "CC(C)Cc1ccc([C@@H](C)C(=O)O)cc1"
    ibuprofen_r = "CC(C)Cc1ccc([C@H](C)C(=O)O)cc1"
    
    ib_s_res = chemistry_pipeline.standardize(ibuprofen_s)
    ib_r_res = chemistry_pipeline.standardize(ibuprofen_r)
    
    assert ib_s_res.canonical_smiles != ib_r_res.canonical_smiles
    assert ib_s_res.has_stereochemistry is True
    assert ib_r_res.has_stereochemistry is True
    assert ib_s_res.inchikey.split("-")[0] == ib_r_res.inchikey.split("-")[0]
    assert ib_s_res.inchikey.split("-")[1] != ib_r_res.inchikey.split("-")[1]


def test_stereochemistry_ez_alkene_isomers():
    """Verify E/Z double bond stereochemistry is preserved and correctly detected in has_stereochemistry."""
    # 2-butene cis vs trans
    trans_butene = "C/C=C/C"
    cis_butene = "C/C=C\\C"
    
    trans_res = chemistry_pipeline.standardize(trans_butene)
    cis_res = chemistry_pipeline.standardize(cis_butene)
    
    assert trans_res.has_stereochemistry is True
    assert cis_res.has_stereochemistry is True
    assert trans_res.canonical_smiles != cis_res.canonical_smiles
    assert trans_res.inchikey != cis_res.inchikey
    assert trans_res.inchikey.split("-")[0] == cis_res.inchikey.split("-")[0]
    assert trans_res.inchikey.split("-")[1] != cis_res.inchikey.split("-")[1]
    
    # Fumaric (trans) vs Maleic (cis) acid
    fumaric_acid = "O=C(O)/C=C/C(=O)O"
    maleic_acid = "O=C(O)/C=C\\C(=O)O"
    
    fum_res = chemistry_pipeline.standardize(fumaric_acid)
    mal_res = chemistry_pipeline.standardize(maleic_acid)
    
    assert fum_res.has_stereochemistry is True
    assert mal_res.has_stereochemistry is True
    assert fum_res.canonical_smiles != mal_res.canonical_smiles
    assert fum_res.inchikey != mal_res.inchikey


def test_stereochemistry_diastereomers():
    """Verify diastereomer pairs (L-threonine vs L-allothreonine) are distinct."""
    l_threonine = "C[C@H](O)[C@@H](N)C(=O)O"
    l_allothreonine = "C[C@@H](O)[C@@H](N)C(=O)O"
    
    threo_res = chemistry_pipeline.standardize(l_threonine)
    allo_res = chemistry_pipeline.standardize(l_allothreonine)
    
    assert threo_res.has_stereochemistry is True
    assert allo_res.has_stereochemistry is True
    assert threo_res.canonical_smiles != allo_res.canonical_smiles
    assert threo_res.inchikey != allo_res.inchikey
    assert threo_res.inchikey.split("-")[0] == allo_res.inchikey.split("-")[0]
    assert threo_res.inchikey.split("-")[1] != allo_res.inchikey.split("-")[1]


def test_stereochemistry_tautomer_chiral_retention():
    """Verify tautomer canonicalization retains chiral centers without losing assignment to '?'."""
    from rdkit import Chem
    
    # (S)-warfarin with chiral benzylic center adjacent to 4-hydroxycoumarin tautomeric system
    s_warfarin = "CC(=O)C[C@H](c1ccccc1)c1c(O)c2ccccc2oc1=O"
    res = chemistry_pipeline.standardize(s_warfarin)
    
    assert res.has_stereochemistry is True
    assert "@" in res.canonical_smiles
    centers = Chem.FindMolChiralCenters(res.mol, includeUnassigned=True)
    assert len(centers) >= 1
    # Chiral center must NOT be degraded to unspecified '?'
    assert all(c[1] in ("R", "S") for c in centers)

