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
    install_sa_leave_settings_defaults()


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


def install_sa_leave_settings_defaults():
    """
    Populate SA Leave Settings (Single) with sensible first-run defaults.

    Contract: only fill fields that are currently empty. HR edits survive
    re-install. The DocType ships `default` attributes on every field — this
    seeder just promotes those defaults from "render hint" to persisted value
    so downstream `frappe.get_single(...)` always sees concrete data.

    `default_leave_policy` is special: only set if the policy record exists.
    `install_leave_policy()` (step 2 of the plan) seeds the policy earlier in
    `setup_site_wide()`, so the link target is normally available by the time
    this runs. Guarded anyway — re-installs where the policy was deleted
    shouldn't clobber the link with a dangling value.
    """
    defaults = {
        "enabled": 1,
        "auto_assign_policy_on_hire": 1,
        "cycle_start_month": 1,
        "cycle_start_day": 1,
        "sick_cycle_months": 36,
        "sick_days_per_cycle": 30,
        "low_balance_threshold_days": 3,
        "annual_leave_carry_forward_max": 5,
        "two_step_approval_threshold_days": 10,
        "default_approver_fallback_role": "HR Manager",
    }

    settings = frappe.get_single("SA Leave Settings")
    changed = False

    for fieldname, value in defaults.items():
        if not settings.get(fieldname):
            settings.set(fieldname, value)
            changed = True

    if not settings.get("default_leave_policy") and frappe.db.exists(
        "Leave Policy", "SA Standard Leave Policy"
    ):
        settings.set("default_leave_policy", "SA Standard Leave Policy")
        changed = True

    if changed:
        settings.save(ignore_permissions=True)


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

    Income Tax Slab is submittable in v16; Salary Structure Assignment only
    accepts submitted slabs. Insert + submit in one shot.
    """
    for definition in INCOME_TAX_SLABS:
        payload = dict(definition)
        slabs = payload.pop("slabs")
        base_name = payload.pop("name")
        name = f"{base_name} - {company}"

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
        doc.submit()
