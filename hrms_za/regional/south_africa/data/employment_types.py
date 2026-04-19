"""
South African Employment Type seed values.

Aligned with SARS source-code distinctions and BCEA/UIF exemptions:
- Directors and domestic workers of less than 24 hours/month are UIF-exempt.
- Independent Contractors fall outside PAYE (usually) and outside BCEA entirely.
- Learners are relevant for ETI (Employment Tax Incentive) claims.
"""


EMPLOYMENT_TYPES = [
    "Permanent",
    "Fixed Term Contract",
    "Temporary Employee",
    "Casual",
    "Director",
    "Independent Contractor",
    "Learner",
]
