"""
SA Leave Settings — Single DocType surfacing every editable knob for the
South-African leave-automation layer.

Everything downstream (the Employee after_insert hook, the scheduler tasks,
the bulk helpers exposed as action buttons) reads its configuration from
here via `frappe.get_single("SA Leave Settings")`. Never hardcode any of
these values elsewhere in hrms_za.

The install-time seeder lives in
`hrms_za.regional.south_africa.setup.install_sa_leave_settings_defaults`
and follows the "fill empty fields only" contract so HR edits survive
re-install.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class SALeaveSettings(Document):
    def validate(self):
        self._validate_cycle_anchor()

    def _validate_cycle_anchor(self):
        month = self.cycle_start_month
        day = self.cycle_start_day

        if not 1 <= month <= 12:
            frappe.throw(_("Cycle Start Month must be between 1 and 12."))

        if not 1 <= day <= 31:
            frappe.throw(_("Cycle Start Day must be between 1 and 31."))

        # Reject month+day combos that never exist on any real date
        # (e.g. 31 Feb, 31 Apr). Feb 29 is accepted — cycle_start_for_year
        # normalises it to Feb 28 in non-leap years.
        days_per_month = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
                          7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
        if day > days_per_month[month]:
            frappe.throw(
                _("Day {0} is not valid for month {1}.").format(day, month)
            )
