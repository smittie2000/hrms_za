"""
South African leave-automation runtime.

Layout:
- `assign_default_policy` runs from Employee.after_insert; the try/except
  wrapper exists because a misconfigured install must never block HR from
  saving an Employee record.
- Bulk helpers are whitelisted; all return `{created, skipped, failed}`
  so sa_leave_settings.js can render a uniform toast.
- Scheduler tasks at the bottom wire to scheduler_events in hooks.py.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate
from frappe.utils.user import get_users_with_role

from hrms_za.regional.south_africa.data.leave_types import (
    ANNUAL_LEAVE_TYPE,
    HR_MANAGER_ROLE,
)
from hrms_za.regional.south_africa.setup import (
    anchor_date,
    current_cycle_window_for_date,
    resolve_sa_standard_leave_policy,
)


_POLICY_APPLIED = "applied"
_POLICY_SKIPPED_NO_DOJ = "no_doj"
_POLICY_SKIPPED_NO_POLICY = "no_policy"
_POLICY_SKIPPED_NO_PERIOD = "no_period"
_POLICY_SKIPPED_SHORT_TENURE = "short_tenure"

_FAILED_LIST_CAP = 100


# ---------------------------------------------------------------------------
# Employee.after_insert — auto-assign the default leave policy
# ---------------------------------------------------------------------------

def assign_default_policy(doc, method=None):
    """Doc event wrapper. Any exception is swallowed + logged."""
    try:
        _try_assign_default_policy(doc)
    except Exception:
        frappe.log_error(
            title="hrms_za: leave policy auto-assign failed",
            message=f"Employee: {doc.name}, Company: {doc.company}",
        )


def _try_assign_default_policy(employee):
    """
    Resolve the assignment context for one Employee, apply it, and record any
    guard-triggered skip as a Comment on the Employee timeline. Returns True
    iff a Leave Policy Assignment was created + submitted.
    """
    settings = frappe.get_cached_doc("SA Leave Settings")
    if not settings.get("enabled"):
        return False
    if not settings.get("auto_assign_policy_on_hire"):
        return False
    if not employee.company:
        return False

    country = frappe.get_cached_value("Company", employee.company, "country")
    if country != "South Africa":
        return False

    policy_name = (
        settings.get("default_leave_policy")
        or resolve_sa_standard_leave_policy()
    )

    period = _resolve_current_leave_period(employee.company)

    status = _apply_policy_for_employee(employee, policy_name, period)
    if status == _POLICY_APPLIED:
        return True

    period_to = period.to_date if period else None
    employee.add_comment("Info", _policy_skip_message(status, employee, period_to))
    return False


def _apply_policy_for_employee(emp, policy_name, period):
    """
    Run the guard chain and create + submit a Leave Policy Assignment if all
    guards pass. Returns one of the `_POLICY_*` status constants.

    `emp` is a full Employee doc OR a _dict from `get_all` — both expose the
    same `.name` / `.date_of_joining` attribute access. `period` is a dict
    (or frappe._dict) with `.name` / `.from_date` / `.to_date`, or None.
    """
    if not emp.date_of_joining:
        return _POLICY_SKIPPED_NO_DOJ

    if not policy_name or not frappe.db.exists("Leave Policy", policy_name):
        return _POLICY_SKIPPED_NO_POLICY

    if not period:
        return _POLICY_SKIPPED_NO_PERIOD

    effective_from = max(getdate(emp.date_of_joining), getdate(period.from_date))
    effective_to = getdate(period.to_date)
    if date_diff(effective_to, effective_from) < 90:
        return _POLICY_SKIPPED_SHORT_TENURE

    _create_leave_policy_assignment(
        employee=emp.name,
        policy_name=policy_name,
        leave_period=period.name,
        effective_from=effective_from,
        effective_to=effective_to,
    )
    return _POLICY_APPLIED


def _policy_skip_message(status, employee, period_to):
    if status == _POLICY_SKIPPED_NO_DOJ:
        return "Leave policy not assigned: date_of_joining is missing."
    if status == _POLICY_SKIPPED_NO_POLICY:
        return (
            "Leave policy not assigned: SA Standard Leave Policy not found. "
            "Set default_leave_policy on SA Leave Settings."
        )
    if status == _POLICY_SKIPPED_NO_PERIOD:
        return (
            f"Leave policy not assigned: no active Leave Period for "
            f"'{employee.company}'."
        )
    if status == _POLICY_SKIPPED_SHORT_TENURE:
        remaining = date_diff(getdate(period_to), getdate(employee.date_of_joining))
        return (
            f"Leave policy not assigned: remaining cycle window is only "
            f"{remaining} days. Create allocations manually on next cycle start."
        )
    return f"Leave policy not assigned (status: {status})"


def _resolve_current_leave_period(company):
    """
    Active Leave Period (name + from_date + to_date) whose window contains
    today, for `company`. None if no period covers today.

    Delegates to HRMS's canonical helper so we benefit from any upstream
    fixes (overlap semantics, edge-case Leave Period configs).
    """
    from hrms.hr.utils import get_leave_period

    today = frappe.utils.today()
    periods = get_leave_period(today, today, company)
    return periods[0] if periods else None


def _create_leave_policy_assignment(
    employee, policy_name, leave_period, effective_from, effective_to,
    carry_forward=0,
):
    """
    Wrapper over HRMS's `create_assignment`. The upstream helper saves as
    draft; Leave Allocations only materialise on submit, so we submit here.
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


def _record_failure(result, message):
    """Append a failure reason to `result['failed']`, capped at _FAILED_LIST_CAP."""
    failed = result["failed"]
    if len(failed) < _FAILED_LIST_CAP:
        failed.append(message)
    elif len(failed) == _FAILED_LIST_CAP:
        failed.append("… (further failures suppressed)")


def _sa_companies(company=None):
    filters = {"country": "South Africa"}
    if company:
        filters["name"] = company
    return frappe.get_all("Company", filters=filters, pluck="name")


def _active_sa_employees(company=None, with_user_id=False):
    """
    Active SA Employees (across one or all SA companies).

    `with_user_id=True` filters out employees with no linked User — the
    weekly low-balance email job has nowhere to send if user_id is blank,
    so do that filter at the SQL level rather than discarding rows after
    fetching balances.
    """
    companies = _sa_companies(company)
    if not companies:
        return []
    filters = {"status": "Active", "company": ["in", companies]}
    if with_user_id:
        filters["user_id"] = ["is", "set"]
    return frappe.get_all(
        "Employee",
        filters=filters,
        fields=["name", "company", "date_of_joining", "leave_approver",
                "department", "company_email", "user_id", "employee_name"],
    )


@frappe.whitelist()
def seed_leave_period(year):
    """
    Seed an SA Leave Period for calendar `year` on every active SA company
    using the configured cycle anchor. Idempotent — skips if a period exists
    for (company, from_date).
    """
    year = int(year)
    result = _empty_result()

    settings = frappe.get_cached_doc("SA Leave Settings")
    month = int(settings.get("cycle_start_month") or 1)
    day = int(settings.get("cycle_start_day") or 1)

    from_date = anchor_date(year, month, day)
    _, to_date = current_cycle_window_for_date(from_date)

    for company in _sa_companies():
        try:
            if frappe.db.exists(
                "Leave Period",
                {"company": company, "from_date": from_date},
            ):
                result["skipped"] += 1
                continue
            frappe.get_doc({
                "doctype": "Leave Period",
                "from_date": from_date,
                "to_date": to_date,
                "company": company,
                "is_active": 1,
            }).insert(ignore_permissions=True)
            result["created"] += 1
        except Exception as exc:
            _record_failure(result, f"{company}: {exc}")

    return result


@frappe.whitelist()
def generate_sa_leave_allocations(year, company=None):
    """
    For every active SA employee without a Leave Policy Assignment in
    `year`'s cycle, create + submit one. Same guard chain as the
    `after_insert` hook, batched with prefetched Leave Period data.
    """
    year = int(year)
    result = _empty_result()

    settings = frappe.get_cached_doc("SA Leave Settings")
    policy_name = (
        settings.get("default_leave_policy")
        or resolve_sa_standard_leave_policy()
    )
    if not policy_name:
        _record_failure(result, "SA Standard Leave Policy not seeded")
        return result

    employees = _active_sa_employees(company)
    if not employees:
        return result

    period_cache = _prefetch_leave_periods_for_year(
        {e.company for e in employees}, year,
    )

    for emp in employees:
        try:
            period = period_cache.get(emp.company)
            if period and _has_active_assignment(emp.name, period.name):
                result["skipped"] += 1
                continue

            status = _apply_policy_for_employee(emp, policy_name, period)
            if status == _POLICY_APPLIED:
                result["created"] += 1
            elif status == _POLICY_SKIPPED_NO_PERIOD:
                _record_failure(
                    result,
                    f"{emp.name}: no Leave Period for {emp.company}/{year}",
                )
            else:
                result["skipped"] += 1
        except Exception as exc:
            _record_failure(result, f"{emp.name}: {exc}")

    return result


def _prefetch_leave_periods_for_year(companies, year):
    """Return {company: frappe._dict(name, from_date, to_date)} for periods whose from_date year == `year`."""
    if not companies:
        return {}
    year = int(year)
    rows = frappe.get_all(
        "Leave Period",
        filters={"company": ["in", list(companies)], "is_active": 1},
        fields=["name", "company", "from_date", "to_date"],
    )
    return {
        r.company: frappe._dict(name=r.name, from_date=r.from_date, to_date=r.to_date)
        for r in rows
        if getdate(r.from_date).year == year
    }


def _has_active_assignment(employee, leave_period):
    return bool(frappe.db.exists(
        "Leave Policy Assignment",
        {"employee": employee, "leave_period": leave_period, "docstatus": 1},
    ))


@frappe.whitelist()
def auto_fill_leave_approvers(company=None):
    """
    Populate `Employee.leave_approver` where empty, using:
      1. Department.leave_approvers[0].approver
      2. Else first active user with SA Leave Settings.default_approver_fallback_role
      3. Else skip + log
    Existing approvers are never overwritten.
    """
    result = _empty_result()

    settings = frappe.get_cached_doc("SA Leave Settings")
    fallback_role = settings.get("default_approver_fallback_role")

    employees = _active_sa_employees(company)
    if not employees:
        return result

    departments = {e.department for e in employees if e.department}
    dept_to_approver = {}
    if departments:
        dept_to_approver = {
            row.parent: row.approver
            for row in frappe.get_all(
                "Department Approver",
                filters={
                    "parent": ["in", list(departments)],
                    "parentfield": "leave_approvers",
                    "idx": 1,
                },
                fields=["parent", "approver"],
            )
        }

    fallback_user = None
    if fallback_role:
        users = get_users_with_role(fallback_role)
        fallback_user = users[0] if users else None

    by_approver = {}
    for emp in employees:
        if emp.leave_approver:
            result["skipped"] += 1
            continue

        approver = dept_to_approver.get(emp.department) or fallback_user
        if not approver:
            _record_failure(
                result,
                f"{emp.name}: no approver resolvable from Department "
                f"or fallback role",
            )
            continue
        by_approver.setdefault(approver, []).append(emp.name)

    for approver, emp_names in by_approver.items():
        try:
            frappe.db.set_value(
                "Employee", {"name": ["in", emp_names]}, "leave_approver", approver,
            )
            result["created"] += len(emp_names)
        except Exception as exc:
            for n in emp_names:
                _record_failure(result, f"{n}: {exc}")

    return result


@frappe.whitelist()
def provision_employee_users(company=None):
    """
    Create a User (role: Employee Self Service) for every SA Employee with
    `company_email` and no `user_id`, and link via Employee.user_id. Does
    NOT auto-send the welcome email — HR controls invites from the User form.

    Idempotent: employees with an existing user_id are skipped; employees
    whose company_email already belongs to a User get linked without
    creating a duplicate.
    """
    result = _empty_result()
    employees = _active_sa_employees(company)
    if not employees:
        return result

    pending_emails = {
        e.company_email for e in employees
        if e.company_email and not e.user_id
    }
    existing_users = set()
    if pending_emails:
        existing_users = set(frappe.get_all(
            "User",
            filters={"email": ["in", list(pending_emails)]},
            pluck="name",
        ))

    for emp in employees:
        try:
            if emp.user_id:
                result["skipped"] += 1
                continue
            if not emp.company_email:
                result["skipped"] += 1
                continue

            if emp.company_email in existing_users:
                frappe.db.set_value(
                    "Employee", emp.name, "user_id", emp.company_email,
                )
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
            _record_failure(result, f"{emp.name}: {exc}")

    return result


@frappe.whitelist()
def recompute_sick_leave_cycles():
    """Phase 2 stub. Shape matches the other bulk helpers for toast consistency."""
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
    Weekly job. Find Leave Applications status=Open older than 48h, group by
    leave_approver, send one consolidated email per approver. Silent no-op
    when there's nothing pending.
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

        # No reference_doctype/reference_name on this digest: it summarises
        # multiple Leave Applications, and pinning the Communication record
        # to an arbitrary first item misleads later audit lookups.
        frappe.sendmail(
            recipients=[approver],
            sender=sender,
            subject=_("Leave Applications awaiting your approval"),
            message="\n".join(body_lines),
        )


def email_low_balance_employees():
    """
    Weekly job. For every active SA Employee whose Annual Leave balance is
    below SA Leave Settings.low_balance_threshold_days, email the employee
    (cc: users with the fallback role). Silent when nobody is below threshold.
    """
    from hrms.hr.doctype.leave_application.leave_application import (
        get_leave_balance_on,
    )

    settings = frappe.get_cached_doc("SA Leave Settings")
    threshold = float(settings.get("low_balance_threshold_days") or 0)
    sender = settings.get("notification_from_email") or None
    fallback_role = settings.get("default_approver_fallback_role") or HR_MANAGER_ROLE

    if threshold <= 0:
        return

    if not frappe.db.exists("Leave Type", ANNUAL_LEAVE_TYPE):
        return

    today = frappe.utils.today()
    hr_users = get_users_with_role(fallback_role) if fallback_role else []

    for emp in _active_sa_employees(with_user_id=True):
        try:
            balance = get_leave_balance_on(emp.name, ANNUAL_LEAVE_TYPE, today)
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
