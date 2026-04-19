"""
Core South African Salary Components.

IMPORTANT: formulas here reference the monthly UIF ceiling (R17,712 as at
2021-06-01, last confirmed unchanged in 2025). This value changes infrequently
but MUST be reviewed every 1 March (start of tax year). When it changes, either
update the formula here, or move the constant into an SA Payroll Settings
Single doctype and reference it from the formula.

The PAYE component is a PLACEHOLDER. Real PAYE requires rebates
(primary / secondary / tertiary) + medical aid tax credits (s6A / s6B), which
are not expressible in a salary component formula. Ship a custom calc function
and call it from a doc_events hook on Salary Slip. See project TODO.

Salary Component → GL Account mapping is per-Company via Salary Component Account
child table. That mapping is NOT shipped here (per INTEGRATION_MAP §4, it's a
per-tenant configuration concern).
"""


# UIF monthly remuneration ceiling (Rands). Current since 2021-06-01.
UIF_MONTHLY_CEILING = 17712

SALARY_COMPONENTS = [
    {
        "salary_component": "Basic",
        "abbr": "B",
        "type": "Earning",
        "is_tax_applicable": 1,
        "depends_on_payment_days": 1,
    },
    {
        "salary_component": "Overtime",
        "abbr": "OT",
        "type": "Earning",
        "is_tax_applicable": 1,
        "depends_on_payment_days": 0,
    },
    {
        "salary_component": "Bonus",
        "abbr": "BON",
        "type": "Earning",
        "is_tax_applicable": 1,
        "depends_on_payment_days": 0,
    },
    {
        "salary_component": "Travel Allowance",
        "abbr": "TA",
        "type": "Earning",
        "is_tax_applicable": 1,
        "depends_on_payment_days": 1,
        "description": (
            "80% of travel allowance is taxable by default under SARS rules "
            "(20% if employer-certified ≥80% business use). PAYE treatment "
            "handled in custom calc, not here."
        ),
    },
    {
        "salary_component": "Cellphone Allowance",
        "abbr": "CA",
        "type": "Earning",
        "is_tax_applicable": 1,
        "depends_on_payment_days": 1,
    },
    {
        "salary_component": "UIF - Employee",
        "abbr": "UIFE",
        "type": "Deduction",
        "amount_based_on_formula": 1,
        "formula": f"min(gross_pay, {UIF_MONTHLY_CEILING}) * 0.01",
        "depends_on_payment_days": 0,
        "round_to_the_nearest_integer": 0,
    },
    {
        "salary_component": "UIF - Employer",
        "abbr": "UIFR",
        "type": "Deduction",
        "statistical_component": 1,
        "amount_based_on_formula": 1,
        "formula": f"min(gross_pay, {UIF_MONTHLY_CEILING}) * 0.01",
        "depends_on_payment_days": 0,
        "do_not_include_in_total": 1,
        "description": (
            "Statistical — employer's matching 1%. Not deducted from employee; "
            "tracked for EMP201 submission."
        ),
    },
    {
        "salary_component": "SDL",
        "abbr": "SDL",
        "type": "Deduction",
        "statistical_component": 1,
        "amount_based_on_formula": 1,
        "formula": "gross_pay * 0.01",
        "depends_on_payment_days": 0,
        "do_not_include_in_total": 1,
        "description": (
            "Skills Development Levy — 1% of total remuneration, employer-paid. "
            "Statistical: not deducted from employee. Small employers "
            "(< R500k annual payroll) are SDL-exempt."
        ),
    },
    {
        "salary_component": "PAYE",
        "abbr": "PAYE",
        "type": "Deduction",
        "variable_based_on_taxable_salary": 1,
        "is_income_tax_component": 1,
        "depends_on_payment_days": 0,
        "description": (
            "PLACEHOLDER. Default HRMS slab-based calc does not handle SA "
            "rebates or medical aid tax credits. Override via doc_events on "
            "Salary Slip once the SA PAYE calculator ships."
        ),
    },
]
