"""
Backfill Leave Policy Assignments for SA Employees who predate v0.0.2.

v0.0.2 added an `Employee.after_insert` hook that auto-assigns the SA
Standard Leave Policy to every new hire. Anyone hired BEFORE the upgrade
won't have been through that flow, so this one-shot patch walks every SA
Employee with a date_of_joining and no active Leave Policy Assignment,
and runs the same assignment path the hook uses.

Shares `_apply_policy_for_employee` from `hrms_za.regional.south_africa.leave`
so the patch and the hook can never drift on guard logic.

Idempotent by construction: re-running the patch skips any employee whose
active assignment already covers today's date. A tenant can safely re-run
the patch (or leave it to bench migrate) without creating duplicates.
"""

import frappe


def execute():
    # Guard: required doctypes must be present. On a fresh install they
    # always will be, but a partial upgrade path might land here before
    # the dependent HRMS migration.
    for required in ("Leave Policy Assignment", "Leave Period", "Leave Policy"):
        if not frappe.db.exists("DocType", required):
            print(f"[hrms_za backfill] {required} not yet migrated; skipping.")
            return

    from hrms_za.regional.south_africa.leave import (
        _apply_policy_for_employee,
        _POLICY_APPLIED,
        _resolve_current_leave_period,
    )
    from hrms_za.regional.south_africa.setup import (
        resolve_sa_standard_leave_policy,
    )

    sa_companies = frappe.get_all(
        "Company", filters={"country": "South Africa"}, pluck="name"
    )
    if not sa_companies:
        print("[hrms_za backfill] no SA companies on this site; skipping.")
        return

    settings = frappe.get_cached_doc("SA Leave Settings")
    if not settings.get("enabled") or not settings.get("auto_assign_policy_on_hire"):
        # Honour the runtime kill-switches, same as the after_insert hook.
        # Tenant can toggle them on, then re-run `bench migrate` to backfill.
        print("[hrms_za backfill] SA Leave Settings disabled; skipping.")
        return

    policy_name = (
        settings.get("default_leave_policy")
        or resolve_sa_standard_leave_policy()
    )

    employees = frappe.get_all(
        "Employee",
        filters={
            "status": "Active",
            "company": ["in", sa_companies],
            "date_of_joining": ["is", "set"],
        },
        fields=["name", "company", "date_of_joining"],
    )
    if not employees:
        print("[hrms_za backfill] no SA employees to backfill.")
        return

    # Resolve the current leave period once per company instead of per employee.
    period_by_company = {
        c: _resolve_current_leave_period(c) for c in sa_companies
    }

    # Single query for all already-covered employees, instead of one
    # frappe.db.exists() round-trip per employee.
    today = frappe.utils.today()
    covered = set(frappe.get_all(
        "Leave Policy Assignment",
        filters={
            "docstatus": 1,
            "employee": ["in", [e.name for e in employees]],
            "effective_from": ["<=", today],
            "effective_to": [">=", today],
        },
        pluck="employee",
    ))

    created = skipped = failed = 0

    for emp in employees:
        if emp.name in covered:
            skipped += 1
            continue

        try:
            status = _apply_policy_for_employee(
                emp, policy_name, period_by_company.get(emp.company),
            )
            if status == _POLICY_APPLIED:
                created += 1
            else:
                skipped += 1
        except Exception as exc:
            failed += 1
            frappe.log_error(
                title="hrms_za backfill: LPA assignment failed",
                message=f"Employee: {emp.name}\n{exc}",
            )

    print(
        f"[hrms_za backfill] SA Leave Policy Assignments — "
        f"{created} created, {skipped} skipped, {failed} failed."
    )
