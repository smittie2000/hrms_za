/* eslint-disable */
frappe.query_reports["EMP501 Reconciliation"] = {
    filters: [
        {fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
         default: frappe.defaults.get_user_default("Company"), reqd: 1},
        {fieldname: "period", label: __("Period"), fieldtype: "Select",
         options: "Interim (Mar-Aug)\nAnnual (Mar-Feb)",
         default: "Interim (Mar-Aug)", reqd: 1},
        {fieldname: "year",   label: __("Tax Year Start"), fieldtype: "Int",
         default: (new Date()).getFullYear(), reqd: 1},
    ],
};
