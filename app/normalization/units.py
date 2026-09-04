"""
Bioactivity Unit Normalization Engine (Section 10 of architecture).
Preserves original scientific observations while deterministically normalizing to canonical SI units.
"""
from dataclasses import dataclass
from typing import Optional, Tuple
import math


class UnitNormalizationError(Exception):
    def __init__(self, message: str, unit: str):
        super().__init__(message)
        self.unit = unit


@dataclass
class NormalizedMeasurement:
    original_value: float
    original_unit: str
    original_relation: str
    normalized_value: float
    normalized_unit: str
    normalized_relation: str
    p_activity: Optional[float]
    is_outlier: bool
    qc_warning: Optional[str] = None


# Canonical conversion factors to nanomolar (nM)
CONCENTRATION_TO_NM = {
    "m": 1e9,
    "molar": 1e9,
    "mm": 1e6,
    "millimolar": 1e6,
    "um": 1e3,
    "µm": 1e3,
    "micromolar": 1e3,
    "nm": 1.0,
    "nanomolar": 1.0,
    "pm": 1e-3,
    "picomolar": 1e-3,
    "fm": 1e-6,
    "femtomolar": 1e-6,
}

PERCENT_UNITS = {"%", "percent", "pct", "% inhibition", "percent inhibition"}


def normalize_unit_string(unit: str) -> str:
    """Cleans unit string to lowercase alphanumeric representation."""
    if not unit:
        return ""
    clean = unit.strip().lower()
    clean = clean.replace("micro", "u").replace("µ", "u")
    return clean


def normalize_relation(rel: Optional[str]) -> str:
    """Standardizes mathematical operator."""
    if not rel or not rel.strip():
        return "="
    clean = rel.strip()
    if clean in ("=", "=="):
        return "="
    if clean in (">", ">="):
        return clean
    if clean in ("<", "<="):
        return clean
    if clean in ("~", "approx"):
        return "~"
    return "="


def normalize_bioactivity(
    value: float,
    unit: str,
    relation: Optional[str] = "=",
    activity_type: Optional[str] = "IC50",
    molecular_weight: Optional[float] = None
) -> NormalizedMeasurement:
    """
    Deterministically normalizes a scientific bioactivity observation.
    Maintains complete provenance of both original and transformed values.
    """
    if value is None:
        raise ValueError("Bioactivity value cannot be None")

    orig_rel = normalize_relation(relation)
    clean_unit = normalize_unit_string(unit)
    norm_rel = orig_rel
    qc_warning = None
    is_outlier = False

    # Negative activity check
    if value < 0:
        is_outlier = True
        qc_warning = f"Negative activity value: {value} {unit}"

    # 1. Direct Concentration Normalization (to nM)
    if clean_unit in CONCENTRATION_TO_NM:
        factor = CONCENTRATION_TO_NM[clean_unit]
        norm_val = round(value * factor, 4)
        norm_unit = "nM"

        # Outlier check for extreme values (< 0.001 nM or > 100,000,000 nM)
        if norm_val > 1e8 or (norm_val < 1e-4 and norm_val > 0):
            is_outlier = True
            qc_warning = f"Extreme normalized potency: {norm_val} nM"

    # 2. Mass-per-volume normalization (e.g. ug/mL -> nM if MW is known)
    elif clean_unit in ("ug/ml", "mg/l", "ug/l", "ng/ml"):
        if molecular_weight and molecular_weight > 0:
            if clean_unit in ("ug/ml", "mg/l"):
                # 1 ug/mL = 1 mg/L = (1 / MW) * 1e-3 mol/L = (1 / MW) * 1e6 nM
                norm_val = round((value / molecular_weight) * 1e6, 4)
                norm_unit = "nM"
            elif clean_unit == "ug/l":
                norm_val = round((value / molecular_weight) * 1e3, 4)
                norm_unit = "nM"
            else:  # ng/ml = 1 ug/L
                norm_val = round((value / molecular_weight) * 1e3, 4)
                norm_unit = "nM"
        else:
            # Preserve mass concentration directly if MW unknown
            norm_val = round(value, 4)
            norm_unit = clean_unit
            qc_warning = "Molecular weight missing for mass-to-molar conversion"

    # 3. Percentage Inhibition
    elif clean_unit in PERCENT_UNITS:
        norm_val = round(value, 2)
        norm_unit = "%"
        if norm_val > 150.0 or norm_val < -50.0:
            is_outlier = True
            qc_warning = f"Suspicious inhibition percentage: {norm_val}%"

    else:
        # Unknown/Custom unit: preserve value with warning
        norm_val = round(value, 4)
        norm_unit = clean_unit or "UNKNOWN"
        qc_warning = f"Unrecognized scientific unit: {unit}"

    # Calculate pActivity (-log10 Molar) for concentration types (IC50, EC50, Ki, Kd, GI50)
    p_activity = None
    act_type_upper = (activity_type or "").upper()
    if norm_unit == "nM" and norm_val > 0 and act_type_upper in ("IC50", "EC50", "KI", "KD", "GI50", "POTENCY"):
        molar_val = norm_val * 1e-9
        try:
            p_activity = round(-math.log10(molar_val), 3)
        except (ValueError, OverflowError):
            p_activity = None

    return NormalizedMeasurement(
        original_value=value,
        original_unit=unit,
        original_relation=orig_rel,
        normalized_value=norm_val,
        normalized_unit=norm_unit,
        normalized_relation=norm_rel,
        p_activity=p_activity,
        is_outlier=is_outlier,
        qc_warning=qc_warning,
    )
