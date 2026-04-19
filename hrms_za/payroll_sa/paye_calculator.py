"""
South African PAYE calculator.

HRMS's built-in Income Tax Slab evaluation gives us the correct bracket-level
annual tax (for the active slab + exempted earnings). What it does NOT do:

    1. Subtract the primary / secondary / tertiary rebate (by age).
    2. Subtract the medical scheme fees tax credit (by dependant count).
    3. Clamp the result at zero for sub-threshold incomes.

This module adds those three steps. It is wired via doc_events as a
`Salary Slip.validate` hook, so it runs AFTER HRMS has finalised the slip
and written the slab PAYE amount — we just adjust the PAYE row and
delta-update the slip totals.

Correctness caveats still open (documented, not blockers for v0.0.1):

- **Retirement fund contribution cap (27.5% / R350k).** Assumed handled
  upstream by marking the RA salary component `exempted_from_income_tax=1`
  on the Salary Structure. This module does NOT independently enforce the
  cap; a future validator can read RETIREMENT_FUND[...] from paye_parameters
  and warn / clamp when the contribution exceeds the cap.
- **Travel-allowance 80/20 rule.** Expected to be handled via an earning
  component with the right taxable portion, not here.
- **Fringe benefits, arrears, bonus spreading.** Deferred.

Source of truth for all numeric inputs (rebates, credits):
  hrms_za/regional/south_africa/data/paye_parameters.py
"""

from hrms_za.regional.south_africa.data.paye_parameters import (
    MEDICAL_CREDITS_MONTHLY,
    REBATES,
)


# Salary Component name we adjust. Must match the component shipped by
# hrms_za.regional.south_africa.data.salary_components.
PAYE_COMPONENT = "PAYE"


# ---------------------------------------------------------------------------
# Pure function — safe to unit-test without Frappe
# ---------------------------------------------------------------------------

def compute_sa_paye(
    slab_annual_tax: float,
    age: int,
    medical_members: int,
    tax_year: str,
) -> float:
    """
    Return the monthly PAYE amount in Rands.

    Args:
        slab_annual_tax: annual tax computed from SARS brackets on the
            employee's taxable income (HRMS already produces this).
        age: employee age at end of the tax period.
        medical_members: total covered lives on medical aid (inc. employee).
        tax_year: SARS label, e.g. "2027" for 1 Mar 2026 – 28 Feb 2027.

    Raises:
        KeyError if tax_year is not configured in paye_parameters.
    """
    rebate = REBATES[tax_year]["primary"]
    if age >= 65:
        rebate += REBATES[tax_year]["secondary"]
    if age >= 75:
        rebate += REBATES[tax_year]["tertiary"]

    mc = MEDICAL_CREDITS_MONTHLY[tax_year]
    monthly_credit = 0.0
    if medical_members >= 1:
        monthly_credit += mc["main_member"]
    if medical_members >= 2:
        monthly_credit += mc["first_dependant"]
    if medical_members > 2:
        monthly_credit += mc["additional_dependant"] * (medical_members - 2)
    annual_credit = monthly_credit * 12

    annual_paye = max(0.0, slab_annual_tax - rebate - annual_credit)
    return annual_paye / 12


# ---------------------------------------------------------------------------
# Salary Slip hook
# ---------------------------------------------------------------------------

def adjust_sa_paye(doc, method=None):
    """
    Rewrite the PAYE deduction on a Salary Slip with the SA rebate- and
    medical-credit-adjusted amount. Delta-updates total_deduction and
    net_pay without recomputing other components.

    Fires on Salary Slip `validate`. No-op for non-SA companies, slips
    without a PAYE row, or posting dates outside a configured tax-year window.
    """
    # Lazy import so the pure compute_sa_paye function above is unit-testable
    # outside a Frappe runtime.
    import frappe
    from frappe.utils import flt
    from hrms_za.regional.south_africa.data.paye_parameters import tax_year_for

    country = frappe.db.get_value("Company", doc.company, "country")
    if country != "South Africa":
        return

    paye_row = _find_paye_row(doc)
    if paye_row is None:
        return

    tax_year = tax_year_for(doc.end_date) or tax_year_for(doc.start_date)
    if tax_year is None:
        # Outside every configured window — don't second-guess HRMS.
        # Add a new entry to paye_parameters.TAX_YEAR_WINDOWS when this fires.
        return

    emp = frappe.db.get_value(
        "Employee",
        doc.employee,
        ["date_of_birth", "medical_aid_members"],
        as_dict=True,
    ) or {}

    age = _age_at(emp.get("date_of_birth"), doc.end_date)
    members = int(flt(emp.get("medical_aid_members")))

    slab_annual_tax = flt(paye_row.amount) * 12
    new_monthly_paye = compute_sa_paye(
        slab_annual_tax=slab_annual_tax,
        age=age,
        medical_members=members,
        tax_year=tax_year,
    )

    _apply_paye_adjustment(doc, paye_row, new_monthly_paye)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_paye_row(doc):
    for d in doc.deductions or []:
        if d.salary_component == PAYE_COMPONENT:
            return d
    return None


def _age_at(date_of_birth, at_date):
    from frappe.utils import getdate

    if not date_of_birth or not at_date:
        return 0
    dob = getdate(date_of_birth)
    at = getdate(at_date)
    age = at.year - dob.year - ((at.month, at.day) < (dob.month, dob.day))
    return max(age, 0)


def _apply_paye_adjustment(doc, paye_row, new_monthly_paye):
    from frappe.utils import flt

    old = flt(paye_row.amount)
    new = flt(new_monthly_paye)
    if abs(old - new) < 0.01:
        return

    delta = new - old
    paye_row.amount = new

    doc.total_deduction = flt(doc.total_deduction) + delta
    doc.net_pay = flt(doc.net_pay) - delta
    if getattr(doc, "rounded_total", None) is not None:
        doc.rounded_total = round(doc.net_pay)
