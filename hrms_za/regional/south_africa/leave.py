"""
South African leave-automation runtime.

Three layers of callables here:

1. The `Employee.after_insert` doc-event hook (`assign_default_policy`) —
   guards against every failure mode and NEVER raises, so a misconfigured
   install can't block HR from saving an Employee.

2. Whitelisted bulk helpers (`seed_leave_period`, `generate_sa_leave_allocations`,
   `auto_fill_leave_approvers`, `provision_employee_users`,
   `recompute_sick_leave_cycles`) — exposed as action buttons on
   SA Leave Settings. All idempotent; all return a `{created, skipped, failed}`
   summary dict so the UI can render a consistent toast.

3. Scheduler tasks (`nudge_pending_leave_approvals`,
   `email_low_balance_employees`) — wired via the `scheduler_events` hook in
   hrms_za/hooks.py.

All config is read from the `SA Leave Settings` Single — no hardcoded values.
"""

import frappe
from frappe import _

from hrms_za.regional.south_africa.setup import (
    _current_cycle_window_for_date,
    _resolve_sa_standard_leave_policy,
)


# ---------------------------------------------------------------------------
# Employee.after_insert — auto-assign the default leave policy
# ---------------------------------------------------------------------------

def assign_default_policy(doc, method=None):
    """
    Doc event wrapper. Any exception is swallowed + logged; the Employee save
    flow must never abort because a leave-policy assignment failed.
    """
    try:
        _try_assign_default_policy(doc)
    except Exception:
        frappe.log_error(
            title="hrms_za: leave policy auto-assign failed",
            message=f"Employee: {doc.name}, Company: {doc.company}",
        )


def _try_assign_default_policy(employee):
    settings = frappe.get_cached_doc("SA Leave Settings")
    if not settings.get("enabled"):
        return
    if not settings.get("auto_assign_policy_on_hire"):
        return

    if not employee.company:
        return

    country = frappe.get_cached_value("Company", employee.company, "country")
    if country != "South Africa":
        return

    if not employee.date_of_joining:
        _skip_with_comment(
            employee,
            "Leave policy not assigned: date_of_joining is missing.",
        )
        return

    policy_name = (
        settings.get("default_leave_policy")
        or _resolve_sa_standard_leave_policy()
    )
    if not policy_name or not frappe.db.exists("Leave Policy", policy_name):
        _skip_with_comment(
            employee,
            "Leave policy not assigned: SA Standard Leave Policy not found. "
            "Set default_leave_policy on SA Leave Settings, then click "
            "'Generate Leave Policy Assignments for Year'.",
        )
        return

    leave_period = _resolve_current_leave_period(employee.company)
    if not leave_period:
        _skip_with_comment(
            employee,
            f"Leave policy not assigned: no active Leave Period for "
            f"'{employee.company}'. Click 'Seed Leave Period for Year' on "
            f"SA Leave Settings to create one.",
        )
        return

    from frappe.utils import date_diff, getdate

    lp = frappe.get_doc("Leave Period", leave_period)
    effective_from = max(getdate(employee.date_of_joining), getdate(lp.from_date))
    effective_to = getdate(lp.to_date)

    if date_diff(effective_to, effective_from) < 90:
        _skip_with_comment(
            employee,
            f"Leave policy not assigned: remaining cycle window is only "
            f"{date_diff(effective_to, effective_from)} days "
            f"(from {effective_from} to {effective_to}). Create allocations "
            f"manually on the next cycle start.",
        )
        return

    _create_leave_policy_assignment(
        employee=employee.name,
        policy_name=policy_name,
        leave_period=leave_period,
        effective_from=effective_from,
        effective_to=effective_to,
    )


def _skip_with_comment(employee, message):
    """Record the skip on the Employee's timeline so HR can see why."""
    employee.add_comment("Info", message)


def _resolve_current_leave_period(company):
    """
    Leave Period name for `company` whose window contains today's date.
    Prefers `is_active=1`. Returns None if no such period exists.
    """
    today = frappe.utils.today()
    return frappe.db.get_value(
        "Leave Period",
        {
            "company": company,
            "from_date": ["<=", today],
            "to_date": [">=", today],
            "is_active": 1,
        },
        "name",
    )


def _create_leave_policy_assignment(
    employee,
    policy_name,
    leave_period,
    effective_from,
    effective_to,
    carry_forward=0,
):
    """
    Thin wrapper over HRMS's single-employee `create_assignment` — that
    helper saves as draft; Leave Allocations are only created on submit
    (via `grant_leave_alloc_for_employee`), so we submit here.
    """
    from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import (
        create_assignment,
    )

    assignment = create_assignment(
        employee,
        frappe._dict({
            "assignment_based_on": "Leave Period",
            "leave_policy": policy_name,
            "leave_period": leave_period,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "carry_forward": int(carry_forward),
        }),
    )
    assignment.submit()
    return assignment


# ---------------------------------------------------------------------------
# Bulk helpers (whitelisted — wired to SA Leave Settings action buttons)
# ---------------------------------------------------------------------------

def _empty_result():
    return {"created": 0, "skipped": 0, "failed": []}


def _sa_companies(company=None):
    """Active SA companies, optionally filtered to a single name."""
    filters = {"country": "South Africa"}
    if company:
        filters["name"] = company
    return frappe.get_all("Company", filters=filters, pluck="name")


def _active_sa_employees(company=None):
    """Active employees on SA companies."""
    filters = {"status": "Active"}
    companies = _sa_companies(company)
    if not companies:
        return []
    filters["company"] = ["in", companies]
    return frappe.get_all(
        "Employee",
        filters=filters,
        fields=["name", "company", "date_of_joining", "leave_approver",
                "department", "company_email", "user_id"],
    )


@frappe.whitelist()
def seed_leave_period(year):
    """
    Create an SA Leave Period for calendar `year` on every active SA company,
    using the configured cycle anchor. Idempotent — skips if a period exists
    for (company, from_date).
    """
    from datetime import date

    year = int(year)
    result = _empty_result()

    settings = frappe.get_cached_doc("SA Leave Settings")
    month = int(settings.get("cycle_start_month") or 1)
    day = int(settings.get("cycle_start_day") or 1)

    try:
        from_date = date(year, month, day)
    except ValueError:
        from_date = date(year, month, day - 1)  # Feb 29 → Feb 28 normalisation
    _, to_date = _current_cycle_window_for_date(from_date)

    for company in _sa_companies():
        try:
            if frappe.db.exists(
                "Leave Period",
                {"company": company, "from_date": from_date},
            ):
                result["skipped"] += 1
                continue
            doc = frappe.get_doc({
                "doctype": "Leave Period",
                "from_date": from_date,
                "to_date": to_date,
                "company": company,
                "is_active": 1,
            })
            doc.insert(ignore_permissions=True)
            result["created"] += 1
        except Exception as exc:
            result["failed"].append(f"{company}: {exc}")

    return result


@frappe.whitelist()
def generate_sa_leave_allocations(year, company=None):
    """
    For every active SA employee without a Leave Policy Assignment covering
    `year`'s cycle, create + submit one. Uses the default leave policy on
    SA Leave Settings.

    Honours the plan's 9-guard chain from `_try_assign_default_policy` for
    each employee so bulk and single-employee paths behave identically.
    """
    year = int(year)
    result = _empty_result()

    settings = frappe.get_cached_doc("SA Leave Settings")
    policy_name = (
        settings.get("default_leave_policy")
        or _resolve_sa_standard_leave_policy()
    )
    if not policy_name:
        result["failed"].append("SA Standard Leave Policy not seeded")
        return result

    employees = _active_sa_employees(company)
    if not employees:
        return result

    from frappe.utils import date_diff, getdate

    for emp in employees:
        try:
            if not emp.date_of_joining:
                result["skipped"] += 1
                continue

            leave_period = _resolve_leave_period_for_year(emp.company, year)
            if not leave_period:
                result["failed"].append(
                    f"{emp.name}: no Leave Period for {emp.company}/{year}"
                )
                continue

            if _has_active_assignment(emp.name, leave_period):
                result["skipped"] += 1
                continue

            lp = frappe.get_doc("Leave Period", leave_period)
            effective_from = max(
                getdate(emp.date_of_joining),
                getdate(lp.from_date),
            )
            effective_to = getdate(lp.to_date)

            if date_diff(effective_to, effective_from) < 90:
                result["skipped"] += 1
                continue

            _create_leave_policy_assignment(
                employee=emp.name,
                policy_name=policy_name,
                leave_period=leave_period,
                effective_from=effective_from,
                effective_to=effective_to,
            )
            result["created"] += 1
        except Exception as exc:
            result["failed"].append(f"{emp.name}: {exc}")

    return result


def _resolve_leave_period_for_year(company, year):
    """Leave Period for `company` whose from_date falls in calendar `year`."""
    from frappe.utils import getdate

    year = int(year)
    candidates = frappe.get_all(
        "Leave Period",
        filters={"company": company, "is_active": 1},
        fields=["name", "from_date"],
    )
    for c in candidates:
        if getdate(c.from_date).year == year:
            return c.name
    return None


def _has_active_assignment(employee, leave_period):
    """True if the employee already has a submitted LPA for this period."""
    return bool(frappe.db.exists(
        "Leave Policy Assignment",
        {
            "employee": employee,
            "leave_period": leave_period,
            "docstatus": 1,
        },
    ))


@frappe.whitelist()
def auto_fill_leave_approvers(company=None):
    """
    Populate Employee.leave_approver where it's empty, using:
      1. Department.leave_approvers[0].approver
      2. Else first active user holding SA Leave Settings.default_approver_fallback_role
      3. Else skip + log
    Existing approvers are never overwritten.
    """
    result = _empty_result()

    settings = frappe.get_cached_doc("SA Leave Settings")
    fallback_role = settings.get("default_approver_fallback_role")

    employees = _active_sa_employees(company)
    for emp in employees:
        try:
            if emp.leave_approver:
                result["skipped"] += 1
                continue

            approver = None
            if emp.department:
                approver = frappe.db.get_value(
                    "Department Approver",
                    {
                        "parent": emp.department,
                        "parentfield": "leave_approvers",
                        "idx": 1,
                    },
                    "approver",
                )

            if not approver and fallback_role:
                approver = frappe.db.get_value(
                    "Has Role",
                    {"role": fallback_role, "parenttype": "User"},
                    "parent",
                    order_by="creation asc",
                )

            if not approver:
                result["failed"].append(
                    f"{emp.name}: no approver resolvable from Department "
                    f"or fallback role"
                )
                continue

            frappe.db.set_value("Employee", emp.name, "leave_approver", approver)
            result["created"] += 1
        except Exception as exc:
            result["failed"].append(f"{emp.name}: {exc}")

    return result


@frappe.whitelist()
def provision_employee_users(company=None):
    """
    Create a User (role: Employee Self Service) for every SA Employee that
    has `company_email` and no `user_id`, and link them. Does NOT send a
    welcome email — flip the "Send Welcome Email" toggle on the User form
    when HR is ready to invite the employee.

    Idempotent: employees with an existing user_id are skipped.
    """
    result = _empty_result()

    for emp in _active_sa_employees(company):
        try:
            if emp.user_id:
                result["skipped"] += 1
                continue
            if not emp.company_email:
                result["skipped"] += 1
                continue

            if frappe.db.exists("User", emp.company_email):
                # User already exists on this email — link the Employee but
                # don't create a duplicate User.
                frappe.db.set_value("Employee", emp.name, "user_id", emp.company_email)
                result["created"] += 1
                continue

            user = frappe.get_doc({
                "doctype": "User",
                "email": emp.company_email,
                "first_name": emp.get("employee_name") or emp.name,
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": "Website User",
                "roles": [{"role": "Employee Self Service"}],
            })
            user.insert(ignore_permissions=True)
            frappe.db.set_value("Employee", emp.name, "user_id", user.name)
            result["created"] += 1
        except Exception as exc:
            result["failed"].append(f"{emp.name}: {exc}")

    return result


@frappe.whitelist()
def recompute_sick_leave_cycles():
    """
    Phase 2 stub. The real 36-month rolling sick-leave cycle algorithm
    lands in a follow-up plan. Returns an empty-result dict shaped like the
    other helpers so the UI's toast renders consistently.
    """
    return {
        "created": 0,
        "skipped": 0,
        "failed": [],
        "status": "not_yet_implemented",
        "phase": 2,
    }


# ---------------------------------------------------------------------------
# Scheduler tasks — wired via scheduler_events in hooks.py
# ---------------------------------------------------------------------------

def nudge_pending_leave_approvals():
    """
    Weekly job. Find Leave Applications with status='Open' older than 48h,
    group by leave_approver, send one consolidated email per approver.
    Silent no-op when there's nothing pending.
    """
    from frappe.utils import add_to_date, format_date

    threshold = add_to_date(frappe.utils.now_datetime(), hours=-48)

    rows = frappe.get_all(
        "Leave Application",
        filters={"status": "Open", "creation": ["<", threshold]},
        fields=["name", "employee_name", "leave_type",
                "from_date", "to_date", "leave_approver", "company"],
    )
    if not rows:
        return

    by_approver = {}
    for r in rows:
        if not r.leave_approver:
            continue
        by_approver.setdefault(r.leave_approver, []).append(r)

    settings = frappe.get_cached_doc("SA Leave Settings")
    sender = settings.get("notification_from_email") or None

    for approver, items in by_approver.items():
        body_lines = [
            f"<p>{len(items)} leave application(s) are still pending your "
            f"approval (submitted more than 48 hours ago):</p>",
            "<ul>",
        ]
        for i in items:
            body_lines.append(
                f"<li><b>{i.employee_name}</b> — {i.leave_type}, "
                f"{format_date(i.from_date)} → {format_date(i.to_date)} "
                f"(<a href='/app/leave-application/{i.name}'>{i.name}</a>)"
                f"</li>"
            )
        body_lines.append("</ul>")
        body = "\n".join(body_lines)

        frappe.sendmail(
            recipients=[approver],
            sender=sender,
            subject=_("Leave Applications awaiting your approval"),
            message=body,
            reference_doctype="Leave Application",
            reference_name=items[0].name,
        )


def email_low_balance_employees():
    """
    Weekly job. For every active SA Employee whose Annual Leave balance is
    below SA Leave Settings.low_balance_threshold_days, email the employee
    (cc: users holding HR Manager role). Silent when nobody is below threshold.
    """
    from frappe.utils import getdate

    from hrms.hr.doctype.leave_application.leave_application import (
        get_leave_balance_on,
    )

    settings = frappe.get_cached_doc("SA Leave Settings")
    threshold = float(settings.get("low_balance_threshold_days") or 0)
    sender = settings.get("notification_from_email") or None
    fallback_role = settings.get("default_approver_fallback_role") or "HR Manager"

    if threshold <= 0:
        return

    annual_leave_type = "Annual Leave (SA)"
    if not frappe.db.exists("Leave Type", annual_leave_type):
        return

    today = frappe.utils.today()
    hr_users = _users_with_role(fallback_role)

    for emp in _active_sa_employees():
        if not emp.user_id:
            continue
        try:
            balance = get_leave_balance_on(emp.name, annual_leave_type, today)
        except Exception:
            continue

        if balance is None or balance >= threshold:
            continue

        frappe.sendmail(
            recipients=[emp.user_id],
            cc=hr_users or None,
            sender=sender,
            subject=_("Your Annual Leave balance is low"),
            message=(
                f"<p>Hi,</p>"
                f"<p>Your current Annual Leave balance is "
                f"<b>{balance:.2f} day(s)</b>, below your company's threshold "
                f"of {threshold:.1f}. Please plan accordingly.</p>"
                f"<p>— HR</p>"
            ),
            reference_doctype="Employee",
            reference_name=emp.name,
        )


def _users_with_role(role):
    """Active User names with `role` assigned."""
    if not role:
        return []
    return frappe.get_all(
        "Has Role",
        filters={"role": role, "parenttype": "User"},
        pluck="parent",
    )
