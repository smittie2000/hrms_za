"""
SA Payroll Matrix — per-employee monthly payroll matrix for HR management.

Column shape matches the HR Manager brief exactly:
  Employee | Name | Dept | Employment Type | Basic | Overtime | Bonus |
  Travel Allowance | Cellphone Allowance | Gross Earnings |
  PAYE | UIF Employee | UIF Employer | SDL | Other Deductions | Total Deductions |
  Net Pay | SARS Tax Number | UIF Reference | [Flag] Missing Tax Number

Source data: submitted Salary Slip rows for the chosen month/year, optionally
filtered by company / department / employment type. Amount-per-component is
looked up via the Salary Detail child rows on each slip.

Compliance flag logic:
- "Missing Tax Number" — Employee has no sa_tax_reference value.
- "Missing UIF Ref"    — Employee marked as UIF contributor but no uif_reference.
Both render as red tags via the `indicator` column convention.

This is a demo-ready report: when no salary slips exist yet, returns [] and the
UI shows an empty grid. Columns/filters are the deliverable today — real-value
correctness arrives with the SA PAYE calculator.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Extract
from frappe.utils import flt


# Component → matrix column mapping. If a tenant renames a component, they
# should update this dict rather than forking the report. The keys match the
# component names shipped by hrms_za.regional.south_africa.data.salary_components.
EARNING_COMPONENT_MAP = {
    "Basic": "basic",
    "Overtime": "overtime",
    "Bonus": "bonus",
    "Travel Allowance": "travel_allowance",
    "Cellphone Allowance": "cellphone_allowance",
}

DEDUCTION_COMPONENT_MAP = {
    "PAYE": "paye",
    "UIF - Employee": "uif_employee",
    "UIF - Employer": "uif_employer",
    "SDL": "sdl",
}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Employee ID"),     "fieldname": "employee",       "fieldtype": "Link",  "options": "Employee", "width": 130},
        {"label": _("Full Name"),        "fieldname": "employee_name",  "fieldtype": "Data",  "width": 180},
        {"label": _("Department"),       "fieldname": "department",     "fieldtype": "Link",  "options": "Department", "width": 140},
        {"label": _("Employment Type"),  "fieldname": "employment_type","fieldtype": "Link",  "options": "Employment Type", "width": 140},
        {"label": _("Basic"),            "fieldname": "basic",          "fieldtype": "Currency", "width": 110},
        {"label": _("Overtime"),         "fieldname": "overtime",       "fieldtype": "Currency", "width": 100},
        {"label": _("Bonus"),            "fieldname": "bonus",          "fieldtype": "Currency", "width": 100},
        {"label": _("Travel Allow."),    "fieldname": "travel_allowance","fieldtype": "Currency", "width": 110},
        {"label": _("Cell Allow."),      "fieldname": "cellphone_allowance","fieldtype": "Currency", "width": 110},
        {"label": _("Gross Earnings"),   "fieldname": "gross_pay",      "fieldtype": "Currency", "width": 130},
        {"label": _("PAYE"),             "fieldname": "paye",           "fieldtype": "Currency", "width": 110},
        {"label": _("UIF (EE)"),         "fieldname": "uif_employee",   "fieldtype": "Currency", "width": 100},
        {"label": _("UIF (ER)"),         "fieldname": "uif_employer",   "fieldtype": "Currency", "width": 100},
        {"label": _("SDL"),              "fieldname": "sdl",            "fieldtype": "Currency", "width": 100},
        {"label": _("Other Deductions"), "fieldname": "other_deductions","fieldtype": "Currency", "width": 120},
        {"label": _("Total Deductions"), "fieldname": "total_deduction","fieldtype": "Currency", "width": 130},
        {"label": _("Net Pay"),          "fieldname": "net_pay",        "fieldtype": "Currency", "width": 130},
        {"label": _("SARS Tax No."),     "fieldname": "sa_tax_reference","fieldtype": "Data",    "width": 120},
        {"label": _("UIF Ref"),          "fieldname": "uif_reference",  "fieldtype": "Data",    "width": 120},
        {"label": _("Compliance"),       "fieldname": "compliance_flag","fieldtype": "Data",    "width": 200},
        {"label": _("Salary Slip"),      "fieldname": "salary_slip",    "fieldtype": "Link",    "options": "Salary Slip", "width": 140},
    ]


def get_data(filters):
    slips = get_salary_slips(filters)
    if not slips:
        return []

    slip_names = [s.name for s in slips]
    earnings_by_slip   = get_components_by_slip(slip_names, "earnings")
    deductions_by_slip = get_components_by_slip(slip_names, "deductions")

    employee_meta = get_employee_meta([s.employee for s in slips])

    rows = []
    for s in slips:
        earn_map = earnings_by_slip.get(s.name, {})
        ded_map  = deductions_by_slip.get(s.name, {})
        meta     = employee_meta.get(s.employee, {})

        row = {
            "employee":         s.employee,
            "employee_name":    s.employee_name,
            "department":       s.department,
            "employment_type":  meta.get("employment_type"),
            "gross_pay":        flt(s.gross_pay),
            "total_deduction":  flt(s.total_deduction),
            "net_pay":          flt(s.net_pay),
            "salary_slip":      s.name,
            "sa_tax_reference": meta.get("sa_tax_reference"),
            "uif_reference":    meta.get("uif_reference"),
        }

        for component_name, column in EARNING_COMPONENT_MAP.items():
            row[column] = flt(earn_map.get(component_name, 0))

        tracked_deduction_total = 0
        for component_name, column in DEDUCTION_COMPONENT_MAP.items():
            amount = flt(ded_map.get(component_name, 0))
            row[column] = amount
            # UIF Employer and SDL are statistical (not in total_deduction),
            # so exclude them from the "other" residual calculation.
            if component_name not in ("UIF - Employer", "SDL"):
                tracked_deduction_total += amount

        row["other_deductions"] = max(flt(s.total_deduction) - tracked_deduction_total, 0)
        row["compliance_flag"] = build_compliance_flag(meta)

        rows.append(row)

    return rows


def get_salary_slips(filters):
    SalarySlip = frappe.qb.DocType("Salary Slip")
    query = (
        frappe.qb.from_(SalarySlip)
        .select(
            SalarySlip.name,
            SalarySlip.employee,
            SalarySlip.employee_name,
            SalarySlip.department,
            SalarySlip.designation,
            SalarySlip.company,
            SalarySlip.start_date,
            SalarySlip.gross_pay,
            SalarySlip.total_deduction,
            SalarySlip.net_pay,
        )
        .where(SalarySlip.docstatus == 1)
    )

    if filters.get("company"):
        query = query.where(SalarySlip.company == filters.company)
    if filters.get("department"):
        query = query.where(SalarySlip.department == filters.department)
    if filters.get("month"):
        query = query.where(Extract("month", SalarySlip.start_date) == filters.month)
    if filters.get("year"):
        query = query.where(Extract("year", SalarySlip.start_date) == filters.year)

    return query.run(as_dict=True)


def get_components_by_slip(slip_names, parentfield):
    if not slip_names:
        return {}

    rows = frappe.get_all(
        "Salary Detail",
        filters={
            "parent": ["in", slip_names],
            "parenttype": "Salary Slip",
            "parentfield": parentfield,
        },
        fields=["parent", "salary_component", "amount"],
    )
    result = {}
    for r in rows:
        result.setdefault(r.parent, {})[r.salary_component] = r.amount
    return result


def get_employee_meta(employee_names):
    if not employee_names:
        return {}
    # Fields read from the custom fields shipped by
    # hrms_za.regional.south_africa.data.custom_fields.
    rows = frappe.get_all(
        "Employee",
        filters={"name": ["in", employee_names]},
        fields=[
            "name",
            "employment_type",
            "sa_tax_reference",
            "uif_contributor",
            "uif_reference",
        ],
    )
    return {r.name: r for r in rows}


def build_compliance_flag(meta):
    flags = []
    if not meta.get("sa_tax_reference"):
        flags.append(_("Missing Tax Number"))
    if meta.get("uif_contributor") and not meta.get("uif_reference"):
        flags.append(_("Missing UIF Ref"))
    if not flags:
        return f'<span class="indicator green">{_("OK")}</span>'
    return " • ".join(f'<span class="indicator red">{f}</span>' for f in flags)
