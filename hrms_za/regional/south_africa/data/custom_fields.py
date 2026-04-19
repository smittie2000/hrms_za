"""
Custom Field definitions for SA localisation.

Added to Employee and Company on app install and whenever Company.country
is set to "South Africa". Installed via frappe.custom.doctype.custom_field.
custom_field.create_custom_fields() which is idempotent (upsert on update=True).

Insert points are chosen against stable core fields in ERPNext v16's employee.json
and company.json — see INTEGRATION_MAP.md for the full field inventory.
"""


def get_custom_fields():
    return {
        "Employee": [
            {
                "fieldname": "sa_tax_section",
                "label": "South African Tax & Compliance",
                "fieldtype": "Section Break",
                "insert_after": "bio",
                "collapsible": 1,
            },
            {
                "fieldname": "sa_id_number",
                "label": "SA ID Number",
                "fieldtype": "Data",
                "insert_after": "sa_tax_section",
                "description": "13-digit South African ID number",
                "length": 13,
            },
            {
                "fieldname": "sa_tax_reference",
                "label": "SARS Income Tax Number",
                "fieldtype": "Data",
                "insert_after": "sa_id_number",
                "description": "10-digit SARS income tax reference",
                "length": 10,
            },
            {
                "fieldname": "sa_tax_cb",
                "fieldtype": "Column Break",
                "insert_after": "sa_tax_reference",
            },
            {
                "fieldname": "uif_contributor",
                "label": "UIF Contributor",
                "fieldtype": "Check",
                "default": "1",
                "insert_after": "sa_tax_cb",
                "description": (
                    "Uncheck for directors, foreign nationals on work permits, "
                    "and employees working < 24 hours per month (UIF Act s4)."
                ),
            },
            {
                "fieldname": "uif_reference",
                "label": "UIF Reference Number",
                "fieldtype": "Data",
                "insert_after": "uif_contributor",
                "depends_on": "eval:doc.uif_contributor",
            },
            {
                "fieldname": "medical_aid_section",
                "label": "Medical Aid (for s6A PAYE credit)",
                "fieldtype": "Section Break",
                "insert_after": "uif_reference",
                "collapsible": 1,
            },
            {
                "fieldname": "medical_aid_scheme",
                "label": "Medical Aid Scheme",
                "fieldtype": "Data",
                "insert_after": "medical_aid_section",
            },
            {
                "fieldname": "medical_aid_members",
                "label": "Total Members (incl. main)",
                "fieldtype": "Int",
                "insert_after": "medical_aid_scheme",
                "default": "0",
                "description": (
                    "Total covered lives including the employee. Drives the "
                    "SA PAYE calculator's medical scheme fees tax credit (s6A)."
                ),
            },
            {
                "fieldname": "medical_aid_cb",
                "fieldtype": "Column Break",
                "insert_after": "medical_aid_members",
            },
            {
                "fieldname": "medical_aid_monthly_contribution",
                "label": "Monthly Contribution",
                "fieldtype": "Currency",
                "insert_after": "medical_aid_cb",
                "description": (
                    "Monthly premium paid to scheme. Stored for future s6B "
                    "(excess medical expenses) credit calc; not yet used by "
                    "the PAYE calculator."
                ),
            },
        ],
        "Company": [
            {
                "fieldname": "sa_statutory_section",
                "label": "South African Statutory References",
                "fieldtype": "Section Break",
                "insert_after": "date_of_establishment",
                "collapsible": 1,
                "depends_on": 'eval:doc.country == "South Africa"',
            },
            {
                "fieldname": "sa_paye_reference",
                "label": "PAYE Reference Number",
                "fieldtype": "Data",
                "insert_after": "sa_statutory_section",
                "description": "Employer PAYE reference (10 digits, starts with 7)",
            },
            {
                "fieldname": "sa_uif_reference",
                "label": "UIF Reference Number",
                "fieldtype": "Data",
                "insert_after": "sa_paye_reference",
                "description": "Employer UIF reference (starts with U)",
            },
            {
                "fieldname": "sa_statutory_cb",
                "fieldtype": "Column Break",
                "insert_after": "sa_uif_reference",
            },
            {
                "fieldname": "sa_sdl_reference",
                "label": "SDL Reference Number",
                "fieldtype": "Data",
                "insert_after": "sa_statutory_cb",
                "description": "Skills Development Levy reference (starts with L)",
            },
            {
                "fieldname": "sa_sars_trading_name",
                "label": "SARS Registered Trading Name",
                "fieldtype": "Data",
                "insert_after": "sa_sdl_reference",
            },
        ],
    }
