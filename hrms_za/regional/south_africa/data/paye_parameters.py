"""
Annual SARS PAYE parameters — rebates, medical credits, tax thresholds,
retirement-fund deduction caps.

These are the numbers that HRMS's built-in slab calculation does NOT apply.
The SA PAYE calculator (still to ship) reads from this file each payroll run,
picks the tax year whose window contains the Salary Slip's posting date, and
applies the rebate + credit logic on top of the slab result.

Source of truth (verified 2026-04-19, updated annually post-Budget):
  https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/
  https://www.sars.gov.za/tax-rates/medical-tax-credit-rates/

Update cadence: every late February / early March after the new Budget.
Add a new dict to each table keyed by the SARS tax-year label
("2026" means 1 March 2025 – 28 February 2026, "2027" means 1 March 2026
– 28 February 2027, etc.). The calculator selects by the effective date.
"""


# Tax-year labels follow SARS convention: the year in which the tax year ENDS.
#   "2026" = 1 Mar 2025 – 28 Feb 2026
#   "2027" = 1 Mar 2026 – 28 Feb 2027

TAX_YEAR_WINDOWS = {
    "2026": ("2025-03-01", "2026-02-28"),
    "2027": ("2026-03-01", "2027-02-28"),
}


# Annual rebates, in Rands. Everyone gets primary. Age 65+ adds secondary.
# Age 75+ adds tertiary on top of secondary.
REBATES = {
    "2026": {
        "primary":   17235,
        "secondary":  9444,
        "tertiary":   3145,
    },
    "2027": {
        "primary":   17820,
        "secondary":  9765,
        "tertiary":   3249,
    },
}


# Annual tax thresholds — below these incomes no PAYE is due. Derived from
# the rebate values; kept here for validation + edge-case short-circuit.
TAX_THRESHOLDS = {
    "2026": {
        "under_65":  95750,
        "65_to_74": 148217,
        "75_plus":  165689,
    },
    "2027": {
        "under_65":   99000,
        "65_to_74":  153250,
        "75_plus":   171300,
    },
}


# Medical Scheme Fees Tax Credit (section 6A) — MONTHLY amounts in Rands.
# Wording per SARS: main member + first dependant each get the higher rate;
# every additional dependant gets the lower rate.
MEDICAL_CREDITS_MONTHLY = {
    "2026": {
        "main_member":          364,
        "first_dependant":      364,
        "additional_dependant": 246,
    },
    "2027": {
        "main_member":          376,
        "first_dependant":      376,
        "additional_dependant": 254,
    },
}


# Retirement-fund contribution deduction cap (Income Tax Act s11F).
# Deductible against PAYE-taxable income up to the lesser of:
#   - 27.5% of the greater of remuneration / taxable income
#   - the annual cap (R350,000 at time of writing, unchanged in recent years)
# Applied BEFORE the slab lookup inside the PAYE calculator.
RETIREMENT_FUND = {
    "rate_cap":        0.275,
    "annual_cap_rand": 350000,
}


# UIF parameters — currently static in the salary_components formula; move
# here once the SA Payroll Settings single doctype ships.
UIF = {
    "monthly_ceiling": 17712,   # last confirmed unchanged since 2021-06-01
    "employee_rate":   0.01,
    "employer_rate":   0.01,
}


# SDL parameters
SDL = {
    "rate":                      0.01,
    "small_employer_threshold":  500000,   # annual payroll; below this = exempt
}


def tax_year_for(posting_date):
    """
    Pick the SARS tax-year label that contains posting_date. Returns None if
    the date falls outside every configured window (force a refresh of this
    file when that happens — a new year needs entries added).
    """
    from frappe.utils import getdate

    d = getdate(posting_date)
    for label, (start, end) in TAX_YEAR_WINDOWS.items():
        if getdate(start) <= d <= getdate(end):
            return label
    return None
