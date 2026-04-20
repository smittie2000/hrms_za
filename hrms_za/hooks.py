app_name = "hrms_za"
app_title = "HRMS South Africa"
app_publisher = "HRMS-ZA Contributors"
app_description = "South African localisation for Frappe HRMS v16"
app_email = "hrms-za@example.com"
app_license = "mit"

required_apps = ["frappe/erpnext", "frappe/hrms"]

after_install = "hrms_za.regional.south_africa.setup.after_install"

doc_events = {
    "Company": {
        "on_update": "hrms_za.regional.south_africa.setup.on_company_update",
    },
    "Salary Slip": {
        "validate": "hrms_za.payroll_sa.paye_calculator.adjust_sa_paye",
    },
}
