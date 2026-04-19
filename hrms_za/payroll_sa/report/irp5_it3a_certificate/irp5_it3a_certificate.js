/* eslint-disable */
frappe.query_reports["IRP5/IT3(a) Certificate"] = {
    filters: [
        {fieldname: "company",  label: __("Company"),  fieldtype: "Link", options: "Company",
         default: frappe.defaults.get_user_default("Company"), reqd: 1},
        {fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee"},
        {fieldname: "tax_year_start", label: __("Tax Year Start"), fieldtype: "Int",
         default: (new Date()).getFullYear(), reqd: 1},
    ],
};
