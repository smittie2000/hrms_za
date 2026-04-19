/* eslint-disable */
frappe.query_reports["EMP201 Monthly Return"] = {
    filters: [
        {fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
         default: frappe.defaults.get_user_default("Company"), reqd: 1},
        {fieldname: "month", label: __("Month"), fieldtype: "Select",
         options: "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12",
         default: (new Date()).getMonth() + 1, reqd: 1},
        {fieldname: "year", label: __("Year"), fieldtype: "Int",
         default: (new Date()).getFullYear(), reqd: 1},
    ],
};
