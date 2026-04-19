"""
EMP501 Reconciliation — placeholder.

Bi-annual SARS reconciliation: EMP201 declarations vs actual payments vs
employee tax certificates (IRP5 / IT3(a)). The real output is a CSV import
for SARS e@syFile. This placeholder ships the summary-per-employee columns
management expects to see on the Desk.
"""

import frappe
from frappe import _


def execute(filters=None):
    return get_columns(), []


def get_columns():
    return [
        {"label": _("Employee"),        "fieldname": "employee",         "fieldtype": "Link",     "options": "Employee", "width": 130},
        {"label": _("Full Name"),        "fieldname": "employee_name",    "fieldtype": "Data",     "width": 180},
        {"label": _("SARS Tax No."),     "fieldname": "sa_tax_reference", "fieldtype": "Data",     "width": 120},
        {"label": _("Total Remun."),     "fieldname": "total_remuneration","fieldtype": "Currency","width": 140},
        {"label": _("PAYE Declared"),    "fieldname": "paye_declared",    "fieldtype": "Currency", "width": 140},
        {"label": _("PAYE on Cert."),    "fieldname": "paye_on_cert",     "fieldtype": "Currency", "width": 140},
        {"label": _("PAYE Paid"),        "fieldname": "paye_paid",        "fieldtype": "Currency", "width": 140},
        {"label": _("Variance"),         "fieldname": "variance",         "fieldtype": "Currency", "width": 140},
        {"label": _("Status"),           "fieldname": "status",           "fieldtype": "Data",     "width": 140},
    ]
