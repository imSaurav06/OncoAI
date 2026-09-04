"""
Chemistry validation utilities and structural sanity checkers.
"""
from typing import Optional, Tuple
from rdkit import Chem


class ValidationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def validate_raw_smiles(smiles: str) -> Tuple[bool, Optional[str]]:
    """
    Performs preliminary validation on raw SMILES input string.
    Returns: (is_valid, error_reason)
    """
    if not smiles or not smiles.strip():
        return False, "SMILES string is empty"
    
    clean_smiles = smiles.strip()
    if len(clean_smiles) > 5000:
        return False, "SMILES exceeds maximum allowed length of 5000 characters"

    return True, None
