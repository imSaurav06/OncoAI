"""
Unit Tests for Bioactivity & Unit Normalization Engine.
"""
import pytest
from app.normalization.units import (
    normalize_bioactivity,
    normalize_relation,
    normalize_unit_string,
)


def test_concentration_normalization_micromolar():
    # 2.5 uM -> 2500.0 nM
    meas = normalize_bioactivity(2.5, "uM", relation="=", activity_type="IC50")
    assert meas.normalized_value == 2500.0
    assert meas.normalized_unit == "nM"
    assert meas.normalized_relation == "="
    # pIC50 = -log10(2500 * 1e-9) = 5.602
    assert meas.p_activity == 5.602


def test_concentration_normalization_nanomolar():
    meas = normalize_bioactivity(10.0, "nM", relation="<", activity_type="Ki")
    assert meas.normalized_value == 10.0
    assert meas.normalized_unit == "nM"
    assert meas.normalized_relation == "<"
    assert meas.p_activity == 8.0
    # Inequality inverts: Ki < 10 nM -> pKi > 8.0
    assert meas.p_activity_relation == ">"
    assert meas.is_censored is True


def test_pactivity_inequality_inversion_censoring():
    """Verify that negative logarithm inverts greater-than to less-than and marks censored."""
    # Inactive compound: IC50 > 10,000 nM -> pIC50 < 5.0
    meas_gt = normalize_bioactivity(10000.0, "nM", relation=">", activity_type="IC50")
    assert meas_gt.normalized_value == 10000.0
    assert meas_gt.p_activity == 5.0
    assert meas_gt.p_activity_relation == "<"
    assert meas_gt.is_censored is True

    # High potency beyond detection limit: IC50 < 0.1 nM -> pIC50 > 10.0
    meas_lt = normalize_bioactivity(0.1, "nM", relation="<", activity_type="IC50")
    assert meas_lt.normalized_value == 0.1
    assert meas_lt.p_activity == 10.0
    assert meas_lt.p_activity_relation == ">"
    assert meas_lt.is_censored is True

    # Exact observation: relation '=' -> p_activity_relation '='
    meas_eq = normalize_bioactivity(50.0, "nM", relation="=", activity_type="IC50")
    assert meas_eq.normalized_value == 50.0
    assert meas_eq.p_activity_relation == "="
    assert meas_eq.is_censored is False


def test_concentration_normalization_millimolar():
    # 0.1 mM -> 100,000 nM
    meas = normalize_bioactivity(0.1, "mM", activity_type="EC50")
    assert meas.normalized_value == 100000.0
    assert meas.normalized_unit == "nM"
    assert meas.p_activity == 4.0
    assert meas.p_activity_relation == "="
    assert meas.is_censored is False


def test_mass_concentration_conversion():
    # 1.0 ug/mL for compound with MW = 500.0 g/mol -> (1 / 500) * 1e6 = 2000 nM
    meas = normalize_bioactivity(1.0, "ug/mL", activity_type="IC50", molecular_weight=500.0)
    assert meas.normalized_value == 2000.0
    assert meas.normalized_unit == "nM"
    assert meas.p_activity == 5.699


def test_percentage_inhibition_unit():
    meas = normalize_bioactivity(85.5, "%", relation=">=", activity_type="% Inhibition")
    assert meas.normalized_value == 85.5
    assert meas.normalized_unit == "%"
    assert meas.normalized_relation == ">="
    assert meas.p_activity is None
    assert meas.is_censored is True


def test_outlier_detection_negative_activity():
    meas = normalize_bioactivity(-5.0, "nM")
    assert meas.is_outlier is True
    assert "Negative activity value" in meas.qc_warning
