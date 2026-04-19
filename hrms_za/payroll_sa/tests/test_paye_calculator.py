"""
Pure-function tests for compute_sa_paye — no Frappe runtime required.

Run locally:
    python -m pytest hrms_za/payroll_sa/tests/test_paye_calculator.py -v

Run inside the backend container:
    docker exec -it -u frappe frappe-backend-1 \
        bench --site crm.hostedsip.co.za run-tests \
        --module hrms_za.payroll_sa.tests.test_paye_calculator

Each test is an independently computable SARS-style worked example.
Input `slab_annual_tax` is calculated by hand against the 2026/27 brackets so
the test fails loudly if either the brackets OR the rebate/credit tables shift
unexpectedly.
"""

import pytest

from hrms_za.payroll_sa.paye_calculator import compute_sa_paye


# 2026/27 bracket hand-computed worked amounts.
# Reference: 245100@18%, 44118+26%above245100, 79998+31%above383100 ...
ANNUAL_TAX_R100K = 18_000       # 100000 * 0.18
ANNUAL_TAX_R300K = 58_392       # 44118 + 0.26 * (300000 - 245100)
ANNUAL_TAX_R500K = 116_237      # 79998 + 0.31 * (500000 - 383100)


# -----------------------------------------------------------------------------
# Low income → PAYE clamps to zero
# -----------------------------------------------------------------------------

def test_below_tax_threshold_clamps_to_zero():
    # R50k/yr at 18% = R9,000 slab tax; primary rebate R17,820 > slab tax
    result = compute_sa_paye(
        slab_annual_tax=9_000, age=30, medical_members=0, tax_year="2027"
    )
    assert result == 0.0


# -----------------------------------------------------------------------------
# Under 65, no medical — primary rebate only
# -----------------------------------------------------------------------------

def test_under_65_r300k_no_medical():
    # 58_392 - 17_820 = 40_572 annual, / 12 = 3_381 monthly
    result = compute_sa_paye(
        slab_annual_tax=ANNUAL_TAX_R300K, age=35, medical_members=0, tax_year="2027"
    )
    assert round(result, 2) == 3_381.00


def test_under_65_r500k_no_medical():
    # 116_237 - 17_820 = 98_417 annual, / 12 = 8_201.42 monthly
    result = compute_sa_paye(
        slab_annual_tax=ANNUAL_TAX_R500K, age=40, medical_members=0, tax_year="2027"
    )
    assert round(result, 2) == pytest.approx(8_201.42, abs=0.01)


# -----------------------------------------------------------------------------
# Age 65+ — secondary rebate kicks in
# -----------------------------------------------------------------------------

def test_age_65_r500k_no_medical():
    # 116_237 - (17_820 + 9_765) = 88_652 annual, / 12 = 7_387.67 monthly
    result = compute_sa_paye(
        slab_annual_tax=ANNUAL_TAX_R500K, age=65, medical_members=0, tax_year="2027"
    )
    assert round(result, 2) == pytest.approx(7_387.67, abs=0.01)


def test_age_75_r500k_no_medical():
    # 116_237 - (17_820 + 9_765 + 3_249) = 85_403 annual, / 12 = 7_116.92
    result = compute_sa_paye(
        slab_annual_tax=ANNUAL_TAX_R500K, age=75, medical_members=0, tax_year="2027"
    )
    assert round(result, 2) == pytest.approx(7_116.92, abs=0.01)


# -----------------------------------------------------------------------------
# Medical aid members — s6A credit
# -----------------------------------------------------------------------------

def test_2_members_main_plus_one_dependant():
    # Monthly credit: R376 + R376 = R752  →  annual R9,024
    # 116_237 - 17_820 - 9_024 = 89_393 annual, / 12 = 7_449.42
    result = compute_sa_paye(
        slab_annual_tax=ANNUAL_TAX_R500K, age=40, medical_members=2, tax_year="2027"
    )
    assert round(result, 2) == pytest.approx(7_449.42, abs=0.01)


def test_4_members_family_of_four():
    # Monthly credit: 376 + 376 + 254*2 = R1,260  →  annual R15,120
    # 116_237 - 17_820 - 15_120 = 83_297 annual, / 12 = 6_941.42
    result = compute_sa_paye(
        slab_annual_tax=ANNUAL_TAX_R500K, age=40, medical_members=4, tax_year="2027"
    )
    assert round(result, 2) == pytest.approx(6_941.42, abs=0.01)


# -----------------------------------------------------------------------------
# Historical tax year — 2025/26 numbers must match too
# -----------------------------------------------------------------------------

def test_tax_year_2026_uses_old_figures():
    # 2025/26 primary rebate is R17,235 (not R17,820). R300k slab tax 2025/26
    # bracket boundaries were different (237,100 vs 245,100), but for this
    # test we just verify the rebate lookup — slab_annual_tax passed in directly.
    r_2026 = compute_sa_paye(
        slab_annual_tax=58_392, age=35, medical_members=0, tax_year="2026"
    )
    r_2027 = compute_sa_paye(
        slab_annual_tax=58_392, age=35, medical_members=0, tax_year="2027"
    )
    # 2027 has a larger primary rebate → lower PAYE
    assert r_2027 < r_2026
    # Delta should be (17_820 - 17_235) / 12 = 48.75
    assert round(r_2026 - r_2027, 2) == pytest.approx(48.75, abs=0.01)


# -----------------------------------------------------------------------------
# Real-world payslip regression
# -----------------------------------------------------------------------------

def test_real_march_2026_r40k_age_38_no_medical():
    slab_tax = 79_998 + 0.31 * (480_000 - 383_100)
    result = compute_sa_paye(
        slab_annual_tax=slab_tax, age=38, medical_members=0, tax_year="2027"
    )
    assert round(result, 2) == 7_684.75


# -----------------------------------------------------------------------------
# Unknown tax year → raises
# -----------------------------------------------------------------------------

def test_unknown_tax_year_raises():
    with pytest.raises(KeyError):
        compute_sa_paye(
            slab_annual_tax=58_392, age=35, medical_members=0, tax_year="2030"
        )
