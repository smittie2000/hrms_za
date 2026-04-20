# hrms_za — Leave Automation Seeder Plan (Phase 1, plumbing only)

## Context

### Why this phase exists

HRMS-ZA v0.0.1 shipped the SARS payroll layer — PAYE calculator with rebates
and medical credits, 2026/27 tax brackets, statutory report shapes, workspace
dashboard. HR Manager feedback post-review: impressive, but the **actual
biggest daily pain is leave admin, not payroll**. Today it's an email chain +
spreadsheet:

- Employees email leave requests.
- HR updates a spreadsheet manually.
- HR emails approval back.
- No single source of truth for balances; sick-leave compliance is eyeballed.
- Year-end rollover is done by hand.

HRMS v16 already ships ~80% of what's needed out of the box — Leave Policy,
Leave Policy Assignment, Leave Application (with native calendar view at
`/app/leave-application/view/calendar`), Leave Allocation with earned-leave
scheduling, Leave Ledger, Notification DocType with role-based dynamic
recipients, `Department.leave_approvers` fallback chain. The issue is that
none of it is *configured* on a fresh site.

**The risk of building more code here is the same mistake we want to avoid** —
duplicating what already ships. So this phase is almost entirely *seeders* that
flip the installed machinery on, plus one Single DocType for editable config
and a handful of bulk helpers exposed as action buttons. The HR Manager's
mental model: every install should leave the system ready, with at most a few
field values and 3–4 button clicks. Laravel seeders / factories, applied to
Frappe.

### Architectural commitment

Every feature delivered via code, three tiers:

| Laravel concept | Frappe equivalent | Location in `hrms_za` |
|---|---|---|
| Migration | DocType JSON | `hrms_za/payroll_sa/doctype/sa_leave_settings/...` |
| Seeder (idempotent) | `after_install` / `on_company_update` functions | `hrms_za/regional/south_africa/setup.py` |
| Factory (bulk helper) | `@frappe.whitelist()` method | `hrms_za/regional/south_africa/leave.py` |
| `config/*.php` | Single DocType | `SA Leave Settings` |
| Artisan command | Action button → whitelisted method | JS on the Single's form |

Every future feature for this app should default to this decomposition. If a
proposed feature can only be delivered by "then HR opens X form and fills in
Y", stop and find a seeder + settings-doctype + button decomposition before
writing code.

### Scope decision

1. **Cycle anchor: configurable**, with **1 January as default**. HR Manager
   sets month+day on `SA Leave Settings`; the seeder uses those values to
   seed a `Leave Period` per SA Company per year. HRMS's built-in Leave
   Policy Assignment pro-rating handles mid-year joiners automatically.
2. **Phase 1 scope is plumbing only.** No dashboard tiles, no Leave
   Liability report, no workspace mutation in this phase. All that ships in
   Phase 1b once the plumbing is exercised with real leave data.

### What is NOT in this phase (flagged for follow-up)

- 36-month rolling sick-leave cycle algorithm (HRMS v16 ships nothing for this — greenfield build).
- Dashboard tiles for leave (number cards, calendar shortcut) — Phase 1b.
- SA Leave Liability query report — Phase 2.
- Auto Email Report records for leave balance digests — blocked on Frappe's lack of role-based recipient resolution; design a wrapper later.
- Two-step approval workflow for >10-day requests — Phase 3.
- Leave encashment / terminal payout helper — later.

## Pressure-tested amendments folded in

A design critique pass surfaced the following real issues; each is addressed:

- **Backfill for existing employees** — `after_install` doc events only fire for new Employees. Ship a migration patch in `patches.txt` to backfill Leave Policy Assignment for all existing SA employees.
- **Never-throw from the `Employee.after_insert` hook** — guard for null company / null country / non-SA country / missing DOJ / missing Leave Policy. All paths log + skip; never raise (would abort the Employee save).
- **Don't use the bulk helper for single-employee inserts** — call the single-record flow directly to avoid upstream's `msgprint` spam on the HR form.
- **Low-balance "notification" is really a scheduled task** — `Notification` DocType doesn't fit "scan all balances weekly". Implement as a scheduler job calling `frappe.sendmail` directly; do not seed it as a Notification record.
- **`Custom DocPerm` has no unique constraint** — re-running the seeder would stack duplicate rows. Dedupe by `(role, parent, permlevel, if_owner)` before every insert.
- **Respect user edits to `SA Leave Settings`** — on re-run, only fill fields that are empty; never overwrite. Single doctypes persist, so the seeder is first-run-only for values.
- **Respect user edits to the seeded Leave Policy** — if `SA Standard Leave Policy` exists in any state (draft/submitted/amended), do not reconcile child rows. Document as a seed-once contract.
- **Short-tenure edge case** — when the derived leave cycle window is <90 days, skip pro-rata and log. Avoids zero-allocation silent bugs.
- **Earned-leave `new_leaves_allocated = 0` at creation** — document this so day-1 "balance is zero" is not reported as a bug; the scheduler tops it up monthly.

## Execution order

> **Step 0 is a manual doc commit to the `hrms_za` repo — not a runtime step.**
> All other steps run inside the app's `after_install` / `on_company_update` /
> scheduler / hooks pipeline, each idempotent and re-runnable.

### Step 0 — Commit the plan to the `hrms_za` repo

- Copy this file to `hrms_za/PLAN.md`.
- Commit with message "docs: phase-1 leave-automation seeder plan".
- Not a seeder / not a runtime step — just ensures context survives between PRs.

### Step 1 — `SA Leave Settings` Single DocType

- Path: `hrms_za/payroll_sa/doctype/sa_leave_settings/`.
- Files: `sa_leave_settings.json` (with `"issingle": 1`, no `autoname`), `sa_leave_settings.py`, `sa_leave_settings.js`, `__init__.py`.
- Module: `Payroll SA` (no new module to register; already in `modules.txt`).

**Fields** (grouped by section break):

*Enablement*
- `enabled` (Check, default `1`) — master kill-switch for all SA-leave automation.
- `auto_assign_policy_on_hire` (Check, default `1`) — toggles the Employee after_insert trigger.

*Cycle anchor*
- `cycle_start_month` (Int, default `1`, min 1 max 12) — month of year the cycle starts.
- `cycle_start_day` (Int, default `1`, min 1 max 31) — day of month the cycle starts.
- `default_leave_policy` (Link Leave Policy, default `SA Standard Leave Policy`) — used by auto-assign.

*Thresholds*
- `sick_cycle_months` (Int, default `36`) — BCEA s22; consumed by Phase 2.
- `sick_days_per_cycle` (Int, default `30`) — BCEA s22.
- `low_balance_threshold_days` (Float, default `3`) — triggers the weekly nudge task.
- `annual_leave_carry_forward_max` (Float, default `5`) — per-company policy.
- `two_step_approval_threshold_days` (Float, default `10`) — reserved for Phase 3.

*Approver fallback*
- `default_approver_fallback_role` (Link Role, default `HR Manager`) — when Employee.leave_approver and Department.leave_approvers[0] are both empty.

*Email*
- `notification_from_email` (Data, default blank) — populated per tenant.

**Action buttons** (wired in `.js`):

1. "Seed Leave Period for Year" → `seed_leave_period(year)`.
2. "Generate Leave Policy Assignments for Year" → `generate_sa_leave_allocations(year, company=None)`.
3. "Auto-Fill Leave Approvers" → `auto_fill_leave_approvers(company=None)`.
4. "Provision Employee Users (ESS)" → `provision_employee_users(company=None)`.
5. "Generate SA Holiday List for Year" → wraps existing `generate_sa_holiday_list(year, company)`.
6. "Recompute Sick Leave Cycles" → stub for Phase 2 (logs and returns).

Each button: confirmation dialog → call → progress toast → result summary (created / skipped / failed).

**Seeder contract:** `install_sa_leave_settings_defaults()` in `setup.py` — only fills fields that are currently empty. User edits survive re-install.

### Step 2 — `SA Standard Leave Policy` seed

- Seeder: `install_leave_policy()` in `setup.py`, called from `setup_site_wide()` **after** `install_leave_types()` (ordering matters — policy details reference the leave-type records).
- Record: `Leave Policy` with `title = "SA Standard Leave Policy"`.
- Child rows (`leave_policy_details`): one per seeded leave type with its BCEA/policy quantity.

| Leave Type | Annual Allocation |
|---|---|
| Annual Leave (SA) | 15 |
| Sick Leave (SA) | 30 |
| Family Responsibility Leave (SA) | 3 |
| Maternity Leave (SA) | 120 |
| Parental Leave (SA) | 10 |
| Adoption Leave (SA) | 70 |
| Commissioning Parental Leave (SA) | 70 |
| Study Leave (SA) | 5 |

- `Leave Policy` is submittable → seeder calls `.insert()` then `.submit()`.
- **Idempotency:** if any doc with name `SA Standard Leave Policy` exists (in any state), seeder returns. No reconciliation — respects HR amendments.
- Policy data lives in `hrms_za/regional/south_africa/data/leave_policy.py` (analogous to our existing data modules).

### Step 3 — Seed `Leave Period` per SA Company per year

- Seeder: `install_leave_period_for_current_year(company)` in `setup.py`, called from `setup_per_company()`.
- For each SA company, computes the current cycle window from `SA Leave Settings.cycle_start_month` + `cycle_start_day`. Default 1-Jan → 31-Dec of the current calendar year.
- Record name: `SA Leave Period {YYYY} - {Company}` (scoped name pattern, matching the Income Tax Slab convention already in use).
- Fields: `from_date`, `to_date`, `is_active=1`, `company`.
- **Idempotency:** `frappe.db.exists("Leave Period", name)` → skip. Never modifies existing periods.
- Exposed for re-run via button #1 on `SA Leave Settings` (for the next year, called each January by HR).

### Step 4 — Employee `after_insert` auto-assign

- Hook: `doc_events.Employee.after_insert = "hrms_za.regional.south_africa.leave.assign_default_policy"` in `hrms_za/hooks.py`.
- Function logic (guard-and-skip, never raise):
  1. Read `frappe.get_single("SA Leave Settings")`. If `enabled==0` or `auto_assign_policy_on_hire==0`, return.
  2. If `doc.company` is null, return.
  3. If `Company.country != "South Africa"`, return.
  4. If `doc.date_of_joining` is null, log a Comment on the Employee ("Leave policy not assigned: date_of_joining missing") and return.
  5. If `settings.default_leave_policy` is null OR the Leave Policy record doesn't exist, log a Comment and return.
  6. Resolve the current Leave Period for `doc.company`. If none, log a Comment and return.
  7. Compute cycle window: `max(doc.date_of_joining, leave_period.from_date)` → `leave_period.to_date`. If the remaining window is <90 days, log a Comment and skip (avoids silent zero-allocation).
  8. Create a Leave Policy Assignment with `assignment_based_on = "Leave Period"`, `leave_period = <resolved>`, `leave_policy = settings.default_leave_policy`. Insert + submit. HRMS auto-pro-rates and creates Leave Allocations via `grant_leave_alloc_for_employee()`.
  9. Wrap the whole create+submit in a `try/except` → `frappe.log_error(title="hrms_za: leave policy auto-assign failed")`. Never propagates; the Employee save always succeeds.
- Direct `create_assignment` flow — **not** the bulk `create_assignment_for_multiple_employees` helper (that one throws `msgprint` into the HR user's form).

### Step 5 — Bulk helpers (whitelisted, exposed via `SA Leave Settings` buttons)

Module: `hrms_za/regional/south_africa/leave.py`. All functions idempotent; all return `{"created": N, "skipped": N, "failed": [names with reasons]}` dicts.

- **`seed_leave_period(year, company=None)`** — creates `SA Leave Period {year} - {company}` for every active SA company (or the named one) using the current cycle anchor from settings. Skip if exists.
- **`generate_sa_leave_allocations(year, company=None)`** — wraps HRMS's `create_assignment_for_multiple_employees(employees, data)`. Finds active SA employees without an active Leave Policy Assignment for the target Leave Period; assigns the settings' default policy. Safe to re-run after hires.
- **`auto_fill_leave_approvers(company=None)`** — for every Employee where `leave_approver` is empty:
  1. If `Department.leave_approvers[0].approver` exists, use it.
  2. Else pick a user with the settings-specified fallback role (first active user).
  3. Else log and skip.
- **`provision_employee_users(company=None)`** — for every Employee with `company_email` and no `user_id`: create a `User` with `Employee Self Service` role, link via `user_id`. Welcome email toggleable (off by default; HR flips the Frappe "send welcome email" on User when ready).
- **`recompute_sick_leave_cycles()`** — stub in this phase. Returns `{"status": "not_yet_implemented", "phase": 2}`.

### Step 6 — Seed 3 `Notification` records

- Seeder: `install_notifications()` in `setup.py`, called from `setup_site_wide()`.
- Pattern: `if frappe.db.exists("Notification", name): return` per record — respect HR edits.
- Message bodies shipped as HTML files under `hrms_za/regional/south_africa/data/email_bodies/*.html`; seeder `frappe.read_file`s them and inlines into the `message` field (HRMS's own pattern).

| Name | `document_type` | `event` | Recipient | Subject |
|---|---|---|---|---|
| SA Leave — Submitted | Leave Application | Submit | `receiver_by_document_field = leave_approver` | Leave request from {{ doc.employee_name }} |
| SA Leave — Approved | Leave Application | Value Change (status=Approved) | `receiver_by_document_field = owner` | Your leave {{ doc.name }} was approved |
| SA Leave — Rejected | Leave Application | Value Change (status=Rejected) | `receiver_by_document_field = owner` | Your leave {{ doc.name }} was rejected |

Low-balance notification is **not** a Notification record (wrong trigger shape for "scan all balances"). Implemented as scheduler task in Step 8.

### Step 7 — Seed `Custom DocPerm` rows for Employee Self Service

- Seeder: `install_ess_permissions()` in `setup.py`, called from `setup_site_wide()`.
- Rows:
  - `parent=Leave Application`, `role=Employee Self Service`, `permlevel=0`, `read=1`, `write=1`, `create=1`, `submit=1`, `if_owner=1`.
  - `parent=Leave Allocation`, `role=Employee Self Service`, `permlevel=0`, `read=1`, `if_owner=1`.
- **Dedupe:** `frappe.db.exists("Custom DocPerm", {role, parent, permlevel, if_owner})` before each insert — `Custom DocPerm` has no unique constraint; re-runs would otherwise stack.

### Step 8 — `scheduler_events` hook

- Added to `hrms_za/hooks.py`:

```python
scheduler_events = {
    "daily_long": [
        "hrms_za.regional.south_africa.leave.recompute_sick_leave_cycles",
    ],
    "weekly": [
        "hrms_za.regional.south_africa.leave.nudge_pending_leave_approvals",
        "hrms_za.regional.south_africa.leave.email_low_balance_employees",
    ],
}
```

- **`nudge_pending_leave_approvals`** — finds Leave Applications with `status=Open` and `creation < now - 48h`; emails each distinct approver via `frappe.sendmail` with a grouped summary. Reads `settings.notification_from_email` (falls back to site default).
- **`email_low_balance_employees`** — aggregates Leave Allocation balances; for each employee where Annual Leave balance < `settings.low_balance_threshold_days`, emails the employee and CCs role `HR Manager`. Builds its own Jinja context (no `doc`); that's the reason this is a scheduler task, not a Notification record.
- **`recompute_sick_leave_cycles`** — stub until Phase 2.

### Step 9 — Migration patch for existing SA employees

- New directory: `hrms_za/patches/v0_0_2/` with `__init__.py` and `backfill_sa_leave_policy_assignments.py`.
- `hrms_za/patches.txt` gets a new line: `hrms_za.patches.v0_0_2.backfill_sa_leave_policy_assignments`.
- Patch logic: for every Employee where `company.country == "South Africa"` AND `date_of_joining` is set AND no active Leave Policy Assignment covers today's date → run the same create+submit flow as Step 4 (shared helper function). Counts created / skipped / failed; prints a summary to the migrate log.
- Guarded by `frappe.db.exists("DocType", "Leave Policy Assignment")` to survive ordering on fresh installs.

### Step 10 — `before_uninstall` hook

- Added to `hrms_za/hooks.py`: `before_uninstall = "hrms_za.regional.south_africa.setup.before_uninstall"`.
- Tears down seeded state cleanly so reinstalls start fresh:
  - Delete the 3 Notification records by name (only if unchanged — check against seeded hashes, else skip).
  - Delete the 2 Custom DocPerm rows added by the seeder (matched by `role, parent, permlevel, if_owner`).
  - Leave data (Leave Policy Assignments, Allocations, Leave Periods) untouched — it's tenant data, not app config.
  - The `SA Leave Settings` Single is dropped automatically by Frappe when the doctype is removed.

### Step 11 — Tests

- New file: `hrms_za/payroll_sa/tests/test_leave_setup.py`.
- Coverage:
  - Fresh install creates the Settings Single with defaults.
  - Fresh install seeds `SA Standard Leave Policy` (submitted).
  - Re-running `after_install` doesn't duplicate records (Notifications, DocPerms, Policy).
  - User edits to `SA Leave Settings` survive re-install.
  - User edits to `SA Standard Leave Policy` survive re-install.
  - Employee created with DOJ and SA company → Leave Policy Assignment + Allocations auto-created.
  - Employee created without DOJ → skipped with Comment added, no exception.
  - Employee created on non-SA company → skipped, no records created.
  - Employee with 30-day remaining cycle window → skipped with Comment (short-tenure edge).
  - Backfill patch covers an existing SA employee, idempotent on re-run.
  - `auto_fill_leave_approvers` resolves via Department → fallback role → skip+log chain.

## Critical files

**Modified**

- `hrms_za/hooks.py` — add `scheduler_events`, `doc_events.Employee.after_insert`, `before_uninstall`.
- `hrms_za/regional/south_africa/setup.py` — add `install_sa_leave_settings_defaults`, `install_leave_policy`, `install_leave_period_for_current_year`, `install_notifications`, `install_ess_permissions`, `before_uninstall`; wire each into `setup_site_wide()` / `setup_per_company()` with correct ordering.
- `hrms_za/patches.txt` — append the backfill patch entry.
- `hrms_za/__init__.py` — bump `__version__` to `0.0.2`.

**New**

- `hrms_za/payroll_sa/doctype/sa_leave_settings/__init__.py`
- `hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.json`
- `hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.py`
- `hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.js`
- `hrms_za/regional/south_africa/leave.py`
- `hrms_za/regional/south_africa/data/leave_policy.py`
- `hrms_za/regional/south_africa/data/notifications.py`
- `hrms_za/regional/south_africa/data/email_bodies/leave_submitted.html`
- `hrms_za/regional/south_africa/data/email_bodies/leave_approved.html`
- `hrms_za/regional/south_africa/data/email_bodies/leave_rejected.html`
- `hrms_za/patches/__init__.py` (if not already)
- `hrms_za/patches/v0_0_2/__init__.py`
- `hrms_za/patches/v0_0_2/backfill_sa_leave_policy_assignments.py`
- `hrms_za/payroll_sa/tests/test_leave_setup.py`
- `hrms_za/PLAN.md` (Step 0 — copy of this plan)

## Reused upstream code (do not reinvent)

- `hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment.create_assignment(employee, data)` — single-employee assignment creation.
- `hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment.grant_leave_alloc_for_employee` — fires on submit, creates Leave Allocations with pro-rating.
- `frappe.custom.doctype.custom_field.custom_field.create_custom_fields` — already in use in setup.py.
- `frappe.desk.page.setup_wizard.setup_wizard.make_records` — HRMS pattern for bulk idempotent seeding; consider adopting where current code does manual upserts.
- Native `Leave Application` calendar view at `/app/leave-application/view/calendar` — no code needed.
- `Department.leave_approvers` child table (`Department Approver` docs with `approver: Link User`) — consumed by `auto_fill_leave_approvers`.
- `Notification.receiver_by_role` — resolves to all users with the role at send time (confirmed via `notification.py:598`).

## Verification (end-to-end test on the target site)

1. **Build & deploy.** Rebuild the layered image with `--no-cache-filter=builder`; redeploy the stack.
2. **Install / migrate.**
   ```bash
   docker exec -u frappe frappe-backend-1 bench --site <your-site> migrate
   docker exec -u frappe frappe-backend-1 bench --site <your-site> clear-cache
   ```
   Both must exit 0. Watch the migrate log for the backfill patch output.
3. **Config surface.** Open `/app/sa-leave-settings`. Confirm defaults (cycle 1 Jan, sick cycle 36/30, threshold 3, fallback role HR Manager). Change `cycle_start_month=3` to prove persistence.
4. **Seed records.** `/app/leave-policy/SA Standard Leave Policy` is submitted. `/app/leave-period` shows `SA Leave Period 2026 - <Company>`. `/app/notification` shows the 3 seeded rows. `/app/custom-docperm` shows the 2 ESS rows.
5. **New hire flow.** Create a test Employee on the SA company with `date_of_joining = today()`. Immediately check:
   - Leave Policy Assignment exists and is submitted for this employee.
   - Leave Allocations exist (one per policy leave type), pro-rated for the remaining cycle.
   - No exception raised during Employee save.
6. **Edge cases.** Create an Employee without DOJ — save succeeds, Comment recorded, no Assignment created. Create an Employee on a non-SA company — no Assignment.
7. **ESS.** Log in as the test Employee's User. Submit a Leave Application. Confirm the approver receives the "SA Leave — Submitted" email (check `/app/email-queue`).
8. **Calendar.** `/app/leave-application/view/calendar` shows the test leave.
9. **Bulk helpers.** Click each of the 5 action buttons on SA Leave Settings; each returns a success toast with a created/skipped/failed summary.
10. **Idempotency.** Run `bench migrate` again. Re-run the 5 buttons. No duplicates anywhere — verify by comparing record counts before/after.
11. **Scheduler.** Manually trigger `bench --site <your-site> execute hrms_za.regional.south_africa.leave.nudge_pending_leave_approvals` — confirm an approver gets a nudge email for the (now >48h old in dev) pending test application.
12. **Uninstall dry-run.** On a throwaway site: `bench --site <your-site> uninstall-app hrms_za` — confirm the 3 Notifications + 2 Custom DocPerms are removed, Leave Policy Assignments / Allocations / Leave Periods remain.
13. **Tests.**
    ```bash
    docker exec -u frappe frappe-backend-1 bench --site <your-site> \
        run-tests --module hrms_za.payroll_sa.tests.test_leave_setup
    ```
    All green.

## Dependencies / preflight

- Existing seeders (`install_custom_fields`, `install_employment_types`, `install_leave_types`, `install_salary_components`) are unchanged and still called from `setup_site_wide` — this plan extends, not replaces.
- Post-Phase-1, before building Phase 1b (dashboard tiles) and Phase 2 (36-month sick cycle), exercise this plumbing with real leave data for ≥2 weeks and collect HR feedback. The dashboard design may shift based on what HR actually checks daily.
