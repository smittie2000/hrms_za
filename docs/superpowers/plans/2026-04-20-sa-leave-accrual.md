# Phase 2 — SA Leave Accrual & Sick Cycle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire BCEA-compliant annual-leave accrual and fixed 36-month sick-leave cycles into the existing Phase-1 leave foundation, plus an auto-draft encashment trigger on termination. No new DocTypes.

**Architecture:** Split the single `SA Standard Leave Policy` into two policies — one for annual-leave-family (calendar-anchored) and one for sick-leave-only (DOJ-anchored with 36-month effective windows). Every active SA employee ends up with two parallel Leave Policy Assignment streams. A daily scheduler emits the next sick-cycle LPA a week before the current one ends; HRMS's native balance query handles cycle-boundary use-or-lose automatically. Termination auto-creates a draft Leave Encashment that HR reviews and submits.

**Tech Stack:** Frappe v16 / Python 3.14 (containerised backend), MariaDB 11.8, Node 24. Test runner: `bench run-tests` (FrappeTestCase, slow, needs test site) + `python -m pytest` (pure functions, fast, no Frappe).

**Companion docs:**
- Spec: `docs/superpowers/specs/2026-04-20-sa-leave-accrual-design.md`
- HR decisions: `docs/superpowers/specs/2026-04-20-sa-leave-accrual-hr-decisions.md`

---

## Preflight

**Dedicated worktree (optional but recommended):** If you're running this plan via subagents, set up a worktree via `superpowers:using-git-worktrees` first. Base branch = `main`; feature branch = `phase-2-leave-accrual`.

**Test site bootstrap:** Some FrappeTestCase tests require a dedicated test site. Create it once before the FrappeTestCase tasks:

```bash
docker exec -u frappe frappe-backend-1 bench new-site test_hrms_za --admin-password test-pw --mariadb-root-password <root-pw>
docker exec -u frappe frappe-backend-1 bench --site test_hrms_za install-app erpnext
docker exec -u frappe frappe-backend-1 bench --site test_hrms_za install-app hrms
docker exec -u frappe frappe-backend-1 bench --site test_hrms_za install-app hrms_za
```

The production site must NEVER be a test target.

**Image rebuild reminder:** After code changes land, rebuild the layered image with `--no-cache-filter=builder`; then redeploy. `redeploy.sh` already exists in the repo and handles this.

---

## File Structure

**New files:**
- `hrms_za/regional/south_africa/cycle_math.py` — pure date helpers (no Frappe imports), including `sa_sick_cycle_window`.
- `hrms_za/regional/south_africa/encashment.py` — pure arithmetic for encashment amount (no Frappe imports).
- `hrms_za/payroll_sa/tests/test_sick_cycle_window.py` — pure-pytest tests for cycle math.
- `hrms_za/payroll_sa/tests/test_leave_encashment_calc.py` — pure-pytest tests for encashment arithmetic.

**Files to modify:**
- `hrms_za/regional/south_africa/data/leave_types.py` — add `allocate_on_day`, `maximum_carry_forwarded_leaves` on Annual Leave (SA); fix "rolling" comment.
- `hrms_za/regional/south_africa/data/leave_policy.py` — replace single policy with two policy definitions.
- `hrms_za/regional/south_africa/setup.py` — split `install_leave_policy`, add `install_sick_cycle_policy`, extend `install_sa_leave_settings_defaults` for six new fields, add two-policy resolver.
- `hrms_za/regional/south_africa/leave.py` — extend `assign_default_policy` for dual streams, add `emit_sick_cycle_lpas`, add `trigger_termination_encashment`, replace `recompute_sick_leave_cycles` stub.
- `hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.json` — add six new fields, fix rolling descriptions.
- `hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.py` — add `on_update` handler to propagate knobs to Leave Type fields.
- `hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.js` — update tooltip, add "Generate Termination Encashment" button.
- `hrms_za/payroll_sa/tests/test_leave_setup.py` — add 18 new FrappeTestCase tests.
- `hrms_za/patches/v0_0_2/backfill_sa_leave_policy_assignments.py` — extend: rename, split, flip flags, backfill both streams.
- `hrms_za/hooks.py` — add daily scheduler task + Employee Separation on_submit doc_event.
- `hrms_za/__init__.py` — bump version to `0.0.2`.
- `README.md`, `PLAN.md` — terminology cleanup (fix 11 "rolling" references across repo as part of task 3).

**Responsibility boundaries:**
- `cycle_math.py` owns date arithmetic. Pure, no I/O, no Frappe.
- `encashment.py` owns encashment amount arithmetic. Pure, no I/O, no Frappe.
- `leave.py` owns runtime wiring — hooks, scheduler, bulk helpers.
- `setup.py` owns install-time seeders.
- `data/*.py` owns seed payloads. No logic; just constants.
- Patch owns migration-only logic, distinct from runtime.

---

## Task 1: Pure helper — `sa_sick_cycle_window` (TDD)

**Files:**
- Create: `hrms_za/regional/south_africa/cycle_math.py`
- Create: `hrms_za/payroll_sa/tests/test_sick_cycle_window.py`

- [ ] **Step 1: Write the failing test file**

Write `hrms_za/payroll_sa/tests/test_sick_cycle_window.py`:

```python
"""
Pure-function tests for sa_sick_cycle_window — no Frappe runtime required.

Run locally:
    python -m pytest hrms_za/payroll_sa/tests/test_sick_cycle_window.py -v
"""

import datetime as _dt

import pytest

from hrms_za.regional.south_africa.cycle_math import sa_sick_cycle_window


D = _dt.date


@pytest.mark.parametrize(
    "doj,on_date,expected_cycle,expected_start,expected_end",
    [
        (D(2023, 5, 1),  D(2023, 5, 1),  0, D(2023, 5, 1),  D(2026, 4, 30)),
        (D(2023, 5, 1),  D(2023, 12, 25),0, D(2023, 5, 1),  D(2026, 4, 30)),
        (D(2023, 5, 1),  D(2026, 4, 30), 0, D(2023, 5, 1),  D(2026, 4, 30)),
        (D(2023, 5, 1),  D(2026, 5, 1),  1, D(2026, 5, 1),  D(2029, 4, 30)),
        (D(2023, 5, 1),  D(2036, 6, 15), 4, D(2035, 5, 1),  D(2038, 4, 30)),
        (D(2024, 2, 29), D(2027, 2, 28), 0, D(2024, 2, 29), D(2027, 2, 28)),
        (D(2024, 2, 29), D(2027, 3, 1),  1, D(2027, 3, 1),  D(2030, 2, 28)),
        (D(2023, 5, 1),  D(2022, 12, 1), 0, D(2023, 5, 1),  D(2026, 4, 30)),
    ],
)
def test_cycle_window(doj, on_date, expected_cycle, expected_start, expected_end):
    cycle, start, end = sa_sick_cycle_window(doj, on_date)
    assert cycle == expected_cycle
    assert start == expected_start
    assert end == expected_end


def test_cycle_end_is_always_one_day_before_next_cycle_start():
    """Fuzz: cycle_start + 36 months == cycle_end + 1 day."""
    import random

    random.seed(42)
    for _ in range(1000):
        doj = D(2000, 1, 1) + _dt.timedelta(days=random.randint(0, 365 * 30))
        offset = random.randint(-365, 365 * 50)
        on_date = doj + _dt.timedelta(days=offset)
        _, start, end = sa_sick_cycle_window(doj, on_date)

        # end + 1 day == next cycle start
        from dateutil.relativedelta import relativedelta
        assert end + _dt.timedelta(days=1) == start + relativedelta(months=36)


def test_returns_python_dates():
    """Output types must be datetime.date, not strings."""
    cycle, start, end = sa_sick_cycle_window(D(2024, 1, 15), D(2024, 6, 1))
    assert isinstance(cycle, int)
    assert isinstance(start, _dt.date)
    assert isinstance(end, _dt.date)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd /home/frappeadmin/hrms_za
python -m pytest hrms_za/payroll_sa/tests/test_sick_cycle_window.py -v
```

Expected: `ModuleNotFoundError: No module named 'hrms_za.regional.south_africa.cycle_math'` (file doesn't exist yet).

- [ ] **Step 3: Write the minimal implementation**

Write `hrms_za/regional/south_africa/cycle_math.py`:

```python
"""
Pure date helpers for South African leave cycles.

This module has NO Frappe imports and NO I/O. It's designed so the cycle
math can be tested with plain pytest against `datetime.date` values,
without standing up a Frappe runtime. Any runtime that wants to work in
Frappe's "string-date world" must convert to `datetime.date` at the
boundary, call these helpers, then convert back.

Key reference: BCEA s22 — "sick leave cycle" = 36 months' employment,
anchored at date of joining (or at end of previous cycle). Each cycle has
a fresh 30-day sick-leave bucket; unused days expire at the boundary.
This is NOT a rolling window — cycles are fixed consecutive blocks.
"""

import datetime as _dt

from dateutil.relativedelta import relativedelta


def sa_sick_cycle_window(doj, on_date):
    """
    Given a date of joining and a query date, return the fixed 36-month
    BCEA sick leave cycle window that contains `on_date`.

    Returns (cycle_number, cycle_start, cycle_end) where:
      - cycle_number is 0 for the first cycle, 1 for the second, etc.
      - cycle_start is the first day of that cycle (date).
      - cycle_end is the last day of that cycle (date) — one day before the
        next cycle starts.

    Edge cases:
      - on_date before doj: returns cycle 0 (the employee's not yet active,
        but the "current" cycle is still the first one).
      - Feb 29 anchors in non-leap target years are normalised to Feb 28 by
        dateutil.relativedelta — matches Frappe's own `add_months` semantics.
    """
    if on_date < doj:
        cycle_number = 0
    else:
        months_elapsed = (on_date.year - doj.year) * 12 + (on_date.month - doj.month)
        if on_date.day < doj.day:
            months_elapsed -= 1
        cycle_number = max(months_elapsed // 36, 0)

    cycle_start = doj + relativedelta(months=36 * cycle_number)
    cycle_end = cycle_start + relativedelta(months=36) - _dt.timedelta(days=1)
    return cycle_number, cycle_start, cycle_end
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /home/frappeadmin/hrms_za
python -m pytest hrms_za/payroll_sa/tests/test_sick_cycle_window.py -v
```

Expected: all 10 tests PASS (8 parametrised + fuzz + type check).

- [ ] **Step 5: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/regional/south_africa/cycle_math.py \
        hrms_za/payroll_sa/tests/test_sick_cycle_window.py
git commit -m "feat(leave): pure sa_sick_cycle_window helper with test matrix"
```

---

## Task 2: Pure helper — encashment arithmetic (TDD)

**Files:**
- Create: `hrms_za/regional/south_africa/encashment.py`
- Create: `hrms_za/payroll_sa/tests/test_leave_encashment_calc.py`

- [ ] **Step 1: Write the failing test file**

Write `hrms_za/payroll_sa/tests/test_leave_encashment_calc.py`:

```python
"""
Pure-function tests for compute_encashment_amount — no Frappe runtime needed.

Run locally:
    python -m pytest hrms_za/payroll_sa/tests/test_leave_encashment_calc.py -v
"""

import pytest

from hrms_za.regional.south_africa.encashment import (
    MissingRate,
    compute_encashment_amount,
)


def test_typical_case():
    assert compute_encashment_amount(balance_days=4.5, per_day_rate=850) == 3825.00


def test_zero_balance():
    assert compute_encashment_amount(balance_days=0, per_day_rate=850) == 0.00


def test_no_rate_raises():
    with pytest.raises(MissingRate):
        compute_encashment_amount(balance_days=4.5, per_day_rate=None)


def test_negative_balance_pays_zero():
    """We never pay out negative balances — they may arise from allow_negative."""
    assert compute_encashment_amount(balance_days=-2.0, per_day_rate=850) == 0.00


def test_fractional_precision_to_two_decimals():
    assert compute_encashment_amount(balance_days=4.333, per_day_rate=850) == 3683.05


def test_rate_zero_raises():
    with pytest.raises(MissingRate):
        compute_encashment_amount(balance_days=4.5, per_day_rate=0)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd /home/frappeadmin/hrms_za
python -m pytest hrms_za/payroll_sa/tests/test_leave_encashment_calc.py -v
```

Expected: `ModuleNotFoundError: No module named 'hrms_za.regional.south_africa.encashment'`.

- [ ] **Step 3: Write the minimal implementation**

Write `hrms_za/regional/south_africa/encashment.py`:

```python
"""
Pure encashment arithmetic for SA leave payout on termination.

No Frappe imports. The Frappe-side caller reads balance + rate from its
sources (get_leave_balance_on, Salary Structure Assignment) and hands
the numbers here for arithmetic.

BCEA s40 requires payout of accrued unused annual leave on termination;
this helper provides the arithmetic that populates `Leave Encashment`
draft documents. Note: BCEA s35 "remuneration" has a specific inclusive
definition — the per-day rate passed in must already honour that. HR
adjusts the draft if the Salary Structure rate doesn't match.
"""


class MissingRate(ValueError):
    """Raised when the per-day rate is absent or zero — cannot compute payout."""


def compute_encashment_amount(balance_days, per_day_rate):
    """
    Return the cash amount owed for `balance_days` of leave at `per_day_rate`.

    - balance_days: days of leave accrued and unused. Negative values return
      0 (we never pay negative balances).
    - per_day_rate: money per day (float or Decimal).

    Raises MissingRate if per_day_rate is None or zero.
    """
    if per_day_rate is None or per_day_rate == 0:
        raise MissingRate(
            "per_day_rate is required to compute encashment amount"
        )

    if balance_days <= 0:
        return 0.00

    amount = float(balance_days) * float(per_day_rate)
    return round(amount, 2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /home/frappeadmin/hrms_za
python -m pytest hrms_za/payroll_sa/tests/test_leave_encashment_calc.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/regional/south_africa/encashment.py \
        hrms_za/payroll_sa/tests/test_leave_encashment_calc.py
git commit -m "feat(leave): pure encashment arithmetic helper"
```

---

## Task 3: Fix "rolling" terminology across the repo (docs only)

**Files modified:**
- `PLAN.md` (3 lines)
- `README.md` (2 lines)
- `hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.json` (2 descriptions)
- `hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.js` (1 tooltip)
- `hrms_za/regional/south_africa/data/leave_policy.py` (2 comments)
- `hrms_za/regional/south_africa/data/leave_types.py` (2 comments)

- [ ] **Step 1: Verify current "rolling" occurrences (sanity check)**

Run:
```bash
cd /home/frappeadmin/hrms_za
grep -rn "rolling" --include='*.md' --include='*.py' --include='*.js' --include='*.json' .
```

Expected: matches in the files listed above. Specs under `docs/superpowers/specs/` should NOT contain "rolling" (already corrected).

- [ ] **Step 2: Rewrite `PLAN.md` references**

Change:
- Line 63: `36-month rolling sick-leave cycle algorithm` → `36-month fixed consecutive sick-leave cycle algorithm (BCEA s22)`
- Line 115: comment on `sick_cycle_months` knob mentioning "Phase 2" remains; no "rolling" word to replace there — no change needed
- Line 340: `Phase 2 (36-month sick cycle)` — already says "sick cycle" not "rolling"; only fix if it does

Re-grep after edits:
```bash
grep -n "rolling" PLAN.md
```

Expected: 0 matches.

- [ ] **Step 3: Rewrite `README.md` references**

Change line 51 from:
```
- 36-month rolling sick leave cycle (BCEA s22).
```
to:
```
- 36-month fixed consecutive sick leave cycle (BCEA s22).
```

Line 41's "rolling" is part of the same feature-list context; apply the same swap.

Re-grep:
```bash
grep -n "rolling" README.md
```

Expected: 0 matches.

- [ ] **Step 4: Rewrite `sa_leave_settings.json` field descriptions**

Edit the two `description` fields:

- `sick_cycle_months`:  
  Old: `"BCEA s22 rolling sick-leave window (months). Consumed by Phase 2 sick-cycle algorithm."`  
  New: `"BCEA s22 fixed sick-leave cycle length (months). Each 36-month cycle starts at the employee's date of joining (or end of previous cycle) and has a fresh bucket."`

- `sick_days_per_cycle`:  
  Old: `"BCEA s22 sick-leave entitlement per rolling cycle (days)."`  
  New: `"BCEA s22 sick-leave entitlement per 36-month cycle (days)."`

- [ ] **Step 5: Rewrite `sa_leave_settings.js` tooltip**

Edit line 43 (the "Recompute Sick Leave Cycles" button tooltip):

Old:
```
__("Phase-2 stub — will recompute every employee's rolling 36-month sick-leave balance once the Phase 2 algorithm lands. Safe to click now (it just returns a status).")
```

New:
```
__("Recompute every employee's fixed 36-month sick-leave cycle. Idempotent — creates next-cycle LPAs for employees within the lookahead window and backfills any missing cycles.")
```

- [ ] **Step 6: Rewrite `data/leave_policy.py` comments**

Edit lines 17–18:

Old:
```python
- BCEA s22: Sick Leave — 30 days per 36-month rolling cycle (modelled as
  flat 30 here; rolling window is a Phase 2 build).
```

New:
```python
- BCEA s22: Sick Leave — 30 days per 36-month fixed consecutive cycle,
  anchored at date of joining. Modelled via the separate SA Sick Leave
  Cycle Policy (not in this file); this file seeds the annual-family policy.
```

- [ ] **Step 7: Rewrite `data/leave_types.py` comments**

Edit lines 7 and 26–28:

Line 7 old:
```python
- BCEA s22: Sick Leave — 30 days per 36-month cycle (placeholder here;
  the rolling 36-month window is NOT yet modelled — see project TODO).
```

Line 7 new:
```python
- BCEA s22: Sick Leave — 30 days per 36-month fixed consecutive cycle.
  The cycle mechanics live in the LPA effective window, not here.
```

Line 26–28 old:
```python
# Sick Leave: BCEA s22 mandates 30 days per 36-month cycle. The rolling
# 36-month window is not modelled yet — treat as 30 days/year until a
# dedicated SA Sick Leave Cycle doctype ships.
```

Line 26–28 new:
```python
# Sick Leave: BCEA s22 mandates 30 days per 36-month fixed consecutive
# cycle. Modelled via LPA effective window in the SA Sick Leave Cycle
# Policy — see regional/south_africa/data/leave_policy.py.
```

- [ ] **Step 8: Verify zero "rolling" references remain**

Run:
```bash
cd /home/frappeadmin/hrms_za
grep -rn "rolling" --include='*.md' --include='*.py' --include='*.js' --include='*.json' . || echo "CLEAN"
```

Expected: `CLEAN` (no hits outside docs/superpowers/specs/ which contain the word as a corrective reference).

- [ ] **Step 9: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add PLAN.md README.md \
        hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.json \
        hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.js \
        hrms_za/regional/south_africa/data/leave_policy.py \
        hrms_za/regional/south_africa/data/leave_types.py
git commit -m "docs(leave): replace 'rolling 36-month window' with 'fixed cycle' terminology

BCEA s22 defines fixed consecutive 36-month cycles (per-employee, DOJ-anchored),
not a rolling window. Eleven references across the repo corrected to match
the actual law and the Phase-2 design."
```

---

## Task 4: Update `leave_types.py` — Annual Leave (SA) earned-leave fields

**Files modified:**
- `hrms_za/regional/south_africa/data/leave_types.py`

- [ ] **Step 1: Apply the edit**

In `hrms_za/regional/south_africa/data/leave_types.py`, replace the Annual Leave (SA) dict (it currently sets `is_earned_leave: 1, earned_leave_frequency: "Monthly", rounding: "0.5"`). Add `allocate_on_day` and `maximum_carry_forwarded_leaves`:

Old:
```python
{
    "leave_type_name": "Annual Leave (SA)",
    "max_leaves_allowed": 15,
    "is_earned_leave": 1,
    "earned_leave_frequency": "Monthly",
    "rounding": "0.5",
    "is_carry_forward": 1,
    "allow_encashment": 1,
    "allow_negative": 0,
},
```

New:
```python
{
    "leave_type_name": "Annual Leave (SA)",
    "max_leaves_allowed": 15,
    "is_earned_leave": 1,
    "earned_leave_frequency": "Monthly",
    "allocate_on_day": "First Day",
    "rounding": "0.5",
    "is_carry_forward": 1,
    "maximum_carry_forwarded_leaves": 5,
    "allow_encashment": 1,
    "allow_negative": 0,
},
```

- [ ] **Step 2: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/regional/south_africa/data/leave_types.py
git commit -m "feat(leave): wire Annual Leave (SA) to monthly earned leave

Sets allocate_on_day=First Day so accruals fire on the 1st of each month
and maximum_carry_forwarded_leaves=5 (matches settings knob default).
Frequency + is_earned_leave already set from Phase 1; this is the
missing wiring."
```

---

## Task 5: Split `leave_policy.py` into two policy definitions

**Files modified:**
- `hrms_za/regional/south_africa/data/leave_policy.py`

- [ ] **Step 1: Replace the file contents**

Overwrite `hrms_za/regional/south_africa/data/leave_policy.py` with:

```python
"""
South African Leave Policy definitions — two policies, not one.

Phase 2 splits what was a single `SA Standard Leave Policy` into:

- `SA Annual Leave Policy` — everything driven by the annual (12-month)
  Leave Period cycle: annual leave, family responsibility, maternity,
  parental, adoption, commissioning, study. LPA effective window matches
  the Leave Period.
- `SA Sick Leave Cycle Policy` — Sick Leave (SA) only. LPA effective
  window is 36 months anchored at the employee's date_of_joining (or
  end of previous cycle). New LPAs emitted by the daily scheduler.

Both are seed-once: if a Leave Policy with the shipped title already
exists (any docstatus), the seeder leaves it alone so HR amendments are
preserved.

References:
- BCEA s20: Annual Leave — 15 working days per 12-month cycle.
- BCEA s22: Sick Leave — 30 days per 36-month fixed consecutive cycle.
- BCEA s25: Maternity Leave — 4 consecutive months.
- BCEA s25A: Parental Leave — 10 consecutive days.
- BCEA s27: Family Responsibility Leave — 3 days per year.

Constant names used by the setup layer:
    ANNUAL_LEAVE_POLICY_NAME, ANNUAL_LEAVE_POLICY_DETAILS
    SICK_CYCLE_POLICY_NAME,  SICK_CYCLE_POLICY_DETAILS

`LEAVE_POLICY_NAME` / `LEAVE_POLICY_DETAILS` are preserved as
backward-compat aliases so the v0.0.2 migration patch can still reference
the pre-split name during the rename step.
"""


ANNUAL_LEAVE_POLICY_NAME = "SA Annual Leave Policy"

ANNUAL_LEAVE_POLICY_DETAILS = [
    {"leave_type": "Annual Leave (SA)",                 "annual_allocation": 15},
    {"leave_type": "Family Responsibility Leave (SA)",  "annual_allocation": 3},
    {"leave_type": "Maternity Leave (SA)",              "annual_allocation": 120},
    {"leave_type": "Parental Leave (SA)",               "annual_allocation": 10},
    {"leave_type": "Adoption Leave (SA)",               "annual_allocation": 70},
    {"leave_type": "Commissioning Parental Leave (SA)", "annual_allocation": 70},
    {"leave_type": "Study Leave (SA)",                  "annual_allocation": 5},
]


SICK_CYCLE_POLICY_NAME = "SA Sick Leave Cycle Policy"

SICK_CYCLE_POLICY_DETAILS = [
    {"leave_type": "Sick Leave (SA)", "annual_allocation": 30},
]


# --- backward-compat aliases ---------------------------------------------
# The v0.0.2 migration patch renames `SA Standard Leave Policy` to
# `SA Annual Leave Policy`; these aliases let the patch reference the old
# name without having to duplicate the constant. Fresh installs never see
# `SA Standard Leave Policy` — the seeder emits the two new names directly.
LEAVE_POLICY_NAME = "SA Standard Leave Policy"
LEAVE_POLICY_DETAILS = ANNUAL_LEAVE_POLICY_DETAILS + SICK_CYCLE_POLICY_DETAILS
```

- [ ] **Step 2: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/regional/south_africa/data/leave_policy.py
git commit -m "feat(leave): split leave policy into annual + sick cycle definitions"
```

---

## Task 6: Extend `sa_leave_settings.json` with six new fields

**Files modified:**
- `hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.json`

- [ ] **Step 1: Add fieldnames to `field_order`**

After the existing `email_section` entry (last in the current `field_order`), append a new section with the six new fields. Modify `field_order` to end with:

```json
  "email_section",
  "notification_from_email",
  "phase2_section",
  "default_sick_cycle_policy",
  "sick_cycle_lookahead_days",
  "phase2_col_break",
  "backfill_missing_cycles",
  "enforce_sick_cycle_cap",
  "annual_leave_applicable_after_days",
  "auto_create_termination_encashment"
```

- [ ] **Step 2: Add the six field definitions to `fields`**

Append these six fields (plus the section break + column break) to the `fields` array, after `notification_from_email`:

```json
  {
    "fieldname": "phase2_section",
    "fieldtype": "Section Break",
    "label": "Sick Cycle + Termination"
  },
  {
    "description": "Policy used when emitting new sick-cycle LPAs. Set by the installer to the seeded SA Sick Leave Cycle Policy; point at a tenant-specific policy if you want.",
    "fieldname": "default_sick_cycle_policy",
    "fieldtype": "Link",
    "label": "Default Sick Cycle Policy",
    "options": "Leave Policy"
  },
  {
    "default": "7",
    "description": "Daily scheduler emits the next-cycle LPA this many days before the current cycle ends. Lower = tighter; higher = safer if the scheduler misses a day.",
    "fieldname": "sick_cycle_lookahead_days",
    "fieldtype": "Int",
    "label": "Sick Cycle Lookahead (Days)",
    "non_negative": 1
  },
  {
    "fieldname": "phase2_col_break",
    "fieldtype": "Column Break"
  },
  {
    "default": "1",
    "description": "When the patch or scheduler finds employees missing historical sick-cycle LPAs, backfill them as non-active records (preserves audit trail). Turn off for fresh tenants with no history to backfill.",
    "fieldname": "backfill_missing_cycles",
    "fieldtype": "Check",
    "label": "Backfill Missing Cycles"
  },
  {
    "default": "1",
    "description": "When on, Sick Leave applications that would exceed the 36-month cycle cap are rejected by HRMS's native validator (allow_negative=0). When off, they're allowed and HR reconciles manually (allow_negative=1). Pushed onto Leave Type Sick Leave (SA) by settings on_update.",
    "fieldname": "enforce_sick_cycle_cap",
    "fieldtype": "Check",
    "label": "Enforce Sick Cycle Cap"
  },
  {
    "default": "0",
    "description": "Working-days-since-joining gate on Annual Leave applications (BCEA-safe). 0 = available from day 1. Pushed onto Leave Type Annual Leave (SA).applicable_after by settings on_update.",
    "fieldname": "annual_leave_applicable_after_days",
    "fieldtype": "Int",
    "label": "Annual Leave Applicable After (Working Days)",
    "non_negative": 1
  },
  {
    "default": "1",
    "description": "When on, Employee Separation submit auto-creates a draft Leave Encashment for the employee's accrued Annual Leave balance. HR reviews + submits. Off = manual button only.",
    "fieldname": "auto_create_termination_encashment",
    "fieldtype": "Check",
    "label": "Auto-Create Termination Encashment"
  }
```

- [ ] **Step 3: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.json
git commit -m "feat(leave-settings): add six phase-2 knobs to SA Leave Settings"
```

---

## Task 7: Add `on_update` handler to `sa_leave_settings.py`

**Files modified:**
- `hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.py`

- [ ] **Step 1: Replace the file contents**

Overwrite `hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.py` with:

```python
"""
SA Leave Settings — Single DocType surfacing every editable knob for the
South-African leave-automation layer.

Everything downstream (the Employee after_insert hook, the scheduler tasks,
the bulk helpers exposed as action buttons) reads its configuration from
here via `frappe.get_single("SA Leave Settings")`. Never hardcode any of
these values elsewhere in hrms_za.

Phase 2 adds an `on_update` handler that propagates the cross-boundary
knobs onto the underlying Leave Type fields so HRMS's native validator
honours them without custom code. Knob-driven, not magic-driven.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class SALeaveSettings(Document):
    def validate(self):
        self._validate_cycle_anchor()

    def _validate_cycle_anchor(self):
        month = self.cycle_start_month
        day = self.cycle_start_day

        if not 1 <= month <= 12:
            frappe.throw(_("Cycle Start Month must be between 1 and 12."))

        if not 1 <= day <= 31:
            frappe.throw(_("Cycle Start Day must be between 1 and 31."))

        # Reject month+day combos that never exist on any real date
        # (e.g. 31 Feb, 31 Apr). Feb 29 is accepted — cycle_start_for_year
        # normalises it to Feb 28 in non-leap years.
        days_per_month = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
                          7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
        if day > days_per_month[month]:
            frappe.throw(
                _("Day {0} is not valid for month {1}.").format(day, month)
            )

    def on_update(self):
        """
        Propagate the three cross-boundary knobs onto the underlying
        Leave Type fields. After this, HRMS's native Leave Application
        validator honours the settings without any custom validator path.
        """
        self._propagate_annual_leave_applicable_after()
        self._propagate_carry_forward_max()
        self._propagate_sick_cycle_enforcement()

    def _propagate_annual_leave_applicable_after(self):
        value = int(self.annual_leave_applicable_after_days or 0)
        if frappe.db.exists("Leave Type", "Annual Leave (SA)"):
            current = frappe.db.get_value(
                "Leave Type", "Annual Leave (SA)", "applicable_after"
            )
            if (current or 0) != value:
                frappe.db.set_value(
                    "Leave Type", "Annual Leave (SA)", "applicable_after", value,
                )

    def _propagate_carry_forward_max(self):
        value = float(self.annual_leave_carry_forward_max or 0)
        if frappe.db.exists("Leave Type", "Annual Leave (SA)"):
            current = frappe.db.get_value(
                "Leave Type", "Annual Leave (SA)", "maximum_carry_forwarded_leaves",
            )
            if (current or 0) != value:
                frappe.db.set_value(
                    "Leave Type", "Annual Leave (SA)",
                    "maximum_carry_forwarded_leaves", value,
                )

    def _propagate_sick_cycle_enforcement(self):
        """
        enforce_sick_cycle_cap=1 → Leave Type.allow_negative=0 (HRMS rejects
        applications that would exceed the cycle cap).
        enforce_sick_cycle_cap=0 → Leave Type.allow_negative=1 (HRMS allows
        drawdown past 0; HR reconciles on payroll).
        """
        allow_negative = 0 if self.enforce_sick_cycle_cap else 1
        if frappe.db.exists("Leave Type", "Sick Leave (SA)"):
            current = frappe.db.get_value(
                "Leave Type", "Sick Leave (SA)", "allow_negative"
            )
            if (current or 0) != allow_negative:
                frappe.db.set_value(
                    "Leave Type", "Sick Leave (SA)",
                    "allow_negative", allow_negative,
                )
```

- [ ] **Step 2: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.py
git commit -m "feat(leave-settings): on_update propagates knobs to Leave Type fields"
```

---

## Task 8: Extend `setup.py::install_leave_policy` — emit two policies + resolvers

**Files modified:**
- `hrms_za/regional/south_africa/setup.py`

- [ ] **Step 1: Update the imports block**

In `hrms_za/regional/south_africa/setup.py`, replace the `leave_policy` import:

Old:
```python
from hrms_za.regional.south_africa.data.leave_policy import (
    LEAVE_POLICY_DETAILS,
    LEAVE_POLICY_NAME,
)
```

New:
```python
from hrms_za.regional.south_africa.data.leave_policy import (
    ANNUAL_LEAVE_POLICY_DETAILS,
    ANNUAL_LEAVE_POLICY_NAME,
    SICK_CYCLE_POLICY_DETAILS,
    SICK_CYCLE_POLICY_NAME,
)
```

- [ ] **Step 2: Replace `install_leave_policy()`**

Replace the existing `install_leave_policy()` function with a two-policy version:

```python
def install_leave_policy():
    """
    Seed two Leave Policies:
      - SA Annual Leave Policy (calendar-year cycle, 7 leave types).
      - SA Sick Leave Cycle Policy (36-month DOJ-anchored cycle, sick only).

    Both are submittable — seeder calls `.insert()` then `.submit()`.
    Both are seed-once: if a Leave Policy with the shipped title already
    exists in any state, the seeder leaves it alone (HR amendments are
    preserved).

    Must run AFTER `install_leave_types()` in `setup_site_wide()` — child
    rows reference the leave-type records by name.
    """
    _seed_policy_if_missing(ANNUAL_LEAVE_POLICY_NAME, ANNUAL_LEAVE_POLICY_DETAILS)
    _seed_policy_if_missing(SICK_CYCLE_POLICY_NAME, SICK_CYCLE_POLICY_DETAILS)


def _seed_policy_if_missing(title, details):
    if frappe.db.exists("Leave Policy", {"title": title}):
        return
    doc = frappe.get_doc({
        "doctype": "Leave Policy",
        "title": title,
        "leave_policy_details": details,
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
```

- [ ] **Step 3: Replace `resolve_sa_standard_leave_policy` with two resolvers**

Replace the existing `resolve_sa_standard_leave_policy()` function with:

```python
def resolve_sa_standard_leave_policy():
    """
    Backward-compat resolver for Phase-1 call sites. Returns the
    autogenerated name of the annual-leave policy regardless of whether
    the record still has its pre-split title or has been renamed.
    """
    # Post-rename: prefer the new name
    name = frappe.db.get_value(
        "Leave Policy",
        {"title": ANNUAL_LEAVE_POLICY_NAME, "docstatus": 1},
        "name",
    )
    if name:
        return name
    # Pre-rename fallback — patch may not have run yet
    return frappe.db.get_value(
        "Leave Policy",
        {"title": "SA Standard Leave Policy", "docstatus": 1},
        "name",
    )


def resolve_sa_annual_leave_policy():
    """Autogenerated record name of the submitted SA Annual Leave Policy."""
    return resolve_sa_standard_leave_policy()


def resolve_sa_sick_cycle_policy():
    """Autogenerated record name of the submitted SA Sick Leave Cycle Policy."""
    return frappe.db.get_value(
        "Leave Policy",
        {"title": SICK_CYCLE_POLICY_NAME, "docstatus": 1},
        "name",
    )
```

- [ ] **Step 4: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/regional/south_africa/setup.py
git commit -m "feat(leave): two-policy seeder + annual/sick resolver helpers"
```

---

## Task 9: Extend `install_sa_leave_settings_defaults` for six new knobs

**Files modified:**
- `hrms_za/regional/south_africa/setup.py`

- [ ] **Step 1: Extend the `defaults` dict and add the sick-cycle resolver**

In `hrms_za/regional/south_africa/setup.py`, replace `install_sa_leave_settings_defaults()` body. Keep the outer docstring and structure; add the six new field defaults and a resolver for `default_sick_cycle_policy`:

```python
def install_sa_leave_settings_defaults():
    """
    Populate SA Leave Settings (Single) with sensible first-run defaults.

    Contract: only fill fields that are currently empty. HR edits survive
    re-install.

    `default_leave_policy` and `default_sick_cycle_policy` are special:
    only set if their target policy records exist. `install_leave_policy()`
    seeds both earlier in `setup_site_wide()`, so the links are normally
    available by the time this runs.
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
        # Phase 2 defaults
        "sick_cycle_lookahead_days": 7,
        "backfill_missing_cycles": 1,
        "enforce_sick_cycle_cap": 1,
        "annual_leave_applicable_after_days": 0,
        "auto_create_termination_encashment": 1,
    }

    settings = frappe.get_single("SA Leave Settings")
    changed = False

    for fieldname, value in defaults.items():
        if not settings.get(fieldname):
            settings.set(fieldname, value)
            changed = True

    if not settings.get("default_leave_policy"):
        resolved = resolve_sa_annual_leave_policy()
        if resolved:
            settings.set("default_leave_policy", resolved)
            changed = True

    if not settings.get("default_sick_cycle_policy"):
        resolved = resolve_sa_sick_cycle_policy()
        if resolved:
            settings.set("default_sick_cycle_policy", resolved)
            changed = True

    if changed:
        settings.save(ignore_permissions=True)
```

- [ ] **Step 2: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/regional/south_africa/setup.py
git commit -m "feat(leave-settings): seed six phase-2 defaults + sick-cycle policy link"
```

---

## Task 10: Extend `assign_default_policy` for dual-stream LPA creation

**Files modified:**
- `hrms_za/regional/south_africa/leave.py`

- [ ] **Step 1: Update imports**

In `hrms_za/regional/south_africa/leave.py`, replace the `setup` import block:

Old:
```python
from hrms_za.regional.south_africa.setup import (
    anchor_date,
    current_cycle_window_for_date,
    resolve_sa_standard_leave_policy,
)
```

New:
```python
from dateutil.relativedelta import relativedelta

from hrms_za.regional.south_africa.cycle_math import sa_sick_cycle_window
from hrms_za.regional.south_africa.setup import (
    anchor_date,
    current_cycle_window_for_date,
    resolve_sa_annual_leave_policy,
    resolve_sa_sick_cycle_policy,
    resolve_sa_standard_leave_policy,
)
```

- [ ] **Step 2: Extend `_try_assign_default_policy` — both streams**

Replace the body of `_try_assign_default_policy` with a dual-stream variant. The function should still return True if *either* policy was successfully assigned (so the patch's "counted as success" accounting continues to work).

Replace the existing function body with:

```python
def _try_assign_default_policy(employee):
    """
    Resolve the assignment context for one Employee, apply both annual and
    sick-cycle policies, record any guard-triggered skip as a Comment, and
    return True iff at least one LPA was created + submitted.
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

    any_created = False

    # --- Annual stream (Leave Period anchored) ---
    annual_policy = (
        settings.get("default_leave_policy")
        or resolve_sa_annual_leave_policy()
    )
    period_name = _resolve_current_leave_period(employee.company)
    period_from = period_to = None
    if period_name:
        lp = frappe.get_doc("Leave Period", period_name)
        period_from, period_to = lp.from_date, lp.to_date

    annual_status = _apply_policy_for_employee(
        employee, annual_policy, period_name, period_from, period_to,
    )
    if annual_status == _POLICY_APPLIED:
        any_created = True
    else:
        _skip_with_comment(
            employee,
            _policy_skip_message(annual_status, employee, period_to),
        )

    # --- Sick cycle stream (DOJ-anchored) ---
    sick_policy = (
        settings.get("default_sick_cycle_policy")
        or resolve_sa_sick_cycle_policy()
    )
    sick_status = _apply_sick_cycle_policy(employee, sick_policy)
    if sick_status == _POLICY_APPLIED:
        any_created = True
    elif sick_status != _POLICY_SKIPPED_SHORT_TENURE:
        # Short-tenure doesn't apply to DOJ-anchored sick LPAs (cycle is
        # always 36 months). Other skip reasons still worth a Comment.
        _skip_with_comment(
            employee,
            _policy_skip_message(sick_status, employee, None),
        )

    return any_created
```

- [ ] **Step 3: Add `_apply_sick_cycle_policy` helper**

Add this function below `_apply_policy_for_employee` (it deliberately doesn't use Leave Period — sick cycle is DOJ-anchored):

```python
def _apply_sick_cycle_policy(emp, policy_name):
    """
    Create + submit a Leave Policy Assignment for the employee's CURRENT
    sick cycle (DOJ-anchored, 36-month window). Returns a _POLICY_* status
    constant.
    """
    if not emp.date_of_joining:
        return _POLICY_SKIPPED_NO_DOJ

    if not policy_name or not frappe.db.exists("Leave Policy", policy_name):
        return _POLICY_SKIPPED_NO_POLICY

    doj = getdate(emp.date_of_joining)
    today = getdate(frappe.utils.today())
    _, cycle_start, cycle_end = sa_sick_cycle_window(doj, today)

    # Idempotency: skip if an LPA for this exact window already exists
    if frappe.db.exists(
        "Leave Policy Assignment",
        {
            "employee": emp.name,
            "assignment_based_on": "Joining Date",
            "effective_from": cycle_start,
            "docstatus": 1,
        },
    ):
        return _POLICY_APPLIED  # already present — count as success

    _create_leave_policy_assignment(
        employee=emp.name,
        policy_name=policy_name,
        leave_period=None,
        effective_from=cycle_start,
        effective_to=cycle_end,
        assignment_based_on="Joining Date",
    )
    return _POLICY_APPLIED
```

- [ ] **Step 4: Update `_create_leave_policy_assignment` to accept `assignment_based_on`**

Replace the existing function signature and body with:

```python
def _create_leave_policy_assignment(
    employee, policy_name, leave_period, effective_from, effective_to,
    carry_forward=0, assignment_based_on="Leave Period",
):
    """
    Wrapper over HRMS's `create_assignment`. The upstream helper saves as
    draft; Leave Allocations only materialise on submit, so we submit here.

    `assignment_based_on`: "Leave Period" for annual stream, "Joining Date"
    for sick cycle stream. The latter ignores leave_period.
    """
    from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import (
        create_assignment,
    )

    data = {
        "assignment_based_on": assignment_based_on,
        "leave_policy": policy_name,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "carry_forward": int(carry_forward),
    }
    if assignment_based_on == "Leave Period" and leave_period:
        data["leave_period"] = leave_period

    assignment = create_assignment(employee, frappe._dict(data))
    assignment.submit()
    return assignment
```

- [ ] **Step 5: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/regional/south_africa/leave.py
git commit -m "feat(leave): assign both annual + sick cycle policies on hire"
```

---

## Task 11: Implement `emit_sick_cycle_lpas` scheduler task

**Files modified:**
- `hrms_za/regional/south_africa/leave.py`

- [ ] **Step 1: Add the scheduler function**

Add this function to `hrms_za/regional/south_africa/leave.py` below the existing `_apply_sick_cycle_policy` helper:

```python
@frappe.whitelist()
def emit_sick_cycle_lpas():
    """
    Daily scheduler task — maintain the sick-cycle LPA stream for every
    active SA employee.

    Two cohorts are handled in one pass:
      1. Employees whose current sick LPA ends within `lookahead_days` —
         emit the next cycle's LPA.
      2. Employees with NO active sick LPA — emit one for their current
         cycle window (gap recovery).

    Result shape matches the other bulk helpers so the settings .js
    toast stays consistent: {"created": N, "skipped": N, "failed": [...]}.
    """
    result = _empty_result()

    settings = frappe.get_cached_doc("SA Leave Settings")
    if not settings.get("enabled"):
        return result

    lookahead = int(settings.get("sick_cycle_lookahead_days") or 7)
    policy_name = (
        settings.get("default_sick_cycle_policy")
        or resolve_sa_sick_cycle_policy()
    )
    if not policy_name:
        _record_failure(result, "SA Sick Leave Cycle Policy not seeded")
        return result

    employees = _active_sa_employees()
    if not employees:
        return result

    today = getdate(frappe.utils.today())
    horizon = today + relativedelta(days=lookahead)

    for emp in employees:
        try:
            status = _emit_sick_cycle_for_employee(
                emp, policy_name, today, horizon,
            )
            if status == "created":
                result["created"] += 1
            else:
                result["skipped"] += 1
        except Exception as exc:
            _record_failure(result, f"{emp.name}: {exc}")

    frappe.logger("hrms_za.leave").info(
        "emit_sick_cycle_lpas complete — "
        f"created={result['created']} skipped={result['skipped']} "
        f"failed={len(result['failed'])}"
    )
    return result


def _emit_sick_cycle_for_employee(emp, policy_name, today, horizon):
    """
    Return "created" if we inserted + submitted a new LPA for this
    employee, else "skipped".
    """
    if not emp.date_of_joining:
        return "skipped"

    doj = getdate(emp.date_of_joining)
    _, current_start, current_end = sa_sick_cycle_window(doj, today)

    # Decide which cycle window to emit.
    if current_end < horizon:
        # Within lookahead window — emit NEXT cycle.
        effective_from = current_end + relativedelta(days=1)
    else:
        # Not near boundary — emit CURRENT cycle only if missing.
        effective_from = current_start

    effective_to = effective_from + relativedelta(months=36) - relativedelta(days=1)

    # Idempotency
    if frappe.db.exists(
        "Leave Policy Assignment",
        {
            "employee": emp.name,
            "assignment_based_on": "Joining Date",
            "effective_from": effective_from,
            "docstatus": 1,
        },
    ):
        return "skipped"

    _create_leave_policy_assignment(
        employee=emp.name,
        policy_name=policy_name,
        leave_period=None,
        effective_from=effective_from,
        effective_to=effective_to,
        assignment_based_on="Joining Date",
    )
    return "created"
```

- [ ] **Step 2: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/regional/south_africa/leave.py
git commit -m "feat(leave): daily scheduler emits sick-cycle LPAs on boundary"
```

---

## Task 12: Implement `trigger_termination_encashment`

**Files modified:**
- `hrms_za/regional/south_africa/leave.py`

- [ ] **Step 1: Add the termination trigger + manual-button helper**

Add to `hrms_za/regional/south_africa/leave.py`, below `_emit_sick_cycle_for_employee`:

```python
@frappe.whitelist()
def generate_termination_encashment(employee, separation_date=None):
    """
    Manual-button equivalent to the hook — lets HR trigger encashment on
    demand (e.g. when the auto knob is off, or when the auto path failed
    and the underlying problem has been fixed).
    """
    return _create_termination_encashment_draft(
        employee, separation_date or frappe.utils.today(),
    )


def trigger_termination_encashment(doc, method=None):
    """
    Doc event on Employee Separation.on_submit. Creates a draft
    Leave Encashment for the accrued Annual Leave (SA) balance on the
    employee's relieving date. Never raises — any failure is logged and
    a Comment is left on the Employee timeline.

    If auto_create_termination_encashment=0, this hook is a no-op; HR
    uses the manual button instead.
    """
    try:
        settings = frappe.get_cached_doc("SA Leave Settings")
        if not settings.get("auto_create_termination_encashment"):
            return

        employee = getattr(doc, "employee", None)
        separation_date = (
            getattr(doc, "relieving_date", None)
            or getattr(doc, "resignation_letter_date", None)
            or frappe.utils.today()
        )
        if not employee:
            return

        _create_termination_encashment_draft(employee, separation_date)
    except Exception as exc:
        frappe.log_error(
            title="hrms_za: termination encashment trigger failed",
            message=f"Separation: {doc.name if hasattr(doc, 'name') else '?'}, "
                    f"err: {exc}",
        )
        try:
            emp = getattr(doc, "employee", None)
            if emp and frappe.db.exists("Employee", emp):
                frappe.get_doc("Employee", emp).add_comment(
                    "Info",
                    "Termination encashment not auto-created — see Error Log.",
                )
        except Exception:
            pass


def _create_termination_encashment_draft(employee, separation_date):
    """
    Core logic: compute annual balance, skip if zero, else create a DRAFT
    Leave Encashment (docstatus=0) for HR to review. BCEA s40: only annual
    leave is encashed at termination; sick leave is not.
    """
    from hrms.hr.doctype.leave_application.leave_application import (
        get_leave_balance_on,
    )

    leave_type = "Annual Leave (SA)"
    balance = get_leave_balance_on(employee, leave_type, separation_date) or 0
    if balance <= 0:
        return {"status": "no_balance", "balance": float(balance)}

    # Already drafted?
    existing = frappe.db.exists(
        "Leave Encashment",
        {"employee": employee, "leave_type": leave_type, "docstatus": 0},
    )
    if existing:
        return {"status": "already_drafted", "name": existing}

    encashment = frappe.get_doc({
        "doctype": "Leave Encashment",
        "employee": employee,
        "leave_type": leave_type,
        "encashment_date": separation_date,
        "encashment_days": balance,
    })
    # Let HRMS's validate() pull the per-day rate from Salary Structure
    encashment.insert(ignore_permissions=True)
    return {"status": "drafted", "name": encashment.name, "days": balance}
```

- [ ] **Step 2: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/regional/south_africa/leave.py
git commit -m "feat(leave): draft Leave Encashment on Employee Separation submit"
```

---

## Task 13: Replace `recompute_sick_leave_cycles` stub with real impl

**Files modified:**
- `hrms_za/regional/south_africa/leave.py`

- [ ] **Step 1: Replace the stub**

In `hrms_za/regional/south_africa/leave.py`, find and replace:

Old:
```python
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
```

New:
```python
@frappe.whitelist()
def recompute_sick_leave_cycles():
    """
    Bulk wrapper — does what the daily scheduler does, callable on demand
    from the SA Leave Settings button. Idempotent. Same result shape as
    the other bulk helpers for toast consistency.
    """
    return emit_sick_cycle_lpas()
```

- [ ] **Step 2: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/regional/south_africa/leave.py
git commit -m "feat(leave): wire Recompute Sick Leave Cycles button to scheduler"
```

---

## Task 14: Update `hooks.py` — scheduler + termination doc_event

**Files modified:**
- `hrms_za/hooks.py`

- [ ] **Step 1: Add Employee Separation on_submit + daily scheduler**

Replace the existing `doc_events` and `scheduler_events` blocks:

Old:
```python
doc_events = {
    "Company": {
        "on_update": "hrms_za.regional.south_africa.setup.on_company_update",
    },
    "Salary Slip": {
        "validate": "hrms_za.payroll_sa.paye_calculator.adjust_sa_paye",
    },
    "Employee": {
        "after_insert": "hrms_za.regional.south_africa.leave.assign_default_policy",
    },
}


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

New:
```python
doc_events = {
    "Company": {
        "on_update": "hrms_za.regional.south_africa.setup.on_company_update",
    },
    "Salary Slip": {
        "validate": "hrms_za.payroll_sa.paye_calculator.adjust_sa_paye",
    },
    "Employee": {
        "after_insert": "hrms_za.regional.south_africa.leave.assign_default_policy",
    },
    "Employee Separation": {
        "on_submit": "hrms_za.regional.south_africa.leave.trigger_termination_encashment",
    },
}


scheduler_events = {
    "daily": [
        "hrms_za.regional.south_africa.leave.emit_sick_cycle_lpas",
    ],
    "daily_long": [
        "hrms_za.regional.south_africa.leave.recompute_sick_leave_cycles",
    ],
    "weekly": [
        "hrms_za.regional.south_africa.leave.nudge_pending_leave_approvals",
        "hrms_za.regional.south_africa.leave.email_low_balance_employees",
    ],
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/hooks.py
git commit -m "feat(hooks): wire daily sick-cycle emitter + termination encashment"
```

---

## Task 15: Update `sa_leave_settings.js` — button + tooltips

**Files modified:**
- `hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.js`

- [ ] **Step 1: Read the existing JS file**

```bash
cat hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.js
```

- [ ] **Step 2: Add the "Generate Termination Encashment" button**

Below the existing `frm.add_custom_button` invocations, append a new one that prompts for an Employee and calls `generate_termination_encashment`:

```javascript
frm.add_custom_button(__("Generate Termination Encashment"),
    () => {
        frappe.prompt(
            [
                {
                    fieldtype: "Link",
                    fieldname: "employee",
                    label: __("Employee"),
                    options: "Employee",
                    reqd: 1,
                },
                {
                    fieldtype: "Date",
                    fieldname: "separation_date",
                    label: __("Separation Date"),
                    default: frappe.datetime.get_today(),
                },
            ],
            values => {
                frappe.call({
                    method: "hrms_za.regional.south_africa.leave.generate_termination_encashment",
                    args: values,
                    freeze: true,
                    freeze_message: __("Creating draft Leave Encashment..."),
                    callback: r => {
                        if (r.message && r.message.status === "drafted") {
                            frappe.show_alert({
                                message: __("Draft Leave Encashment created for {0} days.",
                                    [r.message.days]),
                                indicator: "green",
                            });
                            frappe.set_route(
                                "Form", "Leave Encashment", r.message.name,
                            );
                        } else if (r.message && r.message.status === "no_balance") {
                            frappe.show_alert({
                                message: __("No Annual Leave balance to encash."),
                                indicator: "orange",
                            });
                        } else if (r.message && r.message.status === "already_drafted") {
                            frappe.set_route(
                                "Form", "Leave Encashment", r.message.name,
                            );
                        }
                    },
                });
            },
            __("Generate Termination Encashment"),
            __("Create Draft"),
        );
    },
);
```

- [ ] **Step 3: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/payroll_sa/doctype/sa_leave_settings/sa_leave_settings.js
git commit -m "feat(leave-settings): 'Generate Termination Encashment' button"
```

---

## Task 16: Extend v0.0.2 backfill patch — rename, split, flip, dual-stream

**Files modified:**
- `hrms_za/patches/v0_0_2/backfill_sa_leave_policy_assignments.py`

- [ ] **Step 1: Replace the patch body with the extended version**

Overwrite `hrms_za/patches/v0_0_2/backfill_sa_leave_policy_assignments.py` with:

```python
"""
v0.0.2 migration patch — brings a Phase-1 site to Phase-2 shape.

This patch runs once via bench migrate. It is fully idempotent: a second
run converges to the same state and prints zero deltas.

Steps performed (each guarded and skip-on-already-done):

1. Rename `SA Standard Leave Policy` → `SA Annual Leave Policy` (if the
   pre-split name is present).
2. Remove the Sick Leave (SA) row from the (renamed) annual policy's
   child table — sick leave now lives in its own policy.
3. Ensure the `SA Sick Leave Cycle Policy` record exists (calls the
   seeder path).
4. Update `Annual Leave (SA)` Leave Type: set allocate_on_day,
   maximum_carry_forwarded_leaves.
5. Trigger settings `on_update` to propagate knobs to Leave Type fields.
6. Backfill annual LPA for every active SA employee without one for
   today's Leave Period.
7. Backfill sick cycle LPA for every active SA employee without one
   for their current cycle.
8. If `backfill_missing_cycles=1`, also create historical sick cycle
   LPAs as records (their to_date < today so they're not active).

Shares `_try_assign_default_policy` with the Employee.after_insert hook —
the guard chain never drifts between the two paths.
"""

import frappe


def execute():
    for required in (
        "Leave Policy Assignment", "Leave Period", "Leave Policy", "Leave Type",
    ):
        if not frappe.db.exists("DocType", required):
            print(f"[hrms_za v0.0.2] {required} not yet migrated; skipping.")
            return

    print("[hrms_za v0.0.2] starting Phase-2 migration")

    step_counts = {
        "renamed": 0,
        "sick_row_removed": 0,
        "sick_policy_seeded": 0,
        "leave_type_updated": 0,
        "settings_on_update": 0,
        "emp_annual_created": 0,
        "emp_sick_created": 0,
        "emp_historical_created": 0,
        "failed": 0,
    }

    _rename_standard_to_annual(step_counts)
    _remove_sick_row_from_annual(step_counts)
    _ensure_sick_cycle_policy(step_counts)
    _update_annual_leave_type(step_counts)
    _trigger_settings_on_update(step_counts)
    _backfill_all_employees(step_counts)

    print("[hrms_za v0.0.2] migration complete:")
    for k, v in step_counts.items():
        print(f"  {k} = {v}")


def _rename_standard_to_annual(counts):
    old_title = "SA Standard Leave Policy"
    new_title = "SA Annual Leave Policy"

    row = frappe.db.get_value(
        "Leave Policy", {"title": old_title}, ["name", "docstatus"],
    )
    if not row:
        return
    name, docstatus = row
    frappe.db.set_value("Leave Policy", name, "title", new_title)
    counts["renamed"] = 1
    print(f"[hrms_za v0.0.2] renamed {name}: '{old_title}' → '{new_title}' (docstatus={docstatus})")


def _remove_sick_row_from_annual(counts):
    from hrms_za.regional.south_africa.data.leave_policy import (
        ANNUAL_LEAVE_POLICY_NAME,
    )

    policy_name = frappe.db.get_value(
        "Leave Policy", {"title": ANNUAL_LEAVE_POLICY_NAME}, "name",
    )
    if not policy_name:
        return

    rows = frappe.get_all(
        "Leave Policy Detail",
        filters={"parent": policy_name, "leave_type": "Sick Leave (SA)"},
        pluck="name",
    )
    for row_name in rows:
        frappe.delete_doc("Leave Policy Detail", row_name, ignore_permissions=True)
        counts["sick_row_removed"] += 1


def _ensure_sick_cycle_policy(counts):
    from hrms_za.regional.south_africa.data.leave_policy import (
        SICK_CYCLE_POLICY_DETAILS,
        SICK_CYCLE_POLICY_NAME,
    )

    if frappe.db.exists("Leave Policy", {"title": SICK_CYCLE_POLICY_NAME}):
        return

    doc = frappe.get_doc({
        "doctype": "Leave Policy",
        "title": SICK_CYCLE_POLICY_NAME,
        "leave_policy_details": SICK_CYCLE_POLICY_DETAILS,
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    counts["sick_policy_seeded"] = 1


def _update_annual_leave_type(counts):
    name = "Annual Leave (SA)"
    if not frappe.db.exists("Leave Type", name):
        return
    doc = frappe.get_doc("Leave Type", name)
    changed = False
    if doc.allocate_on_day != "First Day":
        doc.allocate_on_day = "First Day"
        changed = True
    if float(doc.maximum_carry_forwarded_leaves or 0) != 5.0:
        doc.maximum_carry_forwarded_leaves = 5
        changed = True
    if changed:
        doc.save(ignore_permissions=True)
        counts["leave_type_updated"] = 1


def _trigger_settings_on_update(counts):
    try:
        settings = frappe.get_single("SA Leave Settings")
        # touch + save to fire the on_update propagation
        settings.save(ignore_permissions=True)
        counts["settings_on_update"] = 1
    except Exception as exc:
        print(f"[hrms_za v0.0.2] settings on_update skipped: {exc}")


def _backfill_all_employees(counts):
    from hrms_za.regional.south_africa.leave import _try_assign_default_policy

    sa_companies = frappe.get_all(
        "Company", filters={"country": "South Africa"}, pluck="name"
    )
    if not sa_companies:
        print("[hrms_za v0.0.2] no SA companies on this site; skipping backfill.")
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

    today = frappe.utils.today()

    for emp_name in employees:
        try:
            _backfill_one_employee(emp_name, today, counts)
        except Exception as exc:
            counts["failed"] += 1
            frappe.log_error(
                title="hrms_za v0.0.2 backfill: employee failed",
                message=f"Employee: {emp_name}\n{exc}",
            )


def _backfill_one_employee(emp_name, today, counts):
    emp = frappe.get_doc("Employee", emp_name)

    # Count annual LPAs currently active
    annual_active = frappe.db.exists(
        "Leave Policy Assignment",
        {
            "employee": emp_name,
            "assignment_based_on": "Leave Period",
            "docstatus": 1,
            "effective_from": ["<=", today],
            "effective_to": [">=", today],
        },
    )
    sick_active = frappe.db.exists(
        "Leave Policy Assignment",
        {
            "employee": emp_name,
            "assignment_based_on": "Joining Date",
            "docstatus": 1,
            "effective_from": ["<=", today],
            "effective_to": [">=", today],
        },
    )

    if annual_active and sick_active:
        return

    before = {
        "annual_lpas": frappe.db.count("Leave Policy Assignment", {
            "employee": emp_name, "assignment_based_on": "Leave Period",
            "docstatus": 1,
        }),
        "sick_lpas": frappe.db.count("Leave Policy Assignment", {
            "employee": emp_name, "assignment_based_on": "Joining Date",
            "docstatus": 1,
        }),
    }

    _try_assign_default_policy(emp)

    after = {
        "annual_lpas": frappe.db.count("Leave Policy Assignment", {
            "employee": emp_name, "assignment_based_on": "Leave Period",
            "docstatus": 1,
        }),
        "sick_lpas": frappe.db.count("Leave Policy Assignment", {
            "employee": emp_name, "assignment_based_on": "Joining Date",
            "docstatus": 1,
        }),
    }

    counts["emp_annual_created"] += after["annual_lpas"] - before["annual_lpas"]
    counts["emp_sick_created"] += after["sick_lpas"] - before["sick_lpas"]

    settings = frappe.get_cached_doc("SA Leave Settings")
    if settings.get("backfill_missing_cycles"):
        counts["emp_historical_created"] += _backfill_historical_cycles(emp, today)


def _backfill_historical_cycles(emp, today):
    """Emit LPAs for all FULLY-elapsed sick cycles (cycle_end < today)."""
    from dateutil.relativedelta import relativedelta

    from hrms_za.regional.south_africa.cycle_math import sa_sick_cycle_window
    from hrms_za.regional.south_africa.leave import (
        _create_leave_policy_assignment,
    )
    from hrms_za.regional.south_africa.setup import (
        resolve_sa_sick_cycle_policy,
    )

    policy_name = resolve_sa_sick_cycle_policy()
    if not policy_name:
        return 0

    doj = frappe.utils.getdate(emp.date_of_joining)
    today_d = frappe.utils.getdate(today)
    current_cycle, _, _ = sa_sick_cycle_window(doj, today_d)

    created = 0
    for n in range(current_cycle):
        window_start = doj + relativedelta(months=36 * n)
        window_end = window_start + relativedelta(months=36) - relativedelta(days=1)

        if frappe.db.exists(
            "Leave Policy Assignment",
            {
                "employee": emp.name,
                "assignment_based_on": "Joining Date",
                "effective_from": window_start,
                "docstatus": 1,
            },
        ):
            continue

        try:
            _create_leave_policy_assignment(
                employee=emp.name,
                policy_name=policy_name,
                leave_period=None,
                effective_from=window_start,
                effective_to=window_end,
                assignment_based_on="Joining Date",
            )
            created += 1
        except Exception as exc:
            frappe.log_error(
                title="hrms_za v0.0.2 backfill: historical cycle failed",
                message=f"Employee: {emp.name}, cycle {n}\n{exc}",
            )

    return created
```

- [ ] **Step 2: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/patches/v0_0_2/backfill_sa_leave_policy_assignments.py
git commit -m "feat(patch): v0.0.2 rename, split, flip flags, backfill both streams"
```

---

## Task 17: FrappeTestCase integration tests (extend `test_leave_setup.py`)

**Files modified:**
- `hrms_za/payroll_sa/tests/test_leave_setup.py`

- [ ] **Step 1: Read the current test file as a reference**

```bash
wc -l hrms_za/payroll_sa/tests/test_leave_setup.py
head -60 hrms_za/payroll_sa/tests/test_leave_setup.py
```

Use the existing Phase-1 tests' conventions (imports, helpers, test-site setUpClass/tearDown patterns) when adding the new tests.

- [ ] **Step 2: Append Phase-2 test cases**

Add the following to `hrms_za/payroll_sa/tests/test_leave_setup.py` (inside the existing test class, OR as a new `class Phase2Tests(FrappeTestCase)` at file end — your call based on existing file shape):

```python
    # -------------------------- Phase 2 tests ----------------------------

    def test_policy_split_after_install(self):
        """Both SA Annual Leave Policy and SA Sick Leave Cycle Policy exist."""
        annual = frappe.db.get_value(
            "Leave Policy",
            {"title": "SA Annual Leave Policy", "docstatus": 1},
            "name",
        )
        sick = frappe.db.get_value(
            "Leave Policy",
            {"title": "SA Sick Leave Cycle Policy", "docstatus": 1},
            "name",
        )
        self.assertIsNotNone(annual)
        self.assertIsNotNone(sick)

    def test_annual_leave_type_is_earned_monthly(self):
        lt = frappe.get_doc("Leave Type", "Annual Leave (SA)")
        self.assertEqual(int(lt.is_earned_leave), 1)
        self.assertEqual(lt.earned_leave_frequency, "Monthly")
        self.assertEqual(lt.allocate_on_day, "First Day")

    def test_patch_rename_is_idempotent(self):
        """Running the patch twice must converge — second run emits zero deltas."""
        from hrms_za.patches.v0_0_2 import (
            backfill_sa_leave_policy_assignments as patch,
        )
        # Already run as part of install; run again — should be no-op
        patch.execute()
        annual_count = frappe.db.count(
            "Leave Policy", {"title": "SA Annual Leave Policy"}
        )
        self.assertEqual(annual_count, 1)

    def test_new_hire_gets_both_policies(self):
        """Create an SA Employee; assert annual + sick LPAs both submitted."""
        emp = self._create_sa_employee(date_of_joining="2026-04-20")
        annual_lpas = frappe.get_all(
            "Leave Policy Assignment",
            filters={
                "employee": emp, "docstatus": 1,
                "assignment_based_on": "Leave Period",
            },
            pluck="name",
        )
        sick_lpas = frappe.get_all(
            "Leave Policy Assignment",
            filters={
                "employee": emp, "docstatus": 1,
                "assignment_based_on": "Joining Date",
            },
            pluck="name",
        )
        self.assertGreaterEqual(len(annual_lpas), 1)
        self.assertGreaterEqual(len(sick_lpas), 1)

    def test_sick_lpa_effective_window_is_36_months(self):
        emp = self._create_sa_employee(date_of_joining="2026-04-20")
        lpa = frappe.get_value(
            "Leave Policy Assignment",
            {
                "employee": emp, "docstatus": 1,
                "assignment_based_on": "Joining Date",
            },
            ["effective_from", "effective_to"],
            as_dict=True,
        )
        self.assertEqual(str(lpa.effective_from), "2026-04-20")
        self.assertEqual(str(lpa.effective_to), "2029-04-19")

    def test_scheduler_is_idempotent(self):
        from hrms_za.regional.south_africa.leave import emit_sick_cycle_lpas
        r1 = emit_sick_cycle_lpas()
        r2 = emit_sick_cycle_lpas()
        self.assertEqual(r2["created"], 0)

    def test_scheduler_emits_next_cycle_on_boundary(self):
        """Employee with DOJ ~ 36 months ago triggers the lookahead."""
        from dateutil.relativedelta import relativedelta
        from hrms_za.regional.south_africa.leave import emit_sick_cycle_lpas

        today = frappe.utils.getdate(frappe.utils.today())
        doj = today - relativedelta(months=36, days=-3)  # cycle ends in 3 days
        emp = self._create_sa_employee(date_of_joining=str(doj))

        before = frappe.db.count(
            "Leave Policy Assignment",
            {"employee": emp, "assignment_based_on": "Joining Date", "docstatus": 1},
        )
        emit_sick_cycle_lpas()
        after = frappe.db.count(
            "Leave Policy Assignment",
            {"employee": emp, "assignment_based_on": "Joining Date", "docstatus": 1},
        )
        self.assertGreaterEqual(after, before + 1)

    def test_sick_application_blocked_when_cap_enforced(self):
        """HRMS native validator rejects drawdown beyond the cycle bucket."""
        emp = self._create_sa_employee(date_of_joining="2026-04-20")
        self.assertRaises(
            frappe.exceptions.ValidationError,
            self._submit_leave_application,
            emp, "Sick Leave (SA)", "2026-05-01", "2026-06-30",
        )  # 60+ days — well over the 30-day cycle bucket

    def test_settings_knob_flips_allow_negative(self):
        """enforce_sick_cycle_cap=0 → Leave Type.allow_negative=1"""
        settings = frappe.get_single("SA Leave Settings")
        settings.enforce_sick_cycle_cap = 0
        settings.save(ignore_permissions=True)

        allow_negative = frappe.db.get_value(
            "Leave Type", "Sick Leave (SA)", "allow_negative"
        )
        self.assertEqual(int(allow_negative), 1)

        # flip back for test hygiene
        settings.enforce_sick_cycle_cap = 1
        settings.save(ignore_permissions=True)

    def test_termination_auto_creates_encashment_draft(self):
        """Auto knob on + annual balance > 0 → draft Leave Encashment exists."""
        # This test assumes helper `_create_sa_employee_with_balance` exists
        # in the test class; if not, see Step 3 below.
        emp = self._create_sa_employee(date_of_joining="2025-01-01")
        self._grant_annual_balance(emp, days=5)
        sep = self._submit_employee_separation(emp, relieving_date="2026-06-30")

        exists = frappe.db.exists(
            "Leave Encashment",
            {"employee": emp, "leave_type": "Annual Leave (SA)", "docstatus": 0},
        )
        self.assertIsNotNone(exists)

    def test_termination_skipped_when_knob_off(self):
        settings = frappe.get_single("SA Leave Settings")
        settings.auto_create_termination_encashment = 0
        settings.save(ignore_permissions=True)

        emp = self._create_sa_employee(date_of_joining="2025-01-01")
        self._grant_annual_balance(emp, days=5)
        self._submit_employee_separation(emp, relieving_date="2026-06-30")

        exists = frappe.db.exists(
            "Leave Encashment",
            {"employee": emp, "leave_type": "Annual Leave (SA)", "docstatus": 0},
        )
        self.assertIsNone(exists)

        # flip back
        settings.auto_create_termination_encashment = 1
        settings.save(ignore_permissions=True)

    def test_termination_skipped_when_zero_balance(self):
        emp = self._create_sa_employee(date_of_joining="2025-01-01")
        # no balance granted
        self._submit_employee_separation(emp, relieving_date="2026-06-30")

        exists = frappe.db.exists(
            "Leave Encashment",
            {"employee": emp, "leave_type": "Annual Leave (SA)"},
        )
        self.assertIsNone(exists)
```

- [ ] **Step 3: Add helper methods on the test class (if they don't already exist)**

Add to the same test class:

```python
    def _create_sa_employee(self, date_of_joining):
        """Create a test Employee on an SA company. Returns employee name."""
        # Uses the class-level test company / department already seeded in Phase 1
        emp = frappe.get_doc({
            "doctype": "Employee",
            "first_name": f"Test{frappe.generate_hash(length=6)}",
            "date_of_joining": date_of_joining,
            "company": self.test_company,   # from Phase-1 setUpClass
            "status": "Active",
            "gender": "Male",
            "date_of_birth": "1990-01-01",
        })
        emp.insert(ignore_permissions=True)
        return emp.name

    def _grant_annual_balance(self, employee, days):
        """Directly set an annual Leave Allocation balance for testing."""
        lpa = frappe.get_value(
            "Leave Policy Assignment",
            {"employee": employee, "assignment_based_on": "Leave Period",
             "docstatus": 1},
            "name",
        )
        # Find the matching Leave Allocation for Annual Leave (SA)
        alloc = frappe.get_value(
            "Leave Allocation",
            {"employee": employee, "leave_type": "Annual Leave (SA)",
             "docstatus": 1},
            "name",
        )
        if alloc:
            frappe.db.set_value("Leave Allocation", alloc, "new_leaves_allocated", days)

    def _submit_leave_application(self, employee, leave_type, from_date, to_date):
        doc = frappe.get_doc({
            "doctype": "Leave Application",
            "employee": employee,
            "leave_type": leave_type,
            "from_date": from_date,
            "to_date": to_date,
            "half_day": 0,
            "status": "Approved",
            "leave_approver": "Administrator",
        })
        doc.insert(ignore_permissions=True)
        doc.submit()
        return doc.name

    def _submit_employee_separation(self, employee, relieving_date):
        doc = frappe.get_doc({
            "doctype": "Employee Separation",
            "employee": employee,
            "boarding_begins_on": relieving_date,
            "company": self.test_company,
        })
        doc.insert(ignore_permissions=True)
        # Employee Separation may have additional validate requirements;
        # adapt based on v16 field set.
        doc.submit()
        return doc.name
```

- [ ] **Step 4: Run the test suite on the test site**

```bash
docker exec -u frappe frappe-backend-1 bench --site test_hrms_za \
    run-tests --module hrms_za.payroll_sa.tests.test_leave_setup
```

Expected: all Phase-1 + Phase-2 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/payroll_sa/tests/test_leave_setup.py
git commit -m "test(leave): 11 phase-2 FrappeTestCase coverage"
```

---

## Task 18: Bump version + README feature list update

**Files modified:**
- `hrms_za/__init__.py`
- `README.md`

- [ ] **Step 1: Bump the version**

Read `hrms_za/__init__.py` — expect `__version__ = "0.0.1"`. Change to `"0.0.2"`.

```bash
cat hrms_za/__init__.py
```

Then:
```python
__version__ = "0.0.2"
```

- [ ] **Step 2: Update README feature list**

Add the following bullets under the existing feature list (remove any that are now redundant or stale). Do NOT reference tenant-specific domains.

```markdown
- Monthly earned-leave accrual on Annual Leave (SA) — HRMS native, wired via seeder.
- BCEA s22 fixed 36-month sick-leave cycle, per-employee, DOJ-anchored. Daily scheduler emits the next cycle LPA on boundary.
- Auto-draft Leave Encashment on Employee Separation submit (BCEA s40), annual leave only. Manual button fallback on SA Leave Settings.
```

- [ ] **Step 3: Commit**

```bash
cd /home/frappeadmin/hrms_za
git add hrms_za/__init__.py README.md
git commit -m "chore: bump hrms_za to v0.0.2 + document phase-2 features"
```

---

## Task 19: End-to-end verification on the test site

**Files:** no changes — verification only.

- [ ] **Step 1: Rebuild + redeploy to the test site**

```bash
cd ~/frappe_docker
# Rebuild layered image with BuildKit cache buster for apps.json
docker build \
    --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \
    --build-arg=FRAPPE_BRANCH=version-16 \
    --build-arg=PYTHON_VERSION=3.14 \
    --build-arg=NODE_VERSION=24 \
    --secret=id=apps_json,src=apps.json \
    --no-cache-filter=builder \
    --tag=custom-erpnext:16 \
    --file=images/layered/Containerfile .

# Restart only the backend to pull the new code
docker compose -f compose.yaml restart backend queue-long queue-short scheduler
```

- [ ] **Step 2: Migrate the test site**

```bash
docker exec -u frappe frappe-backend-1 bench --site test_hrms_za migrate
docker exec -u frappe frappe-backend-1 bench --site test_hrms_za clear-cache
```

Expected: migrate exits 0; log shows `[hrms_za v0.0.2] migration complete:` with step counts.

- [ ] **Step 3: Confirm DB shape**

Visit:
- `/app/leave-policy` — two policies, both submitted.
- `/app/leave-type/Annual Leave (SA)` — `is_earned_leave = 1`, `earned_leave_frequency = Monthly`, `allocate_on_day = First Day`, `maximum_carry_forwarded_leaves = 5`.
- `/app/sa-leave-settings` — six new fields visible with defaults.

- [ ] **Step 4: New-hire flow**

Create an Employee with `date_of_joining = today`. Confirm:
- Two LPAs (annual + sick cycle) exist and are submitted.
- Annual Leave Allocation has `new_leaves_allocated = 0` (earned — waiting for scheduler).
- Sick Leave Allocation shows 30 days usable.

- [ ] **Step 5: Sick cycle scheduler**

```bash
docker exec -u frappe frappe-backend-1 bench --site test_hrms_za \
    execute hrms_za.regional.south_africa.leave.emit_sick_cycle_lpas
```

Expected: JSON response with `created / skipped / failed`; no exceptions.

- [ ] **Step 6: Knob flip — enforce_sick_cycle_cap**

On SA Leave Settings form, uncheck "Enforce Sick Cycle Cap" + save. Inspect `/app/leave-type/Sick Leave (SA)` — `allow_negative` must be `1`. Re-check and save — `allow_negative` must return to `0`.

- [ ] **Step 7: Termination flow**

Create an Employee Separation for any SA Employee with nonzero annual balance, submit. Confirm:
- A draft `Leave Encashment` exists on that Employee's form.
- Encashment amount = balance × per-day rate (pulled from Salary Structure).
- Flipping `auto_create_termination_encashment = 0` and repeating: no auto-creation. Clicking the "Generate Termination Encashment" button produces the same draft.

- [ ] **Step 8: Idempotency**

```bash
docker exec -u frappe frappe-backend-1 bench --site test_hrms_za migrate
```

Expected: migration step counts all zero (the patch converged on the previous run).

Re-run the scheduler — `created` should be 0 on the second run.

- [ ] **Step 9: Commit any verification notes**

If the verification surfaces findings (additional edge cases, doc gaps), update the spec's "Implementation notes" section and commit. If no changes required:

```bash
echo "Phase 2 verification PASSED on test_hrms_za" > /tmp/v0.0.2-verification.log
```

---

## Self-review findings

Checked the spec section-by-section against the tasks:

- **Spec §2 (architecture two-policy split)** — tasks 5, 8 (data + seeder).
- **Spec §2 (scheduler)** — task 11.
- **Spec §2 (cross-boundary contract)** — implicit via native `get_leave_balance_on` usage in task 12.
- **Spec §3 (Leave Type changes)** — task 4.
- **Spec §3 (Leave Policy records)** — tasks 5, 8.
- **Spec §3 (SA Leave Settings new fields)** — task 6.
- **Spec §3 (existing knobs wired)** — task 7.
- **Spec §4 (runtime code)** — tasks 10, 11, 12, 13.
- **Spec §4 (install/migration)** — tasks 8, 9, 16.
- **Spec §4 (UI)** — task 15.
- **Spec §4 (hooks.py)** — task 14.
- **Spec §5 (data flow 5.1, new hire)** — task 10 impl + task 17 test.
- **Spec §5 (5.2, cycle boundary rollover)** — task 11 impl + task 17 tests.
- **Spec §5 (5.3, validator)** — task 7 (knob propagation) + task 17 test.
- **Spec §5 (5.4, termination)** — task 12 impl + task 15 button + task 17 tests.
- **Spec §5 (5.5, backfill)** — task 16.
- **Spec §6 (never-throw boundaries)** — covered in tasks 10, 11, 12 via `try/except → log_error` wrappers.
- **Spec §6 (scheduler gap-prevention)** — task 11 (lookahead + no-active detection).
- **Spec §6 (edge cases)** — task 17 (tested) + task 11 (Feb 29 via `cycle_math.sa_sick_cycle_window`).
- **Spec §7 (pure-pytest tests)** — tasks 1, 2.
- **Spec §7 (FrappeTestCase tests)** — task 17.
- **Spec §7 (live verification)** — task 19.
- **Spec §10 (terminology cleanup)** — task 3.
- **Spec §11 (DoD, version bump)** — task 18.

No gaps found. Placeholder scan: zero TBD/TODO/FIXME in tasks. Type consistency: `_try_assign_default_policy`, `_apply_policy_for_employee`, `_create_leave_policy_assignment` signatures and return types consistent across tasks 10–13 + task 16. Settings field names (`default_sick_cycle_policy`, `sick_cycle_lookahead_days`, `backfill_missing_cycles`, `enforce_sick_cycle_cap`, `annual_leave_applicable_after_days`, `auto_create_termination_encashment`) identical in JSON (task 6), Python handler (task 7), seeder (task 9), scheduler (task 11), and trigger (task 12).

Fix the spec test §17 — helper method `_submit_employee_separation` calls `doc.submit()` but Employee Separation may require `boarding_begins_on` and staff-side prerequisites. If the test fails on Separation-validation rules, adapt the helper to match v16 field set (out-of-scope for this plan — document as a known-fragile helper in that task's implementation step).

---

## Definition of Done

- All 19 tasks ticked.
- `bench migrate` on the test site exits 0 twice (second run → zero deltas).
- Pure pytest passes (`python -m pytest hrms_za/payroll_sa/tests/ -v`).
- FrappeTestCase passes (`bench --site test_hrms_za run-tests --module …`).
- Spec's §7 live-verification checklist green on test site.
- `grep -rn "rolling" --include='*.md' --include='*.py' --include='*.js' --include='*.json' .` returns only matches inside `docs/superpowers/specs/` (correcting references), nothing else.
- `hrms_za/__init__.py` is `__version__ = "0.0.2"`.

Ship it.
