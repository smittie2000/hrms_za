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
from hrms_za.regional.south_africa.data.leave_policy import (
    LEAVE_POLICY_DETAILS,
    LEAVE_POLICY_NAME,
)
from hrms_za.regional.south_africa.data.leave_types import LEAVE_TYPES
from hrms_za.regional.south_africa.data.notifications import NOTIFICATIONS
from hrms_za.regional.south_africa.data.salary_components import SALARY_COMPONENTS


# Custom DocPerm rows granted to Employee Self Service on first install.
# Dedupe key is (parent, role, permlevel, if_owner) — Custom DocPerm has no
# unique constraint, so re-runs must check before inserting.
ESS_PERMISSIONS = [
    {
        "parent": "Leave Application",
        "role": "Employee Self Service",
        "permlevel": 0,
        "if_owner": 1,
        "perms": {"read": 1, "write": 1, "create": 1, "submit": 1},
    },
    {
        "parent": "Leave Allocation",
        "role": "Employee Self Service",
        "permlevel": 0,
        "if_owner": 1,
        "perms": {"read": 1},
    },
]


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
    install_leave_policy()
    install_sa_leave_settings_defaults()
    install_notifications()
    install_ess_permissions()


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


def install_leave_policy():
    """
    Seed the `SA Standard Leave Policy` once. Leave Policy is submittable in
    v16 — seeder calls `.insert()` then `.submit()`.

    Leave Policy's autoname in v16 is `HR-LPOL-.YYYY.-.#####`, so the record
    name is auto-generated (e.g. `HR-LPOL-2026-00001`) and the human-readable
    title lives on the `title` field. We lookup by title to honour that.

    Seed-once contract: if any Leave Policy with title == SA Standard Leave
    Policy exists in any state, return. Never reconciles child rows — HR may
    have amended the policy, and the seeder must not fight those edits.

    Must run AFTER `install_leave_types()` in `setup_site_wide()` — child
    rows reference the leave-type records by name.
    """
    if frappe.db.exists("Leave Policy", {"title": LEAVE_POLICY_NAME}):
        return

    doc = frappe.get_doc({
        "doctype": "Leave Policy",
        "title": LEAVE_POLICY_NAME,
        "leave_policy_details": LEAVE_POLICY_DETAILS,
    })
    doc.insert(ignore_permissions=True)
    doc.submit()


def _resolve_sa_standard_leave_policy():
    """
    Return the autogenerated record name of the SA Standard Leave Policy, or
    None if it hasn't been seeded (or was renamed past recognition).

    Callers that need to link to the policy (settings seeder, auto-assign
    hook, bulk helpers) must use this, NEVER hardcode `SA Standard Leave
    Policy` as a record name — that's the title, not the name.
    """
    return frappe.db.get_value(
        "Leave Policy", {"title": LEAVE_POLICY_NAME, "docstatus": 1}, "name"
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

    if not settings.get("default_leave_policy"):
        resolved = _resolve_sa_standard_leave_policy()
        if resolved:
            settings.set("default_leave_policy", resolved)
            changed = True

    if changed:
        settings.save(ignore_permissions=True)


def install_notifications():
    """
    Seed 3 Notification records (submitted / approved / rejected) on Leave
    Application. Message bodies come from sibling HTML files under
    data/email_bodies/ and are inlined into the Notification.message field
    at install time.

    Seed-once contract: if the Notification record exists (by name) we skip,
    so HR can freely amend message bodies or subjects without the seeder
    fighting back.
    """
    import os

    base_path = os.path.join(
        os.path.dirname(__file__), "data", "email_bodies"
    )

    for name, body_file, payload in NOTIFICATIONS:
        if frappe.db.exists("Notification", name):
            continue

        body = frappe.read_file(os.path.join(base_path, body_file))
        frappe.get_doc({
            "doctype": "Notification",
            "name": name,
            "subject": payload["subject"],
            "document_type": payload["document_type"],
            "event": payload["event"],
            "value_changed": payload.get("value_changed"),
            "condition": payload.get("condition"),
            "channel": payload["channel"],
            "enabled": payload["enabled"],
            "message": body or "",
            "recipients": payload["recipients"],
        }).insert(ignore_permissions=True)


def install_ess_permissions():
    """
    Seed Custom DocPerm rows so Employee Self Service users can submit their
    own Leave Applications and see their own Leave Allocations on the ESS
    portal. Dedupe by (parent, role, permlevel, if_owner) — Custom DocPerm
    has no unique constraint so a second install without this check would
    stack duplicate rows and confuse the permission resolver.
    """
    for spec in ESS_PERMISSIONS:
        filters = {
            "parent": spec["parent"],
            "role": spec["role"],
            "permlevel": spec["permlevel"],
            "if_owner": spec["if_owner"],
        }
        if frappe.db.exists("Custom DocPerm", filters):
            continue

        frappe.get_doc({
            "doctype": "Custom DocPerm",
            "parent": spec["parent"],
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role": spec["role"],
            "permlevel": spec["permlevel"],
            "if_owner": spec["if_owner"],
            **spec["perms"],
        }).insert(ignore_permissions=True)


def before_uninstall():
    """
    Teardown seeded app-config state so a reinstall starts clean.

    What this DOES remove:
      - The 3 seeded Notification records (by name).
      - The seeded Custom DocPerm rows (matched on parent/role/permlevel/if_owner).

    What this DELIBERATELY LEAVES behind:
      - Leave Policy Assignments, Leave Allocations, Leave Periods — they're
        tenant data tied to real employees and historical payroll runs.
      - The SA Standard Leave Policy — HR may have amended / renamed it.
      - Custom fields on Employee / Company — removing them would delete
        tenant data (tax numbers, UIF refs, medical aid info).

    The `SA Leave Settings` Single is dropped automatically by Frappe when
    the doctype itself is removed during uninstall.
    """
    for name, _body_file, _payload in NOTIFICATIONS:
        if frappe.db.exists("Notification", name):
            try:
                frappe.delete_doc("Notification", name, ignore_permissions=True)
            except Exception:
                frappe.log_error(
                    title="hrms_za uninstall: Notification removal failed",
                    message=f"Notification: {name}",
                )

    for spec in ESS_PERMISSIONS:
        filters = {
            "parent": spec["parent"],
            "role": spec["role"],
            "permlevel": spec["permlevel"],
            "if_owner": spec["if_owner"],
        }
        for row in frappe.get_all("Custom DocPerm", filters=filters, pluck="name"):
            try:
                frappe.delete_doc(
                    "Custom DocPerm", row, ignore_permissions=True, force=True
                )
            except Exception:
                frappe.log_error(
                    title="hrms_za uninstall: Custom DocPerm removal failed",
                    message=f"Custom DocPerm: {row}",
                )


# ---------------------------------------------------------------------------
# Per-company setup
# ---------------------------------------------------------------------------

def setup_per_company(company):
    install_income_tax_slabs(company)
    install_leave_period_for_current_year(company)


def install_leave_period_for_current_year(company):
    """
    Seed a Leave Period covering the current leave-cycle window for `company`.

    The cycle window is derived from `SA Leave Settings.cycle_start_month` +
    `cycle_start_day` (defaults 1 January). For a cycle start of 1 Jan and
    today in mid-2026, the resulting window is 2026-01-01 → 2026-12-31.

    Leave Period's autoname in v16 is `HR-LPR-.YYYY.-.#####`, so the record
    name is auto-generated — we identify an existing period by
    (company, from_date) instead of by a scoped record name.

    Idempotency: if a Leave Period exists for this company with the same
    from_date, return. Never touches existing periods.
    """
    from_date, to_date = _current_cycle_window_for_date(frappe.utils.today())

    if frappe.db.exists(
        "Leave Period",
        {"company": company, "from_date": from_date},
    ):
        return

    doc = frappe.get_doc({
        "doctype": "Leave Period",
        "from_date": from_date,
        "to_date": to_date,
        "company": company,
        "is_active": 1,
    })
    doc.insert(ignore_permissions=True)


def _current_cycle_window_for_date(reference_date):
    """
    Return (from_date, to_date) for the leave cycle containing `reference_date`,
    using `SA Leave Settings.cycle_start_month` / `cycle_start_day`.

    If reference_date's month/day is on or after the cycle anchor, the window
    starts in `reference_date.year` and ends one day before the anchor in the
    following year. Otherwise the cycle started in the previous year.

    Feb 29 anchors are normalised to Feb 28 in non-leap years. Any other
    invalid month/day combo is blocked upstream by SALeaveSettings.validate().
    """
    from datetime import date

    from frappe.utils import add_days, getdate

    ref = getdate(reference_date)

    settings = frappe.get_cached_doc("SA Leave Settings")
    month = int(settings.get("cycle_start_month") or 1)
    day = int(settings.get("cycle_start_day") or 1)

    def anchor_in_year(year):
        try:
            return date(year, month, day)
        except ValueError:
            # Feb 29 in a non-leap year → Feb 28.
            return date(year, month, day - 1)

    current_anchor = anchor_in_year(ref.year)
    if ref >= current_anchor:
        from_date = current_anchor
        to_date = add_days(anchor_in_year(ref.year + 1), -1)
    else:
        from_date = anchor_in_year(ref.year - 1)
        to_date = add_days(current_anchor, -1)

    return from_date, to_date


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
