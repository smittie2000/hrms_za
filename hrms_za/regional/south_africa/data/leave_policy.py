"""
South African standard Leave Policy definition.

One submitted Leave Policy record bundles every BCEA-aligned leave type
with its annual allocation quantity. `install_leave_policy()` (in setup.py)
seeds this ONCE — if any doc named `SA Standard Leave Policy` already
exists in any state (draft / submitted / amended to `-1` / disabled), the
seeder returns without touching it. That lets HR amend the policy freely
without the seeder fighting the changes on every reinstall.

Quantities below are BCEA minima. A tenant that offers more (e.g. 20 annual
days, 7 family responsibility) should fork the shipped policy by amending
it — not edit this file.

References:
- BCEA s20: Annual Leave — 15 working days per 12-month cycle.
- BCEA s22: Sick Leave — 30 days per 36-month rolling cycle (modelled as
  flat 30 here; rolling window is a Phase 2 build).
- BCEA s25:  Maternity Leave — 4 consecutive months.
- BCEA s25A: Parental Leave — 10 consecutive days.
- BCEA s27:  Family Responsibility Leave — 3 days per year.
"""


LEAVE_POLICY_NAME = "SA Standard Leave Policy"


# Each entry maps a shipped Leave Type (from data/leave_types.py) to its
# annual allocation in days. `leave_policy_details` is the child-table
# fieldname on Leave Policy; `leave_type` + `annual_allocation` are the
# child row columns (verified against hrms/hr/doctype/leave_policy_detail).
LEAVE_POLICY_DETAILS = [
    {"leave_type": "Annual Leave (SA)",                 "annual_allocation": 15},
    {"leave_type": "Sick Leave (SA)",                   "annual_allocation": 30},
    {"leave_type": "Family Responsibility Leave (SA)",  "annual_allocation": 3},
    {"leave_type": "Maternity Leave (SA)",              "annual_allocation": 120},
    {"leave_type": "Parental Leave (SA)",               "annual_allocation": 10},
    {"leave_type": "Adoption Leave (SA)",               "annual_allocation": 70},
    {"leave_type": "Commissioning Parental Leave (SA)", "annual_allocation": 70},
    {"leave_type": "Study Leave (SA)",                  "annual_allocation": 5},
]
