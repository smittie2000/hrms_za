"""
Backfill Leave Policy Assignments for SA Employees who predate v0.0.2.

v0.0.2 added an `Employee.after_insert` hook that auto-assigns the SA
Standard Leave Policy to every new hire. Anyone hired BEFORE the upgrade
won't have been through that flow, so this one-shot patch walks every SA
Employee with a date_of_joining and no active Leave Policy Assignment,
and runs the same assignment path the hook uses.

Shares the helper from `hrms_za.regional.south_africa.leave` — the patch
and the hook never drift apart.

Idempotent by construction: re-running the patch skips any employee whose
active assignment already covers today's date. A tenant can safely re-run
the patch (or leave it to bench migrate) without creating duplicates.
"""

import frappe


def execute():
    # Guard: the required doctypes must be present. On a fresh install they
    # always will be, but a partial upgrade path might land here before the
    # dependent HRMS migration.
    for required in ("Leave Policy Assignment", "Leave Period", "Leave Policy"):
        if not frappe.db.exists("DocType", required):
            print(f"[hrms_za backfill] {required} not yet migrated; skipping.")
            return

    from hrms_za.regional.south_africa.leave import _try_assign_default_policy

    sa_companies = frappe.get_all(
        "Company", filters={"country": "South Africa"}, pluck="name"
    )
    if not sa_companies:
        print("[hrms_za backfill] no SA companies on this site; skipping.")
        return

    employees = frappe.get_all(
        "Employee",
        filters={
            "status": "Active",
            "company": ["in", sa_companies],
            "date_of_joining": ["is", "set"],
        },
        pluck="name",
    )

    created = skipped = failed = 0
    today = frappe.utils.today()

    for emp_name in employees:
        # Skip employees that already have an active LPA covering today
        # (they'd be silently duplicated otherwise — the hook's overlap
        # check would reject, but we want to keep the log clean).
        active = frappe.db.exists(
            "Leave Policy Assignment",
            {
                "employee": emp_name,
                "docstatus": 1,
                "effective_from": ["<=", today],
                "effective_to": [">=", today],
            },
        )
        if active:
            skipped += 1
            continue

        try:
            emp = frappe.get_doc("Employee", emp_name)
            if _try_assign_default_policy(emp):
                created += 1
            else:
                skipped += 1
        except Exception as exc:
            failed += 1
            frappe.log_error(
                title="hrms_za backfill: LPA assignment failed",
                message=f"Employee: {emp_name}\n{exc}",
            )

    print(
        f"[hrms_za backfill] SA Leave Policy Assignments — "
        f"{created} created, {skipped} skipped, {failed} failed."
    )
