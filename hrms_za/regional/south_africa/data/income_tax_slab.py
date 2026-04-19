"""
SARS PAYE brackets — shipped DISABLED by default.

WARNINGS:
1. These are 2025/2026 tax-year brackets (1 March 2025 – 28 Feb 2026).
   The current tax year (2026/2027) started 1 March 2026 and its brackets
   are announced at the February 2026 Budget. Verify against the SARS site
   and ADD a new Income Tax Slab record before running payroll for any month
   in 2026/27 or later.
2. HRMS's built-in slab evaluation does NOT apply rebates
   (primary R17,235 / secondary R9,444 / tertiary R3,145 for 2025/26) or
   medical aid tax credits. A pure-slab calc will over-tax every employee.
   Use this slab only as a reference; production PAYE needs the custom
   calculator (see data/salary_components.py PAYE description).

SARS source: https://www.sars.gov.za/tax-rates/income-tax/rates-of-tax-for-individuals/
"""


INCOME_TAX_SLAB = {
    "name": "SA Tax 2025/2026",
    "effective_from": "2025-03-01",
    "disabled": 1,  # user enables after verification
    "currency": "ZAR",
    "slabs": [
        {"from_amount": 0,        "to_amount": 237100,  "percent_deduction": 18, "condition": ""},
        {"from_amount": 237101,   "to_amount": 370500,  "percent_deduction": 26, "condition": ""},
        {"from_amount": 370501,   "to_amount": 512800,  "percent_deduction": 31, "condition": ""},
        {"from_amount": 512801,   "to_amount": 673000,  "percent_deduction": 36, "condition": ""},
        {"from_amount": 673001,   "to_amount": 857900,  "percent_deduction": 39, "condition": ""},
        {"from_amount": 857901,   "to_amount": 1817000, "percent_deduction": 41, "condition": ""},
        {"from_amount": 1817001,  "to_amount": 0,       "percent_deduction": 45, "condition": ""},
    ],
}
