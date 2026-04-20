# Phase 2 — SA Leave Accrual & Sick-Leave Cycle (Code Spec)

**Status:** Design approved, pending HR decision-spec sign-off.
**Date:** 2026-04-20.
**Targets:** `hrms_za` v0.0.2.
**Companion doc:** `2026-04-20-sa-leave-accrual-hr-decisions.md` (HR-facing, for domain validation).

## 1. Context

### Why this phase exists

Phase 1 shipped the leave-automation plumbing — Leave Types, Leave Policy, Leave Periods, auto-assignment on hire, notifications, permissions. It did not ship:

- Real earn-as-you-go accrual for annual leave (Phase 1 allocates upfront, which exposes the tenant to paying out leave the employee hasn't actually worked for).
- Any tracking of the BCEA s22 sick-leave cycle (Phase 1 treats sick leave as a flat 30-day-per-year bucket — wrong under BCEA).
- Any cross-boundary link from employee termination to leave payout.

This phase closes all three gaps using HRMS's own primitives wherever possible, adding genuinely new code only for the one concept upstream has no analogue for: BCEA's **fixed consecutive 36-month sick-leave cycles**.

### Terminology correction

Phase 1's scope documents (`PLAN.md`, `README.md`, several `.py` comments, and two field descriptions on `SA Leave Settings`) describe sick leave as a "rolling 36-month window". This is wrong under BCEA. The Act defines **fixed consecutive 36-month cycles**, each anchored at `date_of_joining` (or the end of the previous cycle), with a fresh 30-day bucket per cycle. Unused days expire at the cycle boundary. Eleven "rolling" references in the repo are listed in §10 for cleanup as part of this phase.

### Pressure-tested amendments

From brainstorming (2026-04-20 session):

- **Two-policy split is cleaner than a single policy with mixed cycles.** Annual leave runs on a 12-month company-wide cycle; sick leave runs on a per-employee 36-month cycle anchored at DOJ. They cannot share a Leave Policy Assignment.
- **BCEA s22(3) first-six-months rule is deliberately skipped.** Employees draw from the full 30-day Cycle 1 bucket from day 1, which exceeds the Act's minimum. This is legally defensible ("we exceed the Act") and avoids an Attendance-integration dependency.
- **Unused sick days at cycle end expire ("use or lose").** BCEA does not require carry-forward; standard SA HR practice is to expire them. No knob — this is the law, not configuration.
- **Termination auto-encashment defaults on**, but HR can flip a knob to require a manual button click instead.
- **Earned-leave accrual uses HRMS's native monthly top-up** rather than a custom Attendance-driven engine. Monthly granularity is sufficient for salaried staff and reuses upstream code.
- **No new DocTypes.** All state lives in existing HRMS tables (`Leave Policy`, `Leave Policy Assignment`, `Leave Allocation`, `Leave Encashment`) and the Phase-1 `SA Leave Settings` Single.

### Scope boundary

In scope: accrual mechanics for Annual Leave (SA), cycle mechanics for Sick Leave (SA), cross-boundary termination encashment trigger, wiring for existing knobs that were set but unused in Phase 1.

Out of scope: dashboards/tiles (Phase 1b), non-annual-leave encashment, BCEA s22(3) pro-rata enforcement, per-day-worked accrual, graduated tenure caps, s35 "remuneration" rate computation (defers to Salary Structure).

---

## 2. Architecture

### Two-policy split

Phase 1 ships one `SA Standard Leave Policy`. Phase 2 splits it into:

| Policy | Leave types | LPA cycle |
|---|---|---|
| **`SA Annual Leave Policy`** (renamed from `SA Standard Leave Policy`) | Annual, Family Responsibility, Maternity, Parental, Adoption, Commissioning Parental, Study | One LPA per Leave Period (12 months, tenant-aligned) |
| **`SA Sick Leave Cycle Policy`** (new) | Sick Leave (SA) only | One LPA per 36-month BCEA cycle (per-employee, DOJ-anchored) |

Each policy holds its own `leave_policy_details` child rows. Neither DocType structure changes — only record contents.

### Two LPA streams per employee

Every active SA employee ends up with two parallel Leave Policy Assignment streams:

- **Annual stream** — one LPA per calendar year, `assignment_based_on = "Leave Period"`. Unchanged from Phase 1 mechanics. Earned-leave flag on `Annual Leave (SA)` changes the Allocation behaviour from "15 upfront" to "monthly top-up".
- **Sick cycle stream** — one LPA per 36-month cycle, `assignment_based_on = "Joining Date"`, `effective_from = cycle_start`, `effective_to = cycle_end`. Managed by a new scheduler task.

### The cycle scheduler

New daily scheduler task `hrms_za.regional.south_africa.leave.emit_sick_cycle_lpas`:

1. Query employees whose current sick LPA's `effective_to` is within `settings.sick_cycle_lookahead_days` (default 7) of today.
2. Also query employees with no active sick LPA (gap-recovery path).
3. For each, compute the next cycle window via `sa_sick_cycle_window(doj, today)`.
4. Create + submit a new LPA for that window.
5. Idempotent: existing LPAs with matching `(employee, effective_from)` are skipped.

When a cycle boundary passes, the old Allocation naturally stops being counted by HRMS's `get_leave_balance_on()` (its `to_date` is past); the new Allocation takes over. Unused days die without any code explicitly writing them off.

### Cross-boundary contract

One function — `sa_leave_balance(employee, leave_type, on_date)` — is a thin wrapper over HRMS's `get_leave_balance_on()`. Every consumer uses it:

| Consumer | Leave type | Purpose |
|---|---|---|
| Leave Application native validator | Both | Block drawdown beyond balance |
| ESS balance display | Both | Employee-facing dashboard |
| Termination encashment trigger | Annual only (BCEA s40) | Payout amount |
| Low-balance scheduler | Annual only | Existing Phase 1 logic |

**Invariant:** if any subsystem reads balances from anywhere else, the contract is broken. This is the one thing the review checklist must verify.

---

## 3. Data model

### Leave Type changes

Only `Annual Leave (SA)` changes. Edit in `regional/south_africa/data/leave_types.py`:

- `is_earned_leave = 1`
- `earned_leave_frequency = "Monthly"`
- `allocate_on_day = "First Day"`
- `rounding = "0.25"`
- `maximum_carry_forwarded_leaves = 5` (wires the existing `annual_leave_carry_forward_max` knob)
- `applicable_after = 0` (left at 0; HR can set via knob)

`Sick Leave (SA)` is unchanged — not earned-leave, not calendar-driven. Its behaviour comes from the LPA effective window.

### Leave Policy records

Two records instead of one. Both are submitted `Leave Policy` instances:

- `SA Annual Leave Policy` — leave types listed in §2.
- `SA Sick Leave Cycle Policy` — `Sick Leave (SA)` with `annual_allocation = settings.sick_days_per_cycle` (default 30).

No schema change to the `Leave Policy` DocType itself.

### SA Leave Settings — new fields

| Fieldname | Type | Default | Purpose |
|---|---|---|---|
| `default_sick_cycle_policy` | Link Leave Policy | `SA Sick Leave Cycle Policy` | Used by the sick-cycle LPA emitter |
| `sick_cycle_lookahead_days` | Int | 7 | Emit next-cycle LPA this many days before current cycle ends |
| `backfill_missing_cycles` | Check | 1 | Create historical LPAs for cycles already elapsed at install time |
| `enforce_sick_cycle_cap` | Check | 1 | If off, flips `Leave Type.allow_negative = 1` on Sick Leave (SA) so balance can go negative |
| `annual_leave_applicable_after_days` | Int | 0 | Pushed into `Leave Type.applicable_after` on Annual Leave (SA) via settings `on_update` |
| `auto_create_termination_encashment` | Check | 1 | If on, Employee Separation submit creates a draft Leave Encashment |

Existing Phase-1 fields that finally get wired:

| Field | Phase-2 consumer |
|---|---|
| `sick_cycle_months` (36) | LPA effective window length |
| `sick_days_per_cycle` (30) | Policy detail quantity on `SA Sick Leave Cycle Policy` |
| `annual_leave_carry_forward_max` (5) | `Leave Type.maximum_carry_forwarded_leaves` on Annual Leave (SA) |

### Database effects on migrate

- One row renamed in `tabLeave Policy`.
- One row moved in `tabLeave Policy Detail` (Sick Leave child row goes to the new policy).
- One row added in `tabLeave Policy` (SA Sick Leave Cycle Policy).
- Leave Type fields updated on Annual Leave (SA).
- Six new fields on SA Leave Settings initialised with defaults.
- No ALTER TABLE beyond Frappe's standard DocType-JSON reconciliation.

### Deliberately untouched

- `Leave Period` records — still tenant-aligned 1-Jan..31-Dec for annual stream.
- Existing annual LPAs — rename cascades transparently.
- `Custom DocPerm` — Phase 1 permissions cover Leave Allocation read for ESS.
- `Notification` seeds — work for both leave types unchanged.

---

## 4. Component inventory

### Runtime code

| File | Change | New callables |
|---|---|---|
| `regional/south_africa/leave.py` | Extend | `emit_sick_cycle_lpas()` (scheduler), `sa_sick_cycle_window(doj, on_date)` (pure helper), `trigger_termination_encashment(employee, separation_date)`, extend `assign_default_policy()` to assign both policies. Replace `recompute_sick_leave_cycles()` stub with real impl. |
| `regional/south_africa/setup.py` | Extend | Split `install_leave_policy()` to emit two policies. Extend `install_sa_leave_settings_defaults()` for six new fields. Add settings `on_update` handler to propagate knobs to Leave Type fields. |
| `regional/south_africa/data/leave_types.py` | Extend | `Annual Leave (SA)` gets `is_earned_leave`, `earned_leave_frequency`, `allocate_on_day`, `rounding`, `maximum_carry_forwarded_leaves`. |
| `regional/south_africa/data/leave_policy.py` | Extend | Rebuild: emit two policies instead of one. |
| `hooks.py` | Extend | `scheduler_events.daily += ["…emit_sick_cycle_lpas"]`; `doc_events["Employee Separation"].on_submit = "…trigger_termination_encashment"`. |

### Install / migration posture

Collapsed (Laravel `migrate:fresh` style): **no new seeder files, no new patch files.**

- `setup.py::setup_site_wide()` ordering unchanged; `install_leave_policy()` internally emits the correct shape.
- Existing `patches/v0_0_2/backfill_sa_leave_policy_assignments.py` grows to:
  1. Rename `SA Standard Leave Policy` → `SA Annual Leave Policy` (if found).
  2. Split sick child row into new `SA Sick Leave Cycle Policy`.
  3. Flip earned-leave flag on `Annual Leave (SA)`.
  4. Propagate settings to Leave Type fields.
  5. Backfill both annual + sick LPAs for existing employees (original scope).
  6. If `backfill_missing_cycles = 1`, emit historical sick LPAs for elapsed cycles.

Idempotent: every step is a check-and-skip. Second `bench migrate` run is a no-op.

### UI wiring

| File | Change |
|---|---|
| `payroll_sa/doctype/sa_leave_settings/sa_leave_settings.js` | "Recompute Sick Leave Cycles" button loses its Phase-2 stub tooltip. Add "Generate Termination Encashment" button (takes Employee arg). Rename tooltips that say "rolling". |
| `payroll_sa/doctype/sa_leave_settings/sa_leave_settings.json` | Add six new fields from §3. Update descriptions that say "rolling" → "fixed 36-month cycle". |
| `README.md`, `PLAN.md`, data module comments | Correct all eleven "rolling" references (see §10). |

### Tests

| File | Change |
|---|---|
| `payroll_sa/tests/test_sick_cycle_window.py` | **NEW** — pure-pytest, no Frappe dependency. Cycle-window math test matrix (§7). |
| `payroll_sa/tests/test_leave_encashment_calc.py` | **NEW** — pure-pytest. Encashment-amount arithmetic edge cases. |
| `payroll_sa/tests/test_leave_setup.py` | Extend — 18 new FrappeTestCase tests covering hire, rollover, validator, termination, backfill paths. |

**Estimated LOC:** ~200 new, ~80 extending existing files.

---

## 5. Data flow walkthroughs

Today for all scenarios: 2026-04-20.

### 5.1 New hire (first day)

Thandi joins Acme (SA) on 2026-04-20. `Employee.after_insert` fires:

1. Read `SA Leave Settings` — enabled, auto-assign on hire, Acme country = South Africa. ✓
2. Annual stream — resolve current Leave Period (`SA Leave Period 2026 - Acme`, 2026-01-01..2026-12-31). Create annual LPA with `effective_from = max(DOJ, period_from) = 2026-04-20`, `effective_to = 2026-12-31`, `leave_policy = SA Annual Leave Policy`. HRMS pro-rates 15 × (256/365) = 10.5 days, but `is_earned_leave = 1` means `new_leaves_allocated = 0` at creation. The monthly earned-leave scheduler tops up 0.875 on 2026-05-01.
3. Sick stream — `sa_sick_cycle_window(2026-04-20, 2026-04-20)` → `(cycle=0, start=2026-04-20, end=2029-04-19)`. Create sick LPA with `assignment_based_on = "Joining Date"`, `leave_policy = SA Sick Leave Cycle Policy`. Allocation: 30 days, usable any time 2026-04-20..2029-04-19.

Thandi's day-1 balances: Annual = 0.00; Sick = 30.00.

### 5.2 Cycle boundary rollover

Thandi on 2029-04-14 (5 days before cycle end; cycle ends 2029-04-19). She's used 22 of 30 sick days. Daily scheduler fires:

1. Query: employees where sick LPA `effective_to - today ≤ 7` → Thandi matches.
2. `sa_sick_cycle_window(2023-05-01, 2029-04-14)` → cycle 0 (current). Compute cycle 1: start=2029-04-20, end=2032-04-19.
3. No existing LPA for that window — create + submit.

Balance queries on each date:

| On date | Cycle-0 Allocation | Cycle-1 Allocation | HRMS reports |
|---|---|---|---|
| 2029-04-18 | 8 left, still active | exists, not yet active | 8 |
| 2029-04-19 | 8 left, last day | not yet active | 8 |
| 2029-04-20 | to_date past, inactive | active | 30 |
| 2029-05-15 | inactive (8 unused gone) | active | 30 |

No custom "use or lose" code. HRMS filters allocations by `from_date <= date <= to_date`.

### 5.3 Sick leave application exceeding cycle cap

Thandi on 2028-06-01 (mid cycle 0, 28/30 used). Applies for 5 sick days. HRMS native validator:

- `get_leave_balance_on` → 2 days
- Requested 5 days
- `Leave Type.allow_negative = 0` (default)
- Throws: *"Insufficient leave balance. You have 2.0 days available."*

No custom validator. If HR flips `enforce_sick_cycle_cap = 0`, the patch also flips `Leave Type.allow_negative = 1` on Sick Leave (SA). Application succeeds, balance goes negative, HR reconciles manually (unpaid, docked, etc.).

### 5.4 Termination & encashment

Thandi resigns, last day 2027-06-30. Annual balance at that date: 4.5 days.

1. HR submits Employee Separation.
2. `doc_events.Employee Separation.on_submit` → `trigger_termination_encashment(Thandi, 2027-06-30)`.
3. `auto_create_termination_encashment = 1` ✓.
4. For Annual Leave (SA): balance 4.5 > 0 → create draft `Leave Encashment`:
   - `employee = Thandi`
   - `leave_type = Annual Leave (SA)`
   - `encashment_days = 4.5`
   - `encashment_date = 2027-06-30`
   - per-day rate pulled from Thandi's Salary Structure Assignment.
   - `docstatus = 0` (HR reviews, submits).
5. Sick Leave (SA) is not encashed — BCEA s40 applies to annual only.

If HR flips the knob off, the auto path is silent; HR clicks the "Generate Termination Encashment" button on the SA Leave Settings form with Thandi selected. Same result, operator-controlled.

### 5.5 Backfill on migrate

Existing Acme site runs `bench migrate`. Extended `v0_0_2` patch:

1. Rename `SA Standard Leave Policy` → `SA Annual Leave Policy`.
2. Remove Sick Leave row from that policy's `leave_policy_details`.
3. Insert `SA Sick Leave Cycle Policy` with Sick Leave 30 days.
4. Update `Annual Leave (SA)` Leave Type: earned-leave flags, carry-forward max.
5. For each active SA employee with DOJ:
   - If no active annual LPA → create one for current Leave Period.
   - If no active sick cycle LPA → compute current cycle from DOJ, create LPA.
   - If `backfill_missing_cycles = 1`, also create historical cycle LPAs as records (to_date < today).
6. Print summary: `{renamed: 1, split: 1, emp_annual_created: N, emp_sick_created: M, …}`.

Second migrate: every step is a no-op; summary prints zeros.

---

## 6. Error handling & edge cases

### Never-throw boundaries

| Surface | Failure | Resolution |
|---|---|---|
| `Employee.after_insert` | Any exception | `try/except` → `frappe.log_error`; Employee save succeeds |
| `Employee Separation.on_submit` | Any exception | `try/except` → `frappe.log_error` + Comment on Employee; Separation submit succeeds |
| Scheduler per-employee iteration | Any exception | `try/except` per-employee; next employee proceeds |
| Patch mid-run | Any exception | `try/except` per step; partial progress preserved; re-run converges |

### Scheduler gap-prevention

Defence in depth:

1. Lookahead window 7 days — normal case, zero gap.
2. Daily cadence — missed tick recovered on next run.
3. No-active-LPA detection — closes any pre-existing gap retroactively by emitting LPA with `effective_from = previous cycle end + 1 day`.
4. Patch + scheduler overlap — migrate handles day-0, scheduler maintains forward.
5. Idempotency on `(employee, effective_from)`.

### Edge cases

| Scenario | Behaviour |
|---|---|
| New hire applies for sick leave same day | Sick LPA created by `after_insert` with `effective_from = today`; balance = 30; works fine |
| Employee with future DOJ | Sick LPA effective_from = future DOJ; balance queries before DOJ return 0 |
| Employee with no DOJ | Phase 1 behaviour — Comment + skip both streams |
| Short-tenure at annual period boundary (<90 days) | Annual LPA skipped per Phase 1; sick LPA still created (DOJ-anchored, independent) |
| Feb 29 DOJ | `add_months` normalises to Feb 28 in non-leap years (Phase 1 pattern) |
| Cycle end/start same day | Old `to_date = 2029-04-19`, new `from_date = 2029-04-20`. No overlap. HRMS validator satisfied |
| HR manually overlapping LPA | HRMS native validator throws; scheduler catches, logs, skips |
| `sick_cycle_months` changed mid-year (36 → 24) | Existing LPAs keep their windows; new LPAs use new length |
| `sick_days_per_cycle` changed (30 → 21) | Existing allocations frozen at submit-time quantity; new LPAs use new policy quantity |
| HR unsubmits/amends sick cycle policy | Seed-once contract respects HR edits (Phase 1 pattern) |
| Employee rehired | New Employee record, new DOJ, fresh streams; old LPAs historical |
| No `leave_encashment_amount_per_day` on Salary Structure | Upstream throws; we wrap → log + Comment; HR fixes rate and clicks manual button |
| Scheduler paused / missed | 7-day lookahead tolerates; next run recovers |
| 100+ employees | <1s per scheduler tick. No batching |
| Long-tenured employee | 1 sick LPA per 3 years = 10 over 30 years. Negligible |

### Logging

- `frappe.log_error` for exceptions.
- `frappe.logger("hrms_za.leave").info(...)` for scheduler summaries.
- Employee-level Comments for human-visible skips.

### NOT defended against

- Malicious HR edits to submitted policies.
- Time-zone confusion (OS is UTC per CLAUDE.md invariant).
- MariaDB outages mid-patch (Frappe transaction rollback handles).
- Historical leave records from outside Frappe (spreadsheet-era).

---

## 7. Testing

### Pure-pytest (fast, no Frappe)

**`test_sick_cycle_window.py`** — tests `sa_sick_cycle_window(doj, on_date)` as a pure function:

| # | DOJ | On date | Expected cycle | Start | End |
|---|---|---|---|---|---|
| 1 | 2023-05-01 | 2023-05-01 | 0 | 2023-05-01 | 2026-04-30 |
| 2 | 2023-05-01 | 2023-12-25 | 0 | 2023-05-01 | 2026-04-30 |
| 3 | 2023-05-01 | 2026-04-30 | 0 | 2023-05-01 | 2026-04-30 |
| 4 | 2023-05-01 | 2026-05-01 | 1 | 2026-05-01 | 2029-04-30 |
| 5 | 2023-05-01 | 2036-06-15 | 4 | 2035-05-01 | 2038-04-30 |
| 6 | 2024-02-29 | 2027-02-28 | 0 | 2024-02-29 | 2027-02-28 |
| 7 | 2024-02-29 | 2027-03-01 | 1 | 2027-03-01 | 2030-02-28 |
| 8 | 2023-05-01 | 2022-12-01 | 0 | 2023-05-01 | 2026-04-30 (pre-DOJ clamps) |

Plus fuzz: 1,000 random `(DOJ, offset)` pairs, assert `cycle_start + 36 months = cycle_end + 1 day`.

**`test_leave_encashment_calc.py`** — tests the encashment arithmetic:

| Scenario | Input | Expected |
|---|---|---|
| Typical | balance=4.5, rate=850 | 3825.00 |
| Zero | 0, 850 | 0.00 |
| No rate | 4.5, None | raises `MissingRate` |
| Negative balance | -2.0, 850 | 0.00 |
| Fractional | 4.333, 850 | 3683.05 |

### FrappeTestCase (slow, needs dedicated test site)

**Ops setup:**

```bash
docker exec -u frappe frappe-backend-1 bench new-site test_hrms_za --admin-password x
docker exec -u frappe frappe-backend-1 bench --site test_hrms_za install-app hrms_za
```

The production site must never be a test target — even with savepoint rollback, orphan records from broken `tearDown` would contaminate real data. Per-test isolation is provided by `frappe.db.rollback(save_point=...)` in `tearDown`, similar to Pest's `DatabaseTransactions` trait.

**Test catalogue (18 tests):**

*Setup / fixtures:*
1. Fresh install produces both policies as submitted records with correct child rows.
2. `Annual Leave (SA)` has `is_earned_leave=1, frequency=Monthly`.
3. Pre-Phase-2 site rename via patch is idempotent.

*Hire flow:*
4. New hire has two LPAs: annual (period-based) + sick (DOJ-based).
5. Sick LPA effective window = DOJ..DOJ+36mo-1.
6. Annual LPA earned-leave starts at 0; scheduler tops up.

*Cycle rollover:*
7. Scheduler emits next-cycle LPA on boundary.
8. Scheduler lookahead: 5 days before boundary triggers next LPA.
9. Scheduler is idempotent.
10. Scheduler closes retroactive gap (effective_from = old_to + 1).

*Leave Application validation:*
11. Sick application blocked when cycle exhausted.
12. Sick application allowed when `enforce_sick_cycle_cap = 0`.

*Termination:*
13. Separation submit auto-creates encashment draft.
14. Knob-off: no auto encashment; manual button works.
15. No salary-rate: Comment logged, no encashment, no exception.

*Backfill patch:*
16. Patch backfills both streams for existing employee with 18-month tenure.
17. Historical-cycle backfill creates elapsed-cycle LPAs for 7-year-tenure employee.
18. Patch is idempotent.

### Live-site verification

After redeploy to the target tenant site:

1. `bench migrate` exits 0; patch summary in log.
2. `/app/leave-policy` shows two submitted policies.
3. `/app/leave-type/Annual Leave (SA)` shows earned-leave flags.
4. `/app/sa-leave-settings` shows six new fields with defaults.
5. New test Employee: two LPAs, annual=0, sick=30.
6. `bench … execute …emit_sick_cycle_lpas` on a 36+mo-tenured test employee: second sick LPA appears.
7. Sick application for 32 days rejected; flipping the knob makes it succeed.
8. `Employee.status = "Left"`, relieving_date = today: draft Leave Encashment on Employee form.
9. Button path produces same result.
10. Second `bench migrate`: patch summary shows zeros.

### Not tested

HRMS's own earned-leave scheduler, `get_leave_balance_on`, `Leave Encashment.validate`, `FrappeTestCase` framework — all trusted upstream.

---

## 8. Cross-boundary contract (summary)

The one rule that must not be broken:

> Every subsystem that reads leave balances MUST go through `sa_leave_balance(employee, leave_type, on_date)`, which is a thin wrapper over HRMS's `get_leave_balance_on()`. No subsystem invents its own balance calculation.

Consumers in scope:
- Leave Application native validator.
- ESS balance display.
- Termination encashment trigger.
- Low-balance email scheduler.
- Any future HR report.

Review checklist: grep the repo for `get_leave_balance_on`, `leaves_taken`, `new_leaves_allocated`, and any custom SUM over Leave Ledger. Any call site outside `sa_leave_balance()` is a defect.

---

## 9. Open questions / future work

- **Phase 1b — dashboard tiles.** Deferred until Phase 2 runs in prod with real leave data for ≥2 weeks.
- **BCEA s35 "remuneration" daily rate.** Current rate source is `Salary Structure Assignment.leave_encashment_amount_per_day`. BCEA s35 requires a specific inclusive definition (housing, transport, commission averages). HR sets the rate to the correct value manually per employee. Automating this is a separate spec.
- **Two-step approval threshold** (>10-day requests). Phase 1 stashed a knob (`two_step_approval_threshold_days = 10`) that nothing reads. Phase 3.
- **Leave encashment during employment** (not termination). Sometimes HR wants to pay out unused leave annually. Out of scope.
- **Public holiday subtraction on multi-day leave requests.** HRMS handles this natively via `Leave Type.include_holiday`. Confirm configuration during verification.

---

## 10. Terminology cleanup

Eleven repo locations use the wrong "rolling" framing. Fix as part of Phase 2:

| File | Lines |
|---|---|
| `PLAN.md` | 62, 114, 340 |
| `README.md` | 41, 51 |
| `payroll_sa/doctype/sa_leave_settings/sa_leave_settings.json` | 90, 98 |
| `payroll_sa/doctype/sa_leave_settings/sa_leave_settings.js` | 43 |
| `regional/south_africa/data/leave_policy.py` | 17, 18 |
| `regional/south_africa/data/leave_types.py` | 7, 26 |

Rename "rolling 36-month window" → "fixed 36-month cycle (BCEA s22)". No code-logic changes.

---

## 11. Definition of done

- Both `bench migrate` runs converge to same state (idempotency verified).
- 18 FrappeTestCase tests + both pure-pytest modules pass.
- Live-site verification §7 checklist green.
- `grep rolling` against `hrms_za/` returns zero hits (outside this spec doc).
- HR Manager signs off on companion decision spec.
- `hrms_za/__init__.py` `__version__` bumped to `0.0.2`.
- `redeploy.sh` rebuilds the layered image with `--no-cache-filter=builder` and the new app commit hash.
