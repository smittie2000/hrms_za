"""
South African regional setup for Frappe HRMS v16.

Entry points:
- after_install: fires once when hrms_za is installed; runs site-wide setup
  and per-company setup for any existing SA Company.
- on_company_update: fires whenever a Company is saved; runs setup if
  country == "South Africa". Safe to re-run (all operations idempotent).

All operations are upserts. Re-running this module must never duplicate records
or raise — that's a hard requirement for the install/upgrade flow.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from hrms_za.regional.south_africa.data.custom_fields import get_custom_fields
from hrms_za.regional.south_africa.data.employment_types import EMPLOYMENT_TYPES
from hrms_za.regional.south_africa.data.income_tax_slab import INCOME_TAX_SLABS
from hrms_za.regional.south_africa.data.leave_types import LEAVE_TYPES
from hrms_za.regional.south_africa.data.salary_components import SALARY_COMPONENTS


# ---------------------------------------------------------------------------
# Entry points wired from hooks.py
# ---------------------------------------------------------------------------

def after_install():
    """Run SA setup for every existing SA company at app install time."""
    setup_site_wide()
    for company in frappe.get_all(
        "Company", filters={"country": "South Africa"}, pluck="name"
    ):
        setup_per_company(company)


def on_company_update(doc, method=None):
    """Re-run setup whenever a Company is saved with country=South Africa."""
    if doc.country != "South Africa":
        return
    setup_site_wide()
    setup_per_company(doc.name)


# ---------------------------------------------------------------------------
# Site-wide setup — runs once, independent of Company
# ---------------------------------------------------------------------------

def setup_site_wide():
    install_custom_fields()
    install_employment_types()
    install_leave_types()
    install_salary_components()


def install_custom_fields():
    create_custom_fields(get_custom_fields(), update=True)


def install_employment_types():
    for name in EMPLOYMENT_TYPES:
        if not frappe.db.exists("Employment Type", name):
            frappe.get_doc({
                "doctype": "Employment Type",
                "employee_type_name": name,
            }).insert(ignore_permissions=True)


def install_leave_types():
    for payload in LEAVE_TYPES:
        name = payload["leave_type_name"]
        if frappe.db.exists("Leave Type", name):
            doc = frappe.get_doc("Leave Type", name)
            doc.update(payload)
            doc.save(ignore_permissions=True)
        else:
            frappe.get_doc({"doctype": "Leave Type", **payload}).insert(
                ignore_permissions=True
            )


def install_salary_components():
    for payload in SALARY_COMPONENTS:
        name = payload["salary_component"]
        if frappe.db.exists("Salary Component", name):
            doc = frappe.get_doc("Salary Component", name)
            doc.update(payload)
            doc.save(ignore_permissions=True)
        else:
            frappe.get_doc({"doctype": "Salary Component", **payload}).insert(
                ignore_permissions=True
            )


# ---------------------------------------------------------------------------
# Per-company setup
# ---------------------------------------------------------------------------

def setup_per_company(company):
    install_income_tax_slabs(company)


def install_income_tax_slabs(company):
    """
    Create an Income Tax Slab per SARS tax year, per company. Never overwrite
    an existing record — the tenant may have tweaked thresholds, toggled
    disabled, or reassigned the slab to a Payroll Period.
    """
    for definition in INCOME_TAX_SLABS:
        payload = dict(definition)
        slabs = payload.pop("slabs")
        name = f"{payload['name']} - {company}"

        if frappe.db.exists("Income Tax Slab", name):
            continue

        doc = frappe.get_doc({
            "doctype": "Income Tax Slab",
            "name": name,
            "company": company,
            **payload,
            "slabs": [
                {"doctype": "Taxable Salary Slab", **s} for s in slabs
            ],
        })
        doc.insert(ignore_permissions=True)
