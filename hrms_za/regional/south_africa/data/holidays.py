"""
South African public holidays per Public Holidays Act 36 of 1994.

12 recognised holidays: 10 fixed-date + 2 Easter-dependent
(Good Friday, Family Day). The Act also carries a Sunday → Monday
substitution rule: "Whenever any public holiday falls on a Sunday,
the Monday following shall be a public holiday." This is applied
automatically by build_holidays_for_year().

Canonical source, verified 2026-04-19:
  https://www.gov.za/about-sa/public-holidays

Ad-hoc holidays (election days, presidentially declared days of mourning,
etc.) are NOT generated here — they are announced individually and must
be added to the Holiday List manually each time. See §9.2 of the
evaluation doc.
"""

from datetime import date, timedelta


# (month, day), description — fixed-date statutory holidays
FIXED_HOLIDAYS = [
    ((1, 1),   "New Year's Day"),
    ((3, 21),  "Human Rights Day"),
    ((4, 27),  "Freedom Day"),
    ((5, 1),   "Workers' Day"),
    ((6, 16),  "Youth Day"),
    ((8, 9),   "National Women's Day"),
    ((9, 24),  "Heritage Day"),
    ((12, 16), "Day of Reconciliation"),
    ((12, 25), "Christmas Day"),
    ((12, 26), "Day of Goodwill"),
]


def easter_sunday(year: int) -> date:
    """
    Return the Gregorian date of Easter Sunday for `year`.

    Implements the Anonymous Gregorian algorithm
    (Meeus/Jones/Butcher). Accurate for any year in the Gregorian calendar.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def build_holidays_for_year(year: int) -> list[tuple[date, str]]:
    """
    Return all 12 SA statutory public holidays for `year` with Sunday → Monday
    substitutions applied per the Public Holidays Act. Result is sorted by date.
    """
    result: list[tuple[date, str]] = []

    for (m, d), name in FIXED_HOLIDAYS:
        dt = date(year, m, d)
        result.append((dt, name))
        if dt.weekday() == 6:  # 6 == Sunday
            observed = dt + timedelta(days=1)
            result.append((observed, f"{name} (observed — {dt} fell on Sunday)"))

    easter = easter_sunday(year)
    result.append((easter - timedelta(days=2), "Good Friday"))
    result.append((easter + timedelta(days=1), "Family Day"))

    result.sort(key=lambda x: x[0])
    return result
