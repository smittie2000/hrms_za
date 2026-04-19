"""
Whitelisted helper to create / refresh a Holiday List for a South African
calendar year.

Usage (bench console):
    from hrms_za.regional.south_africa.holidays import generate_sa_holiday_list
    generate_sa_holiday_list(2026, company="Hosted Communications")

Usage (REST / UI action button):
    POST /api/method/hrms_za.regional.south_africa.holidays.generate_sa_holiday_list
         year=2026&company=Hosted%20Communications

The resulting Holiday List contains:
- All 12 SA statutory public holidays (fixed + Easter-dependent)
- Sunday → Monday substitutions applied per the Public Holidays Act
- All Saturdays and Sundays of the year as weekly offs
"""

import frappe

from hrms_za.regional.south_africa.data.holidays import build_holidays_for_year


@frappe.whitelist()
def generate_sa_holiday_list(
    year,
    company: str = None,
    set_as_default: bool = True,
):
    """
    Create (or refresh) a Holiday List named "South Africa {year}" and
    optionally set it as the given Company's `default_holiday_list`.
    Safe to re-run; existing list contents are wiped and repopulated.
    """
    year = int(year)
    name = f"South Africa {year}"

    doc = (
        frappe.get_doc("Holiday List", name)
        if frappe.db.exists("Holiday List", name)
        else frappe.new_doc("Holiday List")
    )
    if not doc.is_new():
        doc.holidays = []

    doc.holiday_list_name = name
    doc.from_date = f"{year}-01-01"
    doc.to_date = f"{year}-12-31"
    doc.country = "South Africa"

    for dt, desc in build_holidays_for_year(year):
        doc.append("holidays", {
            "holiday_date": dt,
            "description": desc,
            "weekly_off": 0,
        })

    # v16 Holiday List accepts a single weekday in `weekly_off`. Call
    # get_weekly_off_dates() twice to cover both Saturday and Sunday.
    doc.weekly_off = "Sunday"
    doc.get_weekly_off_dates()
    doc.weekly_off = "Saturday"
    doc.get_weekly_off_dates()
    doc.weekly_off = "Sunday"  # keep the single required declared value

    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)
    frappe.db.commit()

    result = {
        "holiday_list":   name,
        "public_rows":    sum(1 for h in doc.holidays if not h.weekly_off),
        "weekend_rows":   sum(1 for h in doc.holidays if h.weekly_off),
        "total_rows":     len(doc.holidays),
        "default_on_company": None,
    }

    if company and set_as_default and frappe.db.exists("Company", company):
        frappe.db.set_value("Company", company, "default_holiday_list", name)
        frappe.db.commit()
        result["default_on_company"] = company

    return result
