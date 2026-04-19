# HRMS v16 ↔ ERPNext v16 — Integration Map

Source trees analyzed:
- `/tmp/frappe-analysis/hrms` (branch `version-16`)
- `/tmp/frappe-analysis/erpnext` (branch `version-16`)

---

## 1. Dependency direction — one-way: HRMS → ERPNext

- `hrms/pyproject.toml:74` → `erpnext = ">=16.0.0,<17.0.0"` (hard dep)
- `hrms/hrms/hooks.py:7` → `required_apps = ["frappe/erpnext"]`
- `erpnext/pyproject.toml:40-41` → only depends on `frappe`; **zero** reference to hrms.

Implication for `hrms_za`: it must depend on `hrms` (which transitively pulls `erpnext`). Don't try to build payroll on top of erpnext alone.

---

## 2. DocType references across the boundary

**HRMS → ERPNext (heavy, write path):**
- Salary Slip, Payroll Entry → Journal Entry, Payment Entry, GL Entry
- Expense Claim → Payment Entry / Journal Entry / GL Entry (via `AccountsController`)
- Employee Advance, Gratuity, Leave Encashment → Payment Entry / GL Entry
- All of the above → Account, Cost Center, Company

**ERPNext → HRMS (light, mostly hook-driven, read):**
- Payment Entry & Journal Entry emit events HRMS listens to (see §5).

Key proofs of coupling:
- `hrms/payroll/doctype/salary_slip/salary_slip.py:31-34` imports `erpnext.accounts.utils`, `erpnext.utilities.transaction_base.TransactionBase`
- `hrms/hr/doctype/expense_claim/expense_claim.py:10,24` inherits `erpnext.controllers.accounts_controller.AccountsController`, imports `make_gl_entries`

---

## 3. Shared DocTypes — Employee lives in ERPNext

| DocType | Home | Notes |
|---|---|---|
| Employee | **ERPNext** (`erpnext/setup/doctype/employee/`) | HRMS overrides class via `override_doctype_class` → `hrms.overrides.employee_master.EmployeeMaster` |
| Department, Company, Designation | ERPNext | HRMS adds custom fields (payroll cost center, leave block list, approvers, HRA settings, payroll payable account) |
| Holiday List | ERPNext | consumed heavily by HRMS leave/payroll |
| Account, Cost Center | ERPNext | targets of all HRMS GL posting |
| User, Role, DocType | Frappe | |

**Do not** create a new Employee doctype in `hrms_za`. Extend via custom fields or sibling doc_events.

---

## 4. Accounting integration — how HR docs reach the GL

- **Salary Slip** posts via `make_journal_entry()` at `hrms/payroll/doctype/salary_slip/salary_slip.py:635`; payroll payable account comes from `get_payroll_payable_account()` at :2466 (reads `Company.default_payroll_payable_account`).
- **Salary component ↔ account mapping** is per-company, via the `Salary Component Account` child doctype.
- **Payroll Entry** (`hrms/payroll/doctype/payroll_entry/payroll_entry.py:109-183`) validates accounts and cancels linked JEs on reversal.
- **Expense Claim** goes through ERPNext's `AccountsController` — GL entries on submit are automatic if the COA is set up correctly.
- **Employee Advance, Gratuity, Leave Encashment** declared in `advance_payment_payable_doctypes` (`hooks.py:253`) — Payment Entry can link and settle these.
- **Loan integration** (lending app, if present) is wired via custom fields injected by `hrms/setup.py:815-851` (`repay_from_salary` on Loan / Loan Repayment).

---

## 5. Hook-based integration surface (`hrms/hooks.py`)

**`override_doctype_class` (:152-157):**
- Employee → `EmployeeMaster`
- Timesheet → `EmployeeTimesheet`
- Payment Entry → `EmployeePaymentEntry`
- Project → `EmployeeProject`

**`doc_events` (:163-219) — ERPNext doctypes HRMS intercepts:**
- User.validate — enforce employee-role rules
- Company.validate/on_update — trigger regional setup, payroll field defaults
- Holiday List.on_update/on_trash — cache invalidation
- Timesheet.validate — require active employee
- Payment Entry.on_submit/on_cancel/on_update_after_submit — sync Expense Claim payment
- **Journal Entry** — validate, on_submit, on_cancel update Expense Claim, Full & Final Statement, Salary Withholding
- Loan.validate — enforce salary-repayment invariants
- Employee.* — onboarding, approver role sync, job applicant link, transfers, trash cleanup

**Regional dispatch hook (:280-286):** currently India-only; pattern is `frappe.get_attr(module_name)()`.

---

## 6. Regional / localization split — critical for hrms_za

**HRMS regional tree (`hrms/hrms/regional/`):** only `india/` (PF, PT, HRA exemption, Gratuity Rule, tax slabs) + an empty `united_arab_emirates/`.

**ERPNext regional tree (`erpnext/erpnext/regional/`):** includes **`south_africa/`** already — GST/VAT templates, print formats. **No HRMS-side SA support exists yet.**

**Wiring:**
- `run_regional_setup(country)` fires from Company on_update hook.
- Dispatcher calls `hrms.regional.{frappe.scrub(country)}.setup.setup()` (e.g. `hrms.regional.south_africa.setup.setup()`).
- `hrms/overrides/company.py:41-51` wraps the call in try/except — missing module silently no-ops, so adding `south_africa/` is non-breaking.
- Country comes from **`Company.country`** (not System Settings).

**Shape of hrms_za work:**
- Sibling app (preferred per CLAUDE.md portability constraint) providing:
  - `hrms_za/regional/south_africa/setup.py` — create SA salary components, tax slabs, custom fields (SAID, tax reference, UIF reference).
  - `hrms_za/regional/south_africa/data/salary_components.json` — PAYE, UIF (ER/EE), SDL, medical-aid tax credit, pension/RA contribution, etc.
  - Regional overrides for PAYE calculation (if formula-only salary components prove insufficient).
  - SARS reports (EMP201, EMP501, IRP5/IT3(a)) as query/script reports.

---

## 7. Reports & print formats

- HRMS reports (`hrms/payroll/report/*`) are self-contained — they query HRMS doctypes only, not ERPNext transactions.
- HRMS contributes 9 doctypes to global search at indices 19-43 (after ERPNext masters at 0-18) — `hooks.py:289-301`.
- No cross-app report coupling to worry about.

---

## 8. Fixtures & setup wizard

- **HRMS global fixtures** (`hrms/setup.py:332-422`): generic Leave Types, Employment Types, Expense Claim Types, Vehicle Service Items, Job Applicant Sources. Country-agnostic.
- **ERPNext install** seeds COA, tax templates, cost centers per country.
- **Per-country HRMS fixtures** load at Company create/country-change via `make_company_fixtures` — reads `hrms/regional/<country>/data/salary_components.json` if present. This is the hook hrms_za uses.

---

## 9. Permissions / roles

- Shared role names between apps: HR User, HR Manager, Leave Approver, Expense Approver, Accounts User/Manager. No conflicts.
- HRMS ships a Role Profile "HR" at `hrms/setup.py:748-755`.
- `Employee Self Service` User Type (`hrms/setup.py:621-660`) gates ESS doc access.
- India regional creates report-scoped role perms (`hrms/regional/india/setup.py:246-259`).
- For hrms_za: reuse existing HR roles; only define new ones if SA-specific workflows (e.g. SARS submission approval) justify it.

---

## Headline constraints for hrms_za

1. Build as a **standalone app**, add via `apps.json` — do **not** fork hrms unless a change must live inside hrms's module tree.
2. Extend Employee via custom fields / sibling hooks, never by redefining the doctype.
3. Hook into `Company.country == "South Africa"` regional dispatch; keep PAYE/UIF logic in salary component formulas where possible — they survive HRMS upgrades.
4. SA is already present in `erpnext/regional/south_africa/` (tax/VAT). Do **not** duplicate — layer payroll-side localization alongside.
5. Salary component → GL account mapping is per-company via `Salary Component Account`. Fixtures should create components; account mapping must be documented (per-tenant) rather than hardcoded.
6. Expense Claim / Advance / Gratuity inherit ERPNext accounting — they just need an SA-aware COA, no HRMS-side work.
7. Data must live in DocTypes, not host files (portability for Frappe Cloud / Coolify migration).
