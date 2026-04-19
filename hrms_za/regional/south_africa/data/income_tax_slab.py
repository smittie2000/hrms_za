"""
SARS PAYE brackets — per tax year.

Source (authoritative): https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/

Each March at the Finance Minister's budget speech SARS publishes the brackets
for the tax year starting 1 March. Add a new dict to INCOME_TAX_SLABS each
year; setup.py installs all of them per-company and Frappe picks the right one
based on the Payroll Period's effective date.

IMPORTANT — correctness caveat:
    HRMS's built-in slab evaluation applies the percentage table but does NOT
    apply SA-specific primary/secondary/tertiary age rebates or medical aid
    tax credits (s6A / s6B). That means any PAYE value computed from these
    slabs alone will over-tax every employee by the rebate amount
    (2025/26 primary rebate = R17 235/year = R1 436/month).

    These slabs are shipped for demo / reference. The production PAYE
    calculation arrives with the SA PAYE calculator (a dedicated doc_events
    hook on Salary Slip that wraps the slab result with rebate and medical
    credit logic).
"""


INCOME_TAX_SLABS = [
    {
        # Historical reference. Disabled by default — unlikely to be needed
        # for month-end payroll runs made now, but kept for testing,
        # back-dated corrections, and audit replay.
        "name": "SA Tax 2025/2026",
        "effective_from": "2025-03-01",
        "disabled": 1,
        "currency": "ZAR",
        "slabs": [
            {"from_amount": 0,       "to_amount": 237100,  "percent_deduction": 18, "condition": ""},
            {"from_amount": 237101,  "to_amount": 370500,  "percent_deduction": 26, "condition": ""},
            {"from_amount": 370501,  "to_amount": 512800,  "percent_deduction": 31, "condition": ""},
            {"from_amount": 512801,  "to_amount": 673000,  "percent_deduction": 36, "condition": ""},
            {"from_amount": 673001,  "to_amount": 857900,  "percent_deduction": 39, "condition": ""},
            {"from_amount": 857901,  "to_amount": 1817000, "percent_deduction": 41, "condition": ""},
            {"from_amount": 1817001, "to_amount": 0,       "percent_deduction": 45, "condition": ""},
        ],
    },
    {
        # Current tax year (1 March 2026 – 28 February 2027).
        # Published by SARS at the 25 February 2026 budget — source URL above.
        # Shipped ENABLED so demo Salary Slips populate PAYE; value is the
        # slab result only (rebates + medical credits still TODO).
        "name": "SA Tax 2026/2027",
        "effective_from": "2026-03-01",
        "disabled": 0,
        "currency": "ZAR",
        "slabs": [
            {"from_amount": 0,       "to_amount": 245100,  "percent_deduction": 18, "condition": ""},
            {"from_amount": 245101,  "to_amount": 383100,  "percent_deduction": 26, "condition": ""},
            {"from_amount": 383101,  "to_amount": 530200,  "percent_deduction": 31, "condition": ""},
            {"from_amount": 530201,  "to_amount": 695800,  "percent_deduction": 36, "condition": ""},
            {"from_amount": 695801,  "to_amount": 887000,  "percent_deduction": 39, "condition": ""},
            {"from_amount": 887001,  "to_amount": 1878600, "percent_deduction": 41, "condition": ""},
            {"from_amount": 1878601, "to_amount": 0,       "percent_deduction": 45, "condition": ""},
        ],
    },
]
