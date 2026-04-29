"""
South African Leave Type seed values aligned to BCEA minima.

Key references:
- BCEA s20: Annual Leave — 15 working days or 21 consecutive days per cycle.
- BCEA s22: Sick Leave — 30 days per 36-month cycle (placeholder here;
  the fixed 36-month cycle is NOT yet modelled — see project TODO).
- BCEA s25: Maternity Leave — 4 consecutive months (120 days), unpaid under BCEA
  (UIF covers portion).
- BCEA s25A: Parental Leave — 10 consecutive days.
- BCEA s27: Family Responsibility Leave — 3 days per year.
"""


# Canonical SA Leave Type names. Import these instead of hardcoding the
# string literals — the leave_type_name fields below MUST match.
ANNUAL_LEAVE_TYPE = "Annual Leave (SA)"
SICK_LEAVE_TYPE = "Sick Leave (SA)"

# Default fallback role used when an Employee/Department has no approver.
# Centralised so the literal doesn't drift across leave.py + JSON defaults.
HR_MANAGER_ROLE = "HR Manager"


LEAVE_TYPES = [
    {
        "leave_type_name": ANNUAL_LEAVE_TYPE,
        "max_leaves_allowed": 15,
        "is_earned_leave": 1,
        "earned_leave_frequency": "Monthly",
        "rounding": "0.5",
        "is_carry_forward": 1,
        "allow_encashment": 1,
        "allow_negative": 0,
    },
    # Sick Leave: BCEA s22 mandates 30 days per 36-month cycle. The fixed
    # 36-month cycle (consecutive blocks anchored on hire date) is not
    # modelled yet — treat as 30 days/year until a dedicated SA Sick Leave
    # Cycle doctype ships.
    {
        "leave_type_name": SICK_LEAVE_TYPE,
        "max_leaves_allowed": 30,
        "is_earned_leave": 0,
        "is_carry_forward": 0,
        "allow_negative": 0,
    },
    {
        "leave_type_name": "Family Responsibility Leave (SA)",
        "max_leaves_allowed": 3,
        "is_carry_forward": 0,
        "allow_negative": 0,
    },
    {
        "leave_type_name": "Maternity Leave (SA)",
        "max_leaves_allowed": 120,
        "is_lwp": 1,
        "is_carry_forward": 0,
        "allow_negative": 0,
    },
    {
        "leave_type_name": "Parental Leave (SA)",
        "max_leaves_allowed": 10,
        "is_lwp": 1,
        "is_carry_forward": 0,
        "allow_negative": 0,
    },
    {
        "leave_type_name": "Adoption Leave (SA)",
        "max_leaves_allowed": 70,
        "is_lwp": 1,
        "is_carry_forward": 0,
        "allow_negative": 0,
    },
    {
        "leave_type_name": "Commissioning Parental Leave (SA)",
        "max_leaves_allowed": 70,
        "is_lwp": 1,
        "is_carry_forward": 0,
        "allow_negative": 0,
    },
    {
        "leave_type_name": "Study Leave (SA)",
        "max_leaves_allowed": 5,
        "is_carry_forward": 0,
        "allow_negative": 0,
    },
]
