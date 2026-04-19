# Requirements vs. existing HRMS v16

Organized by the 7 sections in the HR Manager brief. Every item tagged as one of:

- **DELIVERED** — shipped in `hrms_za` v0.0.1 and installed on site
- **EXISTS** — ships in HRMS/ERPNext, plug it in
- **CONFIG** — ships, but needs SA-specific setup (fixtures / custom fields / formula) — testable with configuration only
- **SIMILAR-TEST** — framework is there, but the SA semantics need a custom layer on top and real-world validation
- **PARTIAL** — a subset shipped; a concrete gap remains and is flagged
- **MISSING** — has to be built in `hrms_za`

---

## Progress snapshot — v0.0.1

| Category | Delivered | Still to build |
|---|---|---|
| Employee master fields | SARS tax number, SA ID, UIF contributor flag, UIF reference | SA ID Luhn / 13-digit validator |
| Company statutory fields | Employer PAYE, UIF, SDL refs + SARS trading name | — |
| Employment Types | 7 SA types seeded | — |
| Leave Types (BCEA) | 8 types seeded inc. Annual 15d earned-monthly, Family Responsibility, Maternity, Parental, Adoption, Commissioning, Study | 36-month rolling sick cycle |
| Salary Components | Basic, Overtime, Bonus, Travel Allowance, Cellphone Allowance, UIF Employee (1% capped formula), UIF Employer (statistical 1%), SDL (statistical 1%), **PAYE with full SA calc (rebates + medical credits, 8 unit tests passing)** | ETI, RA deduction cap enforcement (currently trusts `exempted_from_income_tax` flag) |
| Income Tax Slab | **2026/27 SARS brackets** (from 25 Feb 2026 Budget) shipped **ENABLED** for the current tax year; 2025/26 shipped disabled as historical reference | Pure-slab PAYE replaced by SA calculator (rebates + medical credits) |
| **Dashboard Workspace** | `/app/sa-payroll` — single-page HR Manager dashboard with 5 number cards, 3 charts, 8 shortcut buttons, 3 grouped link cards | — |
| **Matrix Report (centerpiece)** | `SA Payroll Matrix` — per-employee monthly matrix with every column from the brief (Basic / OT / Bonus / Allowances / Gross / PAYE / UIF-EE / UIF-ER / SDL / Other / Net) + red compliance flags + drill-down to Salary Slip | — |
| **SARS statutory reports (shape)** | EMP201 Monthly Return, EMP501 Reconciliation, IRP5/IT3(a) Certificate — all delivered as placeholder reports with SARS-correct columns/codes | Real aggregation (blocked on PAYE calculator) |
| **Scheduled email delivery** | Native Frappe **Auto Email Report** supports every report above — shape-correct PDFs/CSVs arrive in HR Manager / Finance / Auditor inboxes on a schedule with zero code | Schedule records to be created per tenant |
| Compliance dashboard | Number cards for Missing Tax Numbers + Missing UIF Refs; per-row red flag tags in SA Payroll Matrix | Overtime BCEA check, PAYE variance, leave liability |

---

## 1. Employee Master Data Table

| Field | Status | Evidence |
|---|---|---|
| Employee ID, Full Name, Job Title (Designation), Department, Start Date (`date_of_joining`) | EXISTS | `erpnext/setup/doctype/employee/employee.json` |
| Employment Type (Permanent / Contract / Temporary) | **DELIVERED** | 7 SA Employment Types seeded — Permanent, Fixed Term, Temporary, Casual, Director, Independent Contractor, Learner |
| CTC | EXISTS | `ctc` field on Employee |
| Basic Salary | EXISTS | via `Salary Structure Assignment.base` |
| **SARS Income Tax Number** | **DELIVERED** | custom field `sa_tax_reference` on Employee |
| **UIF Contributor (Yes/No)** | **DELIVERED** | custom field `uif_contributor` — defaults on, with description of exemptions |
| **SA ID Number** | **PARTIAL** | field `sa_id_number` delivered; 13-digit Luhn validator still TODO |
| **UIF reference number** | **DELIVERED** | custom field `uif_reference` (employee) + `sa_uif_reference` (employer on Company) |

---

## 2. Monthly Payroll Matrix

| Item | Status | Notes |
|---|---|---|
| Per-employee matrix (all columns from brief) | **DELIVERED** | `SA Payroll Matrix` query report at `/app/query-report/SA Payroll Matrix` — columns exactly match the brief, filters by Company/Month/Year/Department/Employment Type, drills through to Salary Slip |
| Basic / Overtime / Bonus / Allowances / Gross | **DELIVERED** | Earning components seeded: Basic, Overtime, Bonus, Travel Allowance, Cellphone Allowance |
| Auto-calculated Gross / Total Deductions / Net Pay | EXISTS | Salary Slip computes natively; surfaced in the matrix |
| **PAYE auto-calc (SARS tax tables + rebates + medical credits)** | **DELIVERED** | Full calc live. HRMS evaluates the 2026/27 slab on Salary Slip validate; `hrms_za.payroll_sa.paye_calculator.adjust_sa_paye` then subtracts primary / secondary (65+) / tertiary (75+) rebates and s6A medical scheme fees credit based on `Employee.date_of_birth` + `Employee.medical_aid_members`, and delta-updates `total_deduction` + `net_pay`. **8 worked-example unit tests pass** (R50k-clamped-to-zero / R300k / R500k × ages 35/65/75 × 0/2/4 medical members / 2026 vs 2027 rebate delta). |
| **UIF = 1% capped at threshold** | **DELIVERED** | `UIF - Employee` component with formula `min(gross_pay, 17712) * 0.01` |
| **UIF Employer 1%** | **DELIVERED** | `UIF - Employer` statistical component |
| **SDL (Skills Dev Levy 1% employer)** | **DELIVERED** | `SDL` statistical component |
| Other deductions (garnishee, RA, medical) | EXISTS | generic Deduction components; surfaced in the matrix as "Other Deductions" residual column |
| **RA / pension tax deductibility (27.5% of remun, max R350k/yr)** | MISSING | SA-specific interaction with PAYE base; needs custom logic |
| **ETI (Employment Tax Incentive)** | MISSING | young-worker rebate |

---

## 3. Leave Management Matrix

| Item | Status | Notes |
|---|---|---|
| Annual leave allocation / entitlement | **DELIVERED** | `Annual Leave (SA)` — 15 days, earned monthly (→ 1.25/month), rounding 0.5, carry-forward + encashment enabled |
| Leave Taken (monthly + YTD) | EXISTS | `Employee Leave Balance` + `Leave Ledger` reports |
| Leave Balance auto-calc | EXISTS | Leave Ledger Entry sums to balance |
| **BCEA annual leave (15 working / 21 consecutive days)** | **DELIVERED** | `Annual Leave (SA)` — 15-working-days variant; add a second record for 21-consecutive-days if any department uses that cycle |
| **1.25 days/month accrual** | **DELIVERED** | baked into Annual Leave (SA) via `earned_leave_frequency=Monthly` |
| Family Responsibility Leave (3 days/year) | **DELIVERED** | `Family Responsibility Leave (SA)` |
| **Sick leave: 30 days per 36-month rolling cycle (BCEA s22)** | **PARTIAL** | `Sick Leave (SA)` shipped as 30-day flat annual; the 36-month rolling window still MISSING |
| **Maternity Leave (120 days)** | **DELIVERED** | `Maternity Leave (SA)` |
| **Parental Leave (10 days)** | **DELIVERED** | `Parental Leave (SA)` |
| **Adoption + Commissioning Parental (70 days)** | **DELIVERED** | both shipped |
| **Study Leave** | **DELIVERED** | `Study Leave (SA)` 5 days (policy, not BCEA) |
| Negative-balance flag | EXISTS | Leave Type `allow_negative` |

---

## 4. Compliance Controls Panel

| Indicator | Status |
|---|---|
| PAYE calc vs expected variance | MISSING — blocked on SA PAYE calculator |
| UIF threshold compliance | MISSING — query report TODO |
| **Missing tax numbers** | **DELIVERED** — number card `SA Employees Missing Tax Number` on dashboard + per-row red flag in SA Payroll Matrix |
| **Missing UIF reference** | **DELIVERED** — number card `SA Employees Missing UIF Reference` + per-row red flag in SA Payroll Matrix |
| Negative leave balances | CONFIG — `Employee Leave Balance Summary` report surfaces it; dashboard chart + threshold TODO |
| Excessive overtime (BCEA: max 10h/week, 3h/day, 45h/week) | MISSING |

---

## 5. Dashboard Visuals

| Chart | Status |
|---|---|
| **Total Payroll Cost (monthly)** | **DELIVERED** — number card `SA Total Payroll Cost (Month)` + line chart `SA Monthly Payroll Cost` (12-month trend) |
| **Departmental Payroll Breakdown** | **DELIVERED** — bar chart `SA Department Payroll (This Month)` on dashboard |
| Designation breakdown | EXISTS — upstream `designation_wise_salary(last_month)` chart still available |
| **Total PAYE Liability** | **DELIVERED** (shape) — number card `SA Total PAYE Liability (Month)`; values depend on PAYE calculator |
| **Total UIF Contributions** | **DELIVERED** — number card `SA Total UIF Contributions (Month)` + donut chart `SA Statutory Contributions` (PAYE / UIF-EE / UIF-ER / SDL) |
| **Total SDL Contributions** | **DELIVERED** — component in statutory donut |
| Leave Liability (Provision) | MISSING — actuarial-style calc |
| Net Pay Distribution | EXISTS — `Salary Register` + `Salary Payments Based on Payment Mode` |
| **Single-URL HR dashboard** | **DELIVERED** — `/app/sa-payroll` workspace ties all of the above + report shortcuts + master-data links into one page |

---

## 6. Automation Rules

| Rule | Status |
|---|---|
| PAYE follows SARS brackets + rebates + medical credits | **DELIVERED** — 2026/27 slab enabled + `adjust_sa_paye` hook applies rebates and s6A credit on every Salary Slip validate |
| UIF 1% capped at threshold | **DELIVERED** — formula on `UIF - Employee` component |
| SDL 1% employer | **DELIVERED** — formula on `SDL` statistical component |
| Earned leave 1.25/month | **DELIVERED** — `Annual Leave (SA)` monthly accrual |
| Sick 30/36-month rolling | MISSING — see §3 |

---

## 7. Output Requirements

| Item | Status |
|---|---|
| **Matrix layout / filtering** | **DELIVERED** — `SA Payroll Matrix` with Company/Month/Year/Department/Employment Type filters |
| **Export monthly payslip summaries** | **DELIVERED** — `SA Payroll Matrix` exports to Excel/CSV/PDF natively from the report toolbar; per-employee Salary Slip print is unchanged |
| **Drill-down per employee** | **DELIVERED** — Employee ID and Salary Slip columns are Link fields → one click to the full record |
| **Red compliance flags** | **DELIVERED** — per-row compliance column in SA Payroll Matrix shows red `Missing Tax Number` / `Missing UIF Ref` indicators; green `OK` otherwise |

---

## 8. Using the system — operational guide

Audience: admin doing the deploy + HR Manager doing monthly payroll.

### 9.1 First-time install (admin, once)

After the image is rebuilt with `hrms_za` baked in:

```bash
docker exec -u frappe frappe-backend-1 \
    bench --site crm.hostedsip.co.za install-app hrms_za

docker exec -u frappe frappe-backend-1 \
    bench --site crm.hostedsip.co.za migrate

docker exec -u frappe frappe-backend-1 \
    bench --site crm.hostedsip.co.za clear-cache
```

`install-app` runs `after_install` — creates all custom fields + fixtures + the two Income Tax Slabs for every SA Company. `migrate` loads the standard records shipped in the app tree: the `SA Payroll` workspace, `SA Payroll Matrix` query report, placeholder SARS reports, 5 number cards, 3 dashboard charts.

If you later set `Company.country = "South Africa"` on a Company that wasn't SA at install, `on_company_update` re-runs the setup automatically. No bench command needed.

### 9.2 Company setup (admin, per SA Company)

On the Company form:
1. Set `Country = South Africa`.
2. In the **South African Statutory References** section: fill `PAYE Reference Number` (10 digits, starts with 7), `UIF Reference Number` (starts with U), `SDL Reference Number` (starts with L), `SARS Registered Trading Name`.
3. Open **Income Tax Slab** list → confirm `SA Tax 2026/2027 - <Company>` exists and is enabled. Confirm `SA Tax 2025/2026 - <Company>` exists and is disabled (historical reference only).
4. Create a `Payroll Period` covering the current tax year (1 March 2026 – 28 February 2027).
5. **Generate the Holiday List for the calendar year.** Without one set as the Company's `Default Holiday List`, every Salary Slip fails with *"No Holiday List was found for Employee X or their company Y"*. `hrms_za` ships a whitelisted helper — call it once per year from `bench console`:
   ```python
   from hrms_za.regional.south_africa.holidays import generate_sa_holiday_list
   generate_sa_holiday_list(2026, company="Hosted Communications")
   ```
   Result: a `South Africa 2026` Holiday List containing all 12 statutory public holidays (fixed + Easter-dependent, Sunday→Monday substitutions applied per Public Holidays Act 36 of 1994) plus every Saturday and Sunday as weekly offs. Assigned as `default_holiday_list` on the named Company. Ad-hoc holidays (election days, declared days of mourning) are NOT auto-generated — add them to the list manually as they're announced. Re-running for the same year refreshes the list in-place.

### 9.3 Employee setup (HR Manager, per employee)

On each Employee form, two new collapsible sections appear:

**South African Tax & Compliance**
- `SA ID Number` — 13 digits.
- `SARS Income Tax Number` — 10 digits.
- `UIF Contributor` — check (default on). Uncheck for directors, foreigners on work permits, or employees < 24 hrs/month.
- `UIF Reference Number` — visible only when UIF Contributor is checked.

**Medical Aid (for s6A PAYE credit)**
- `Medical Aid Scheme` — scheme name (Discovery / Bonitas / etc.).
- `Total Members (incl. main)` — drives the monthly tax credit.
- `Monthly Contribution` — premium paid to the scheme (reserved for s6B, not yet used).

Also verify the core `Date of Birth` field is populated — **mandatory** for age-based rebates. No DOB = primary rebate only (still correct under 65).

### 9.4 Salary Structure (HR Manager, per role / pay band)

Create a `Salary Structure` including at minimum:

- **Earnings**: Basic (required), Overtime, Bonus, Travel Allowance, Cellphone Allowance (as applicable).
- **Deductions**: PAYE, UIF - Employee.
- **Statistical** (not deducted from employee, tracked for EMP201): UIF - Employer, SDL.

Then create a `Salary Structure Assignment` for each employee linking Employee → Structure → `Income Tax Slab = SA Tax 2026/2027 - <Company>`.

### 9.5 Running monthly payroll (HR Manager, once a month)

1. **Create Payroll Entry** — Company + Start Date (1st of month) + End Date (last of month).
2. Click **Get Employees** → **Create Salary Slips**.
3. Each draft slip fires the PAYE calculator: HRMS computes slab tax, `adjust_sa_paye` subtracts rebates + medical credit, totals update.
4. Review matrix on the **`SA Payroll` workspace** → **SA Payroll Matrix** shortcut.
5. Back on the Payroll Entry, **Submit Salary Slips** → Journal Entries posted to the GL automatically.

### 9.6 Dashboard — single URL for management

Navigate to **`/app/sa-payroll`**. What's on the page:

- Row 1 — five number cards: Total Payroll (Month), Total PAYE (Month), Total UIF (Month), Missing Tax Numbers, Missing UIF Refs. Click any card → filtered list of the underlying records.
- Row 2 — three charts: 12-month payroll trend (line), department payroll breakdown this month (bar), statutory contribution mix PAYE/UIF/SDL (donut).
- Row 3 — eight shortcut buttons: SA Payroll Matrix, EMP201, EMP501, IRP5/IT3(a), Employees, Salary Slips, Payroll Entry, Leave Allocation.
- Row 4 — three link cards: SA Master Data, Payroll Processing, Leave & Compliance.

### 9.7 Matrix report — the per-employee grid

From dashboard shortcut or **`/app/query-report/SA Payroll Matrix`**:

Filters: Company (required), Month, Year, Department, Employment Type. Output: one row per submitted Salary Slip with Basic / OT / Bonus / Travel / Cell / Gross / PAYE / UIF-EE / UIF-ER / SDL / Other / Net, plus SARS Tax No. + UIF Ref + a **Compliance** column that renders red `Missing Tax Number` / `Missing UIF Ref` chips for anyone whose data isn't clean, green `OK` otherwise. Employee ID and Salary Slip columns are Links — one click drills through. Toolbar exports to Excel / CSV / PDF.

### 9.8 Wiring Auto Email Reports (admin, once per schedule)

For every recipient/report pairing in §8:

1. **`/app/auto-email-report/new`**
2. **Report**: `SA Payroll Matrix` (or EMP201 / EMP501 / IRP5 / leave balance).
3. **Filters**: JSON object, supports Jinja for dynamic dates. Example for "current month":
   ```
   {"month": "{{ today().month }}", "year": "{{ today().year }}"}
   ```
4. **User**: sets the permission context (pick a user with HR Manager role).
5. **Email To**: comma-separated recipient emails.
6. **Frequency**: Daily / Weekly / Monthly. For Weekly, set Day of Week.
7. **Day of Month** (for Monthly): 25 for pre-run, 1 for post-run, 5 for EMP201.
8. **Format**: PDF (most reliable for HR bosses), CSV (for Finance import), Excel, or HTML.
9. Save → ensure `Enabled` is checked.

The scheduler container (`frappe-scheduler-1`) runs these automatically via the Frappe scheduler + Redis queue. Delivery attempts are logged in **Email Queue**; failures are retried.

### 9.9 How to eyeball PAYE correctness

For any submitted Salary Slip on an SA employee, open the slip and compare the PAYE deduction line against these anchors (2026/27 tax year, no medical aid):

| Monthly gross | Under 65 | Age 65 | Age 75 |
|---|---|---|---|
| R25 000 | ≈ R1 381 | ≈ R567 | ≈ R296 |
| R50 000 | ≈ R6 801 | ≈ R5 987 | ≈ R5 716 |
| R100 000 | ≈ R23 318 | ≈ R22 504 | ≈ R22 232 |

Add medical credit: subtract R376/month for each of the first two members, plus R254/month for each additional. (These anchors match the regression suite in `hrms_za/payroll_sa/tests/test_paye_calculator.py`.)

---

## 9. Automation & Scheduling — the unfair advantage

> **Feature highlight for management.** Every query report in this app — matrix, EMP201, EMP501, IRP5, and every compliance card — plugs into Frappe's native **Auto Email Report** scheduler with **zero extra code**. Create one "Auto Email Report" record per report, set the recipients, cadence, and format, and the system mails the rendered report (PDF / Excel / HTML) on schedule. If no data changes, the same (correct) report lands in the inbox next month — which is itself an audit-trail artefact for compliance reviews.

Feasible out-of-the-box schedule once the app is installed:

| Recipient | Report | Cadence | Purpose |
|---|---|---|---|
| HR Manager | SA Payroll Matrix | **25th of each month** (payroll cut-off) | Pre-run sanity check before Payroll Entry submission |
| HR Manager + Finance | SA Payroll Matrix | **1st of each month** (final, after submit) | Month-end payroll archive |
| Finance | EMP201 Monthly Return | **5th of each month** (EMP201 due the 7th) | SARS submission prep |
| Finance + Auditor | EMP501 Reconciliation | **15 September** (interim) + **15 May** (annual) | SARS bi-annual reconciliation |
| Each Employee (ESS) | IRP5/IT3(a) Certificate (filtered to self) | **Annually — 31 May** | Employee tax certificate delivery |
| Compliance Officer | Missing Tax Numbers / Missing UIF Refs | **Weekly — Monday 08:00** | Proactive data-quality follow-up before payroll |
| HR Manager | Employee Leave Balance Summary | **1st of each quarter** | Leave-liability awareness |
| CFO | Outgoing Salary + Statutory Contributions charts (dashboard digest) | **1st of each month** | Payroll cost trend |

Implementation effort per schedule: **≈ 30 seconds in the Desk UI** — no code, no cron, no container rebuild. Delivery is reliable because it runs on Frappe's Redis-backed scheduler (already live on this host as the `frappe-scheduler` container).

Mechanism: `Auto Email Report` DocType → pick an existing report → set filters (Jinja variables supported for dynamic dates like "last month") → pick recipients → pick frequency (`Daily` / `Weekly` / `Monthly`) → pick format. Frappe handles rendering, attachment, and delivery. Subject line and body template are per-schedule. Failed sends are logged in `Email Queue` with retry.

**Why this matters to HR Management:** the dashboard visit becomes optional. The compliance artefacts arrive in the inbox on the correct day, with the correct filters, in the correct format, addressed to the correct people — permanently, without any human remembering to run it.

---

## SARS statutory reports

All now have a **shape-correct delivered report** with SARS-aligned columns/source codes. Real aggregation lands with the PAYE calculator:

| Report | Status | Notes |
|---|---|---|
| **EMP201** — monthly PAYE/UIF/SDL submission | **DELIVERED (shape)** | Line items for codes 7002 (PAYE) / 7003 (SDL) / 7004 (UIF EE) / 7005 (UIF ER) / 7006 (ETI) / total. Amounts computed once PAYE calculator ships. |
| **EMP501** — bi-annual reconciliation | **DELIVERED (shape)** | Per-employee columns: Tax No, Total Remun, PAYE Declared vs On-Cert vs Paid, Variance, Status. |
| **IRP5 / IT3(a)** — annual employee tax certificates | **DELIVERED (shape)** | SARS source-code layout (3601 / 3605 / 3697 / 3698 / 4101–4103 / 4116 etc.). |
| **UI-19** — UIF declaration | MISSING | Still to build. |
| **OID / Workmen's Comp W.As.8** — annual return of earnings | MISSING | Still to build. |

---

## Headline risks — still open

1. **36-month rolling sick leave cycle** — Sick Leave (SA) shipped as 30-day flat for now; the rolling window must replace it before audit readiness.
2. **UIF ceiling hardcoded at R17,712** — move into an `SA Payroll Settings` Single doctype before the annual change so tenants can edit without touching code.
3. **Retirement fund 27.5% / R350k cap** — the PAYE calculator currently trusts the upstream `exempted_from_income_tax` flag on the RA component to reduce taxable income. A validator that clamps excess contributions to the s11F cap is a follow-up.
4. **Auto Email Report schedules not yet created** — mechanism in place; each tenant's recipient list and cadence is a per-company config task (documented in §8).
5. **Annual SARS refresh** is now a documented process — update `income_tax_slab.py` + `paye_parameters.py` every March and ship a new patch release.
6. **Travel allowance 80/20 rule, fringe benefits, bonus spreading** — deferred, not in v0.0.1.
