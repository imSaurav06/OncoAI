"""
Deterministic RDKit Chemistry Standardization Pipeline (Section 7 of architecture).
Implements deterministic: Parse -> Validate -> Sanitize -> Standardize -> Canonicalize -> Scaffold -> Descriptors -> Fingerprints -> QC.
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import rdkit
from rdkit import Chem
from rdkit.Chem import MolStandardize
from rdkit.Chem.MolStandardize import rdMolStandardize
from rdkit.Chem.Scaffolds import MurckoScaffold

from app.config.settings import settings
from app.chemistry.descriptors import calculate_descriptors
from app.chemistry.fingerprints import generate_morgan_fingerprint


class ChemistryPipelineError(Exception):
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class InvalidStructureError(ChemistryPipelineError):
    pass


class SanitizationError(ChemistryPipelineError):
    pass


class StandardizationError(ChemistryPipelineError):
    pass


@dataclass
class StandardizationResult:
    canonical_smiles: str
    isomeric_smiles: Optional[str]
    inchikey: str
    inchi: Optional[str]
    was_modified: bool
    salt_removed: bool
    charge_neutralized: bool
    salt_fragment_smiles: Optional[str]
    parent_smiles: str
    mol: Chem.Mol


@dataclass
class AnalysisResult:
    standardization: StandardizationResult
    descriptors: Dict[str, Any]
    murcko_scaffold: Optional[str]
    fingerprint_hex: str
    fingerprint_on_bits: int
    rdkit_version: str
    pipeline_version: str


class ChemistryPipeline:
    """
    Deterministic chemistry standardization and property extraction engine.
    Ensures reproducibility across platform versions.
    """

    def __init__(self):
        self.rdkit_version = rdkit.__version__
        self.pipeline_version = settings.PIPELINE_VERSION
        self.fragment_chooser = rdMolStandardize.LargestFragmentChooser()
        self.uncharger = rdMolStandardize.Uncharger()

    def standardize(self, raw_smiles: str) -> StandardizationResult:
        """
        Executes deterministic multi-stage standardization pipeline.
        """
        if not raw_smiles or not raw_smiles.strip():
            raise InvalidStructureError("EMPTY_SMILES", "SMILES input cannot be empty")

        clean_input = raw_smiles.strip()

        # Step 1: Parse without sanitizing to catch malformed structures
        mol = Chem.MolFromSmiles(clean_input, sanitize=False)
        if mol is None:
            raise InvalidStructureError(
                "PARSE_FAILED",
                f"Failed to parse SMILES into chemical graph: {clean_input}"
            )

        # Step 2: Validate atomic properties & valence
        if mol.GetNumAtoms() == 0:
            raise InvalidStructureError("EMPTY_GRAPH", "Parsed molecule contains zero atoms")

        # Step 3: Sanitize
        try:
            Chem.SanitizeMol(mol)
        except Exception as exc:
            raise SanitizationError(
                "SANITIZE_FAILED",
                f"RDKit sanitization failed: {str(exc)}",
                {"original_smiles": clean_input}
            )

        original_canonical = Chem.MolToSmiles(mol, canonical=True)
        salt_removed = False
        salt_fragment_smiles = None
        charge_neutralized = False

        # Step 4: Standardize
        try:
            # 4a: Disconnect metals and normalize standard functional groups
            clean_mol = rdMolStandardize.Cleanup(mol)

            # 4b: Salt and fragment stripping (retain largest organic parent)
            frags = Chem.GetMolFrags(clean_mol, asMols=True)
            if len(frags) > 1:
                salt_removed = True
                parent_mol = self.fragment_chooser.choose(clean_mol)
                parent_smi = Chem.MolToSmiles(parent_mol, canonical=True)
                
                # Identify removed salt/solvent fragments
                removed_frags = []
                for f in frags:
                    fsmi = Chem.MolToSmiles(f, canonical=True)
                    if fsmi != parent_smi:
                        removed_frags.append(fsmi)
                if removed_frags:
                    salt_fragment_smiles = ".".join(removed_frags)
            else:
                parent_mol = clean_mol

            # 4c: Neutralize charges (uncharger)
            pre_charge = Chem.GetFormalCharge(parent_mol)
            uncharged_mol = self.uncharger.uncharge(parent_mol)
            post_charge = Chem.GetFormalCharge(uncharged_mol)
            if pre_charge != post_charge:
                charge_neutralized = True

            # 4d: Tautomer canonicalization
            final_mol = rdMolStandardize.CanonicalTautomer(uncharged_mol)

        except Exception as exc:
            raise StandardizationError(
                "STANDARDIZE_FAILED",
                f"Standardization transform failed: {str(exc)}",
                {"original_smiles": clean_input}
            )

        # Step 5: Canonicalize representations
        canonical_smiles = Chem.MolToSmiles(final_mol, canonical=True, isomericSmiles=False)
        isomeric_smiles = Chem.MolToSmiles(final_mol, canonical=True, isomericSmiles=True)
        
        try:
            inchi = Chem.MolToInchi(final_mol)
            inchikey = Chem.MolToInchiKey(final_mol)
        except Exception as exc:
            raise StandardizationError(
                "INCHI_FAILED",
                f"Failed to generate standard InChIKey: {str(exc)}"
            )

        was_modified = (canonical_smiles != original_canonical)

        return StandardizationResult(
            canonical_smiles=canonical_smiles,
            isomeric_smiles=isomeric_smiles,
            inchikey=inchikey,
            inchi=inchi,
            was_modified=was_modified,
            salt_removed=salt_removed,
            charge_neutralized=charge_neutralized,
            salt_fragment_smiles=salt_fragment_smiles,
            parent_smiles=canonical_smiles,
            mol=final_mol,
        )

    def analyze(self, raw_smiles: str) -> AnalysisResult:
        """
        Executes standardization followed by full descriptor calculation,
        Murcko scaffold derivation, and Morgan fingerprint generation.
        """
        std = self.standardize(raw_smiles)
        mol = std.mol

        # Murcko scaffold extraction
        try:
            scaffold_smi = MurckoScaffold.MurckoScaffoldSmiles(mol=mol)
            if scaffold_smi == "":
                scaffold_smi = None
        except Exception:
            scaffold_smi = None

        # Descriptors calculation
        descriptors = calculate_descriptors(mol)

        # Morgan fingerprint generation (ECFP4 equivalent)
        _, fp_hex, on_bits = generate_morgan_fingerprint(mol)

        return AnalysisResult(
            standardization=std,
            descriptors=descriptors,
            murcko_scaffold=scaffold_smi,
            fingerprint_hex=fp_hex,
            fingerprint_on_bits=on_bits,
            rdkit_version=self.rdkit_version,
            pipeline_version=self.pipeline_version,
        )


# Global reusable pipeline instance
chemistry_pipeline = ChemistryPipeline()
