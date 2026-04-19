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
| Salary Components | Basic, Overtime, Bonus, Travel Allowance, Cellphone Allowance, UIF Employee (1% capped formula), UIF Employer (statistical 1%), SDL (statistical 1%), PAYE placeholder | PAYE calc with rebates + medical credits, ETI, RA deduction cap |
| Income Tax Slab | 2025/26 SARS brackets, shipped DISABLED for verification | 2026/27 brackets, pure-slab PAYE replaced by SA calculator |
| SARS statutory reports | — | EMP201, EMP501, IRP5/IT3(a), UI-19, OID W.As.8 |
| Compliance dashboard | — | All indicators (variance, threshold, missing refs, overtime, leave liability) |

---

## 1. Employee Master Data Table

| Field | Status | Evidence |
|---|---|---|
| Employee ID, Full Name, Job Title (Designation), Department, Start Date (`date_of_joining`) | EXISTS | `erpnext/setup/doctype/employee/employee.json` |
| Employment Type (Permanent / Contract / Temporary) | **DELIVERED** | 7 SA Employment Types seeded by `hrms_za/regional/south_africa/data/employment_types.py` — Permanent, Fixed Term, Temporary, Casual, Director, Independent Contractor, Learner |
| CTC | EXISTS | `ctc` field on Employee |
| Basic Salary | EXISTS | via `Salary Structure Assignment.base` |
| **SARS Income Tax Number** | **DELIVERED** | custom field `sa_tax_reference` on Employee |
| **UIF Contributor (Yes/No)** | **DELIVERED** | custom field `uif_contributor` — defaults on, with description of exemptions |
| **SA ID Number** | **PARTIAL** | field `sa_id_number` delivered; 13-digit Luhn validator still TODO |
| **UIF reference number** | **DELIVERED** | custom field `uif_reference` (employee side) + `sa_uif_reference` (employer side on Company) |

---

## 2. Monthly Payroll Matrix

| Item | Status | Notes |
|---|---|---|
| Basic / Overtime / Bonus / Allowances / Gross | **DELIVERED** | Earning components seeded: Basic, Overtime, Bonus, Travel Allowance, Cellphone Allowance |
| Auto-calculated Gross / Total Deductions / Net Pay | EXISTS | Salary Slip computes natively |
| **PAYE auto-calc (SARS tax tables)** | **SIMILAR-TEST** | 2025/26 Income Tax Slab shipped disabled for reference; PAYE salary component is a placeholder. Rebates (primary/secondary/tertiary) + medical aid tax credits (s6A/s6B) need custom calculator — not in v0.0.1. |
| **UIF = 1% capped at threshold** | **DELIVERED** | `UIF - Employee` component with formula `min(gross_pay, 17712) * 0.01`. Ceiling hardcoded; moving to SA Payroll Settings single doctype in next slice. |
| **UIF Employer 1%** | **DELIVERED** | `UIF - Employer` statistical component (not deducted from employee; tracked for EMP201) |
| **SDL (Skills Dev Levy 1% employer)** | **DELIVERED** | `SDL` statistical component, 1% of gross. Small employers (< R500k annual payroll) should disable. |
| Other deductions (garnishee, RA, medical) | EXISTS | generic Deduction components |
| **RA / pension tax deductibility (27.5% of remun, max R350k/yr)** | MISSING | SA-specific interaction with PAYE base; needs custom logic |
| **ETI (Employment Tax Incentive)** | MISSING | young-worker rebate; optional but material |

---

## 3. Leave Management Matrix

| Item | Status | Notes |
|---|---|---|
| Annual leave allocation / entitlement | **DELIVERED** | `Annual Leave (SA)` — 15 days, earned monthly (→ 1.25/month), rounding 0.5, carry-forward + encashment enabled |
| Leave Taken (monthly + YTD) | EXISTS | `Employee Leave Balance` + `Leave Ledger` reports |
| Leave Balance auto-calc | EXISTS | Leave Ledger Entry sums to balance |
| **BCEA annual leave (15 working / 21 consecutive days)** | **DELIVERED** | shipped as `Annual Leave (SA)` — 15-working-days variant (most common); add a second Leave Type record for 21-consecutive-days if any department uses that cycle |
| **1.25 days/month accrual** | **DELIVERED** | baked into Annual Leave (SA) via `earned_leave_frequency=Monthly` |
| Family Responsibility Leave (3 days/year) | **DELIVERED** | `Family Responsibility Leave (SA)` |
| **Sick leave: 30 days per 36-month rolling cycle (BCEA s22)** | **PARTIAL** | `Sick Leave (SA)` shipped as 30-day flat annual; the 36-month rolling window is still MISSING — flagged as "treat as 30 days/year until the SA Sick Leave Cycle doctype ships". Budget real design time here. |
| **Maternity Leave (120 days)** | **DELIVERED** | `Maternity Leave (SA)` — unpaid under BCEA (UIF covers portion) |
| **Parental Leave (10 days)** | **DELIVERED** | `Parental Leave (SA)` |
| **Adoption + Commissioning Parental (70 days)** | **DELIVERED** | both shipped |
| **Study Leave** | **DELIVERED** | `Study Leave (SA)` 5 days (policy, not BCEA) |
| Negative-balance flag | EXISTS | Leave Type `allow_negative` |

---

## 4. Compliance Controls Panel

| Indicator | Status |
|---|---|
| PAYE calc vs expected variance | MISSING — needs SA PAYE calculator to ship first, then a reconciliation report |
| UIF threshold compliance | MISSING — need a query report flagging employees whose UIF deduction ≠ expected from formula |
| Missing tax numbers | **PARTIAL** — field exists now (`sa_tax_reference`); List View filter / query report still to build |
| Missing UIF reference | **PARTIAL** — field exists (`uif_reference`); report TODO |
| Negative leave balances | CONFIG — `Employee Leave Balance Summary` report covers this today; dashboard chart + threshold TODO |
| Excessive overtime (BCEA: max 10h/week, 3h/day, total 45h/week) | MISSING — Attendance + overtime data exist, but the BCEA-compliance calculation doesn't |

---

## 5. Dashboard Visuals

| Chart | Status |
|---|---|
| Total Payroll Cost (monthly) | EXISTS — `payroll/dashboard_chart/outgoing_salary` |
| Departmental Payroll Breakdown | EXISTS — `department_wise_salary(last_month)` |
| Designation breakdown | EXISTS — `designation_wise_salary(last_month)` |
| Total PAYE Liability | SIMILAR-TEST — `Income Tax Deductions` report exists; SA-PAYE-specific version + chart TODO |
| Total UIF Contributions | MISSING — buildable now that UIF components are standardised |
| Total SDL Contributions | MISSING — buildable now that SDL component is standardised |
| Leave Liability (Provision) | MISSING — actuarial-style calc (balance × daily rate × employees) |
| Net Pay Distribution | EXISTS — `Salary Register` + `Salary Payments Based on Payment Mode` |

---

## 6. Automation Rules

| Rule | Status |
|---|---|
| PAYE follows SARS brackets | SIMILAR-TEST — slab shipped disabled; full calc with rebates TODO |
| UIF 1% capped at threshold | **DELIVERED** — formula on `UIF - Employee` component |
| SDL 1% employer | **DELIVERED** — formula on `SDL` statistical component |
| Earned leave 1.25/month | **DELIVERED** — `Annual Leave (SA)` configured for monthly accrual |
| Sick 30/36-month rolling | MISSING — see §3 |

---

## 7. Output Requirements

| Item | Status |
|---|---|
| Matrix layout / filtering | EXISTS — Report Builder + Query Reports |
| Export payslips monthly | EXISTS — Salary Slip print / email; HRMS has bank remittance & salary register reports |
| Drill-down per employee | EXISTS — Employee form + connections panel |
| Red compliance flags | MISSING — Number Cards + custom workspace with conditional styling |

---

## SARS statutory reports (implied but not in the HR Manager list)

All **MISSING** in upstream. These remain the real deliverables of `hrms_za`:

- **EMP201** — monthly PAYE/UIF/SDL submission
- **EMP501** — bi-annual reconciliation
- **IRP5 / IT3(a)** — annual employee tax certificates, with SARS source codes 3601 / 3605 / 3697 / 3698 etc.
- **UI-19** — UIF declaration
- **OID / Workmen's Comp W.As.8** — annual return of earnings

---

## Headline risks — still open

1. **PAYE with rebates + medical aid tax credits** — the single biggest correctness risk. The 2025/26 slab is in place as a reference, but a pure-slab evaluation will over-tax every employee. Budget a regression suite against published SARS worked examples before any payroll run.
2. **36-month rolling sick leave cycle** — Sick Leave (SA) is in place as a 30-day flat allocation so leave requests don't break; the rolling window must replace it before audit readiness.
3. **UIF ceiling is hardcoded at R17,712.** Must move into an `SA Payroll Settings` single doctype before the annual change so tenants can edit without touching code.
4. **2026/27 tax-year brackets not shipped.** Current tax year started 1 March 2026; verify SARS's Feb 2026 budget release and add a second Income Tax Slab record before running payroll for any month in 2026/27 or later.
5. **No UI-side "matrix dashboard" primitive in Frappe v16.** Delivery will be a Workspace with Number Cards + Dashboard Charts + a Query Report, plus custom CSS for red-flag styling. Not a single bespoke widget.
