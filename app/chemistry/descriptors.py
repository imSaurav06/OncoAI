"""
Molecular descriptor calculations using RDKit.
"""
from typing import Dict, Any
from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski, Crippen, rdMolDescriptors


def calculate_descriptors(mol: Chem.Mol) -> Dict[str, Any]:
    """
    Computes standard physicochemical and Lipinski/Veber descriptors for a standardized molecule.
    """
    chiral_centers = Chem.FindMolChiralCenters(mol, includeUnassigned=True)
    defined_chiral = [c for c in chiral_centers if c[1] in ("R", "S")]

    return {
        "molecular_weight": round(float(Descriptors.MolWt(mol)), 4),
        "exact_mass": round(float(Descriptors.ExactMolWt(mol)), 4),
        "molecular_formula": rdMolDescriptors.CalcMolFormula(mol),
        "heavy_atom_count": int(mol.GetNumHeavyAtoms()),
        "formal_charge": int(Chem.GetFormalCharge(mol)),
        "clogp": round(float(Crippen.MolLogP(mol)), 4),
        "tpsa": round(float(rdMolDescriptors.CalcTPSA(mol)), 4),
        "hbd": int(Lipinski.NumHDonors(mol)),
        "hba": int(Lipinski.NumHAcceptors(mol)),
        "rotatable_bonds": int(Lipinski.NumRotatableBonds(mol)),
        "fraction_csp3": round(float(rdMolDescriptors.CalcFractionCSP3(mol)), 4),
        "num_rings": int(rdMolDescriptors.CalcNumRings(mol)),
        "num_aromatic_rings": int(rdMolDescriptors.CalcNumAromaticRings(mol)),
        "num_aliphatic_rings": int(rdMolDescriptors.CalcNumAliphaticRings(mol)),
        "num_chiral_centers": int(len(chiral_centers)),
        "num_defined_chiral_centers": int(len(defined_chiral)),
        "num_undefined_chiral_centers": int(len(chiral_centers) - len(defined_chiral)),
    }
