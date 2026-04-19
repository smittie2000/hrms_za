"""
IRP5 / IT3(a) Employee Tax Certificate — placeholder.

Annual employee tax certificate with SARS source codes (3601 salary, 3605 bonus,
3697 gross remuneration, 3698, 4101/4102/4103 deductions, 4116 medical credit,
etc.). Ships the source-code column shape; aggregation TODO.
"""

import frappe
from frappe import _


def execute(filters=None):
    return get_columns(), []


def get_columns():
    return [
        {"label": _("Source Code"),        "fieldname": "source_code",        "fieldtype": "Data",     "width": 110},
        {"label": _("Description"),        "fieldname": "description",        "fieldtype": "Data",     "width": 260},
        {"label": _("Amount (ZAR)"),       "fieldname": "amount",             "fieldtype": "Currency", "width": 160},
        {"label": _("Certificate Type"),   "fieldname": "certificate_type",   "fieldtype": "Data",     "width": 140},
        {"label": _("Notes"),              "fieldname": "notes",              "fieldtype": "Data",     "width": 300},
    ]
