"""
EMP201 Monthly Return — placeholder.

Shape-correct layout of the SARS EMP201 monthly submission:
  - PAYE liability (total)
  - UIF contributions (employee + employer)
  - SDL liability
  - ETI refund claimed
  - Net payable to SARS

Calculation not implemented. This report intentionally returns an empty
single-row dataset for the chosen period so the UI shows the SARS-facing
column shape for management/demo review. Replace `execute` with real
aggregation once the PAYE calculator is live.
"""

import frappe
from frappe import _


def execute(filters=None):
    return get_columns(), get_placeholder_row(filters or {})


def get_columns():
    return [
        {"label": _("Line"),             "fieldname": "line",    "fieldtype": "Data",     "width": 260},
        {"label": _("Code"),             "fieldname": "code",    "fieldtype": "Data",     "width": 80},
        {"label": _("Amount (ZAR)"),     "fieldname": "amount",  "fieldtype": "Currency", "width": 160},
        {"label": _("Notes"),            "fieldname": "notes",   "fieldtype": "Data",     "width": 400},
    ]


def get_placeholder_row(filters):
    return [
        {"line": _("PAYE Liability"),                "code": "7002", "amount": 0, "notes": _("From Salary Slip PAYE deductions")},
        {"line": _("SDL Liability"),                 "code": "7003", "amount": 0, "notes": _("1% of total remuneration")},
        {"line": _("UIF Contribution (Employee)"),   "code": "7004", "amount": 0, "notes": _("1% of remuneration, capped")},
        {"line": _("UIF Contribution (Employer)"),   "code": "7005", "amount": 0, "notes": _("1% of remuneration, capped")},
        {"line": _("ETI Claimed"),                   "code": "7006", "amount": 0, "notes": _("Employment Tax Incentive refund — not yet implemented")},
        {"line": _("Total Payable to SARS"),         "code": "",     "amount": 0, "notes": _("PAYE + SDL + UIF(EE+ER) − ETI")},
    ]
