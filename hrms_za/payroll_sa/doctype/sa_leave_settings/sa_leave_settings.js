frappe.ui.form.on("SA Leave Settings", {
    refresh(frm) {
        const group = __("Actions");
        const buttons = [
            {
                label: __("Seed Leave Period for Year"),
                handler: () => run_with_year(frm, __("Seed Leave Period"),
                    "hrms_za.regional.south_africa.leave.seed_leave_period"),
            },
            {
                label: __("Generate Leave Policy Assignments for Year"),
                handler: () => run_with_year(frm,
                    __("Generate Leave Policy Assignments"),
                    "hrms_za.regional.south_africa.leave.generate_sa_leave_allocations"),
            },
            {
                label: __("Auto-Fill Leave Approvers"),
                handler: () => run_simple(frm, __("Auto-Fill Leave Approvers"),
                    "hrms_za.regional.south_africa.leave.auto_fill_leave_approvers",
                    __("Set each Employee's leave_approver from their Department's approver chain, falling back to the default role. Existing approvers are preserved.")),
            },
            {
                label: __("Provision Employee Users (ESS)"),
                handler: () => run_simple(frm, __("Provision Employee Users"),
                    "hrms_za.regional.south_africa.leave.provision_employee_users",
                    __("Create a User (role: Employee Self Service) for every Employee with a company_email and no user_id. Does NOT send welcome emails automatically — flip Send Welcome Email on the User form when ready.")),
            },
            {
                label: __("Generate SA Holiday List for Year"),
                handler: () => generate_holiday_list(frm),
            },
            {
                label: __("Recompute Sick Leave Cycles"),
                handler: () => run_simple(frm, __("Recompute Sick Leave Cycles"),
                    "hrms_za.regional.south_africa.leave.recompute_sick_leave_cycles",
                    __("Phase-2 stub — will recompute every employee's fixed-cycle 36-month sick-leave balance once the Phase 2 algorithm lands. Safe to click now (it just returns a status).")),
            },
        ];

        // Skip if buttons already attached this lifecycle — refresh fires
        // on every field change, and re-binding allocates a fresh handler
        // closure each time even though add_custom_button dedupes the DOM.
        for (const btn of buttons) {
            if (frm.custom_buttons[btn.label]) continue;
            frm.add_custom_button(btn.label, btn.handler, group);
        }
    },
});


function run_with_year(frm, title, method) {
    frappe.prompt(
        [
            {
                fieldname: "year",
                fieldtype: "Int",
                label: __("Year"),
                default: new Date().getFullYear(),
                reqd: 1,
            },
        ],
        (values) => {
            frappe.confirm(
                __("Run {0} for {1}? This affects every active SA company.",
                   [title, values.year]),
                () => frappe.call({
                    method,
                    args: { year: values.year },
                    freeze: true,
                    freeze_message: __("Running {0} for {1}...", [title, values.year]),
                    callback: (r) => show_result_toast(title, r.message),
                })
            );
        },
        title,
        __("Run")
    );
}


function run_simple(frm, title, method, confirm_text) {
    frappe.confirm(
        confirm_text || __("Run {0}?", [title]),
        () => frappe.call({
            method,
            freeze: true,
            freeze_message: __("Running {0}...", [title]),
            callback: (r) => show_result_toast(title, r.message),
        })
    );
}


function generate_holiday_list(frm) {
    frappe.prompt(
        [
            {
                fieldname: "year",
                fieldtype: "Int",
                label: __("Year"),
                default: new Date().getFullYear(),
                reqd: 1,
            },
            {
                fieldname: "company",
                fieldtype: "Link",
                options: "Company",
                label: __("Company"),
                reqd: 1,
                get_query: () => ({ filters: { country: "South Africa" } }),
            },
        ],
        (values) => frappe.call({
            method: "hrms_za.regional.south_africa.holidays.generate_sa_holiday_list",
            args: { year: values.year, company: values.company },
            freeze: true,
            freeze_message: __("Generating SA Holiday List..."),
            callback: (r) => {
                if (r.message) {
                    frappe.show_alert({
                        message: __("Holiday list {0}: {1} public holidays + {2} weekend rows. Set as default on {3}.",
                                   [r.message.holiday_list,
                                    r.message.public_rows,
                                    r.message.weekend_rows,
                                    r.message.default_on_company || __("(none)")]),
                        indicator: "green",
                    }, 10);
                }
            },
        }),
        __("Generate SA Holiday List"),
        __("Generate")
    );
}


function show_result_toast(title, result) {
    if (!result) {
        frappe.show_alert({
            message: __("{0} completed with no result.", [title]),
            indicator: "orange",
        }, 5);
        return;
    }

    const created = result.created || 0;
    const skipped = result.skipped || 0;
    const failed = (result.failed || []).length;

    let indicator = "green";
    if (failed > 0) indicator = "red";
    else if (created === 0 && skipped > 0) indicator = "blue";

    frappe.show_alert({
        message: __("{0}: {1} created, {2} skipped, {3} failed.",
                   [title, created, skipped, failed]),
        indicator,
    }, 10);

    if (failed > 0) {
        console.warn(`[${title}] failures:`, result.failed);
    }
}
