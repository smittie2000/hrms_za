"""
Phase 1 leave-automation integration tests.

Unlike test_paye_calculator (pure-function pytest), these need a real Frappe
runtime because they exercise seeders, doc events, and Leave Policy
Assignment submission.

Run inside the backend container:

    docker exec -it -u frappe frappe-backend-1 \\
        bench --site <your-site> run-tests \\
        --module hrms_za.payroll_sa.tests.test_leave_setup

FrappeTestCase wraps each test_* method in its own savepoint, so writes
INSIDE a test method roll back automatically. Records created in
`setUpClass` (Companies, Employees, Leave Periods) DO NOT roll back —
this module's `tearDownClass` deletes those explicitly so a re-run starts
clean. Nothing here should touch real tenant data.
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from hrms_za.regional.south_africa.data.leave_policy import LEAVE_POLICY_NAME
from hrms_za.regional.south_africa.data.notifications import NOTIFICATIONS
from hrms_za.regional.south_africa.leave import (
    _try_assign_default_policy,
    auto_fill_leave_approvers,
)
from hrms_za.regional.south_africa.setup import (
    current_cycle_window_for_date,
    install_ess_permissions,
    install_leave_policy,
    install_notifications,
    install_sa_leave_settings_defaults,
    resolve_sa_standard_leave_policy,
)


TEST_COMPANY_NAME = "HRMS-ZA Test Co (SA)"
TEST_COMPANY_ABBR = "HRMSZA"
TEST_NON_SA_COMPANY = "HRMS-ZA Test Co (ZZ)"
TEST_NON_SA_ABBR = "HRMSZAZZ"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _ensure_company(name, abbr, country):
    if frappe.db.exists("Company", name):
        return name
    frappe.get_doc({
        "doctype": "Company",
        "company_name": name,
        "abbr": abbr,
        "country": country,
        "default_currency": "ZAR" if country == "South Africa" else "USD",
    }).insert(ignore_permissions=True)
    return name


def _ensure_test_employee(company, date_of_joining, name_suffix="1"):
    """Create a minimal test Employee on `company`; return the Employee name."""
    employee_name = f"hrms_za_test_employee_{name_suffix}"
    if frappe.db.exists("Employee", {"employee_name": employee_name}):
        return frappe.db.get_value(
            "Employee", {"employee_name": employee_name}, "name"
        )

    doc = frappe.get_doc({
        "doctype": "Employee",
        "employee_name": employee_name,
        "first_name": employee_name,
        "company": company,
        "date_of_joining": date_of_joining,
        "gender": "Other",
        "status": "Active",
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def _settings():
    return frappe.get_single("SA Leave Settings")


def _purge_test_employees_and_dependencies(companies):
    """
    Delete every Employee whose employee_name starts with the
    'hrms_za_test_employee_' marker, plus their LPAs / Comments / Leave
    Periods on the supplied test companies. Safe to call when nothing was
    seeded — every step is exists-checked.

    Companies are deliberately NOT deleted: Frappe blocks Company deletion
    once child Account / Cost Center records have been auto-created, and
    the test classes' setUpClass paths are idempotent (`_ensure_company`).
    """
    test_employees = frappe.get_all(
        "Employee",
        filters={"employee_name": ["like", "hrms_za_test_employee_%"]},
        pluck="name",
    )

    if test_employees:
        for lpa in frappe.get_all(
            "Leave Policy Assignment",
            filters={"employee": ["in", test_employees]},
            pluck="name",
        ):
            try:
                frappe.delete_doc(
                    "Leave Policy Assignment", lpa,
                    ignore_permissions=True, force=True,
                )
            except Exception:
                pass

        for cmt in frappe.get_all(
            "Comment",
            filters={
                "reference_doctype": "Employee",
                "reference_name": ["in", test_employees],
            },
            pluck="name",
        ):
            try:
                frappe.delete_doc(
                    "Comment", cmt, ignore_permissions=True, force=True,
                )
            except Exception:
                pass

        for emp in test_employees:
            try:
                frappe.delete_doc(
                    "Employee", emp, ignore_permissions=True, force=True,
                )
            except Exception:
                pass

    for lp in frappe.get_all(
        "Leave Period",
        filters={"company": ["in", list(companies)]},
        pluck="name",
    ):
        try:
            frappe.delete_doc(
                "Leave Period", lp, ignore_permissions=True, force=True,
            )
        except Exception:
            pass

    frappe.db.commit()


# -----------------------------------------------------------------------------
# Seeder tests
# -----------------------------------------------------------------------------

class TestSeeders(FrappeTestCase):
    def test_settings_defaults_populated(self):
        install_sa_leave_settings_defaults()
        s = _settings()
        self.assertEqual(int(s.cycle_start_month), 1)
        self.assertEqual(int(s.cycle_start_day), 1)
        self.assertEqual(int(s.sick_cycle_months), 36)
        self.assertEqual(int(s.sick_days_per_cycle), 30)
        self.assertEqual(s.default_approver_fallback_role, "HR Manager")

    def test_settings_seeder_respects_user_edits(self):
        install_sa_leave_settings_defaults()
        s = _settings()
        s.cycle_start_month = 3  # HR edit — simulate user change to March
        s.save(ignore_permissions=True)

        # Re-run seeder — must not overwrite the edited value.
        install_sa_leave_settings_defaults()
        self.assertEqual(int(_settings().cycle_start_month), 3)

    def test_leave_policy_seed_is_seed_once(self):
        install_leave_policy()
        first = resolve_sa_standard_leave_policy()
        self.assertIsNotNone(first, "policy must be created")

        install_leave_policy()  # must be no-op
        self.assertEqual(resolve_sa_standard_leave_policy(), first)

    def test_notifications_seed_is_idempotent(self):
        install_notifications()
        before = frappe.db.count("Notification", {"document_type": "Leave Application"})

        install_notifications()  # must not create duplicates
        after = frappe.db.count("Notification", {"document_type": "Leave Application"})
        self.assertEqual(before, after)

        for name, _, _ in NOTIFICATIONS:
            self.assertTrue(
                frappe.db.exists("Notification", name),
                f"seeded Notification '{name}' missing",
            )

    def test_ess_permissions_seed_is_idempotent(self):
        install_ess_permissions()
        before = frappe.db.count(
            "Custom DocPerm",
            {"role": "Employee Self Service", "parent": "Leave Application"},
        )

        install_ess_permissions()  # must not stack duplicates
        after = frappe.db.count(
            "Custom DocPerm",
            {"role": "Employee Self Service", "parent": "Leave Application"},
        )
        self.assertEqual(before, after)


# -----------------------------------------------------------------------------
# Cycle window tests (pure, no Frappe DB writes)
# -----------------------------------------------------------------------------

class TestCycleWindow(FrappeTestCase):
    def test_1_jan_anchor_mid_year(self):
        install_sa_leave_settings_defaults()
        frm, to = current_cycle_window_for_date("2026-07-15")
        self.assertEqual(getdate(frm), getdate("2026-01-01"))
        self.assertEqual(getdate(to), getdate("2026-12-31"))

    def test_1_jan_anchor_on_anchor(self):
        install_sa_leave_settings_defaults()
        frm, to = current_cycle_window_for_date("2026-01-01")
        self.assertEqual(getdate(frm), getdate("2026-01-01"))
        self.assertEqual(getdate(to), getdate("2026-12-31"))

    def test_mar_1_anchor_pre_anchor_date(self):
        install_sa_leave_settings_defaults()
        s = _settings()
        s.cycle_start_month = 3
        s.cycle_start_day = 1
        s.save(ignore_permissions=True)
        try:
            # Feb 15 2026 is BEFORE the 1-March anchor → falls in 2025/26 cycle
            frm, to = current_cycle_window_for_date("2026-02-15")
            self.assertEqual(getdate(frm), getdate("2025-03-01"))
            self.assertEqual(getdate(to), getdate("2026-02-28"))
        finally:
            s.cycle_start_month = 1
            s.cycle_start_day = 1
            s.save(ignore_permissions=True)


# -----------------------------------------------------------------------------
# Employee auto-assign tests
# -----------------------------------------------------------------------------

class TestEmployeeAutoAssign(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        install_leave_policy()
        install_sa_leave_settings_defaults()
        _ensure_company(TEST_COMPANY_NAME, TEST_COMPANY_ABBR, "South Africa")
        _ensure_company(TEST_NON_SA_COMPANY, TEST_NON_SA_ABBR, "United States")
        # Force a Leave Period covering today on the SA test company.
        frm, to = current_cycle_window_for_date(today())
        if not frappe.db.exists(
            "Leave Period",
            {"company": TEST_COMPANY_NAME, "from_date": frm},
        ):
            frappe.get_doc({
                "doctype": "Leave Period",
                "company": TEST_COMPANY_NAME,
                "from_date": frm,
                "to_date": to,
                "is_active": 1,
            }).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        _purge_test_employees_and_dependencies(
            {TEST_COMPANY_NAME, TEST_NON_SA_COMPANY},
        )
        super().tearDownClass()

    def test_sa_employee_with_doj_gets_assignment(self):
        emp = _ensure_test_employee(
            TEST_COMPANY_NAME, add_days(today(), -30), name_suffix="sa_with_doj"
        )
        # Simulate an already-inserted Employee path (after_insert would have
        # fired on real insert; call explicitly here so we can assert on it
        # without relying on hook ordering in the test runner).
        frappe.clear_cache()
        _try_assign_default_policy(frappe.get_doc("Employee", emp))

        self.assertTrue(
            frappe.db.exists(
                "Leave Policy Assignment",
                {"employee": emp, "docstatus": 1},
            ),
            "SA Employee with valid DOJ must get a submitted LPA",
        )

    def test_employee_without_doj_skipped_with_comment(self):
        # Create an Employee with no DOJ. We must use db-level update to
        # bypass the Employee doctype's mandatory validation on date_of_joining
        # if present — otherwise construct with DOJ and then null it out
        # pre-hook invocation.
        emp = _ensure_test_employee(
            TEST_COMPANY_NAME, today(), name_suffix="sa_no_doj"
        )
        frappe.db.set_value("Employee", emp, "date_of_joining", None)
        before = frappe.db.count(
            "Leave Policy Assignment", {"employee": emp, "docstatus": 1}
        )
        _try_assign_default_policy(frappe.get_doc("Employee", emp))
        after = frappe.db.count(
            "Leave Policy Assignment", {"employee": emp, "docstatus": 1}
        )
        self.assertEqual(before, after, "no LPA must be created without DOJ")

        # Comment must be logged on the Employee timeline.
        comment = frappe.db.exists(
            "Comment",
            {
                "reference_doctype": "Employee",
                "reference_name": emp,
                "content": ["like", "%date_of_joining is missing%"],
            },
        )
        self.assertTrue(comment, "skip reason must be recorded as Comment")

    def test_non_sa_employee_is_skipped(self):
        emp = _ensure_test_employee(
            TEST_NON_SA_COMPANY, add_days(today(), -30),
            name_suffix="non_sa",
        )
        before = frappe.db.count(
            "Leave Policy Assignment", {"employee": emp}
        )
        _try_assign_default_policy(frappe.get_doc("Employee", emp))
        after = frappe.db.count(
            "Leave Policy Assignment", {"employee": emp}
        )
        self.assertEqual(before, after, "non-SA employee must be skipped")


# -----------------------------------------------------------------------------
# Approver resolution tests
# -----------------------------------------------------------------------------

class TestApproverResolution(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        install_sa_leave_settings_defaults()
        _ensure_company(TEST_COMPANY_NAME, TEST_COMPANY_ABBR, "South Africa")

    @classmethod
    def tearDownClass(cls):
        _purge_test_employees_and_dependencies({TEST_COMPANY_NAME})
        super().tearDownClass()

    def test_auto_fill_skips_employees_with_existing_approver(self):
        emp = _ensure_test_employee(
            TEST_COMPANY_NAME, add_days(today(), -10),
            name_suffix="approver_preset",
        )
        frappe.db.set_value(
            "Employee", emp, "leave_approver", "Administrator"
        )
        result = auto_fill_leave_approvers(company=TEST_COMPANY_NAME)
        # Admin must remain; skipped count should include this one.
        self.assertEqual(
            frappe.db.get_value("Employee", emp, "leave_approver"),
            "Administrator",
        )
        self.assertGreaterEqual(result["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
