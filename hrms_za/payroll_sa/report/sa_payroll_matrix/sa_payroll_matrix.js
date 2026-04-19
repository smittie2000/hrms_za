// SA Payroll Matrix — filters
/* eslint-disable */

frappe.query_reports["SA Payroll Matrix"] = {
    filters: [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
            reqd: 1,
        },
        {
            fieldname: "month",
            label: __("Month"),
            fieldtype: "Select",
            options: [
                {value: 1,  label: __("January")},
                {value: 2,  label: __("February")},
                {value: 3,  label: __("March")},
                {value: 4,  label: __("April")},
                {value: 5,  label: __("May")},
                {value: 6,  label: __("June")},
                {value: 7,  label: __("July")},
                {value: 8,  label: __("August")},
                {value: 9,  label: __("September")},
                {value: 10, label: __("October")},
                {value: 11, label: __("November")},
                {value: 12, label: __("December")},
            ],
            default: (new Date()).getMonth() + 1,
            reqd: 1,
        },
        {
            fieldname: "year",
            label: __("Year"),
            fieldtype: "Int",
            default: (new Date()).getFullYear(),
            reqd: 1,
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department",
        },
        {
            fieldname: "employment_type",
            label: __("Employment Type"),
            fieldtype: "Link",
            options: "Employment Type",
        },
    ],
};
