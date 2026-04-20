# Leave Accrual & Sick-Leave Cycle — Decisions for HR to Review

**Purpose:** This is the plain-English companion to the technical spec. It describes the **policy decisions** the system will make on your behalf, so you can smell-test the logic before we write code. If something here feels wrong, flag it — it's much cheaper to fix now than after it's built.

**Companion technical spec:** `2026-04-20-sa-leave-accrual-design.md` (for engineering review).

**Date:** 2026-04-20.

---

## What this document is for

The platform will enforce some opinions automatically — who gets what leave, when it expires, what happens at termination. You wrote the business rules for this in the original HR feedback; we've translated them into a system design. This doc plays the rules back to you in scenarios.

**How to use this doc:** read each section and ask "would this be OK at Acme?" If yes, sign off. If something smells wrong — even if you can't articulate why — flag it. That smell is usually right.

Each section ends with a **"Confirm?"** prompt. We need a yes on all of them before code is written.

---

## The five decisions we're proposing

### Decision 1 — Annual leave accrues monthly, not upfront

**What the system will do:** When an employee joins, their Annual Leave balance starts at **zero**. Each month, the system adds roughly 1.25 days to their balance (15 days per year ÷ 12). After 12 months of employment, they've accumulated the full 15 days.

**What this prevents:** An employee who joins in January taking all 15 days of leave in February, then resigning in March. Under monthly accrual, at the end of February they've earned only ~2.5 days, so the system won't let them take 15.

**What this means in practice:**

- Month 1: earn 1.25 days.
- Month 4: earn another 1.25, balance accumulates to 5 days (assuming none taken).
- Month 12: balance is 15 days (full annual entitlement).
- If the employee takes 5 days in month 4 and resigns in month 7: they earned 7 × 1.25 = 8.75 days; they took 5; they're paid out for 3.75 days on exit. Fair.

**Alternative we rejected:** Allocating all 15 days upfront on Jan 1 (which is what the Phase 1 version does). This exposes the company to paying out leave that hasn't been earned.

**Confirm?** Yes / No — is monthly accrual what you want?

---

### Decision 2 — Sick leave runs on 36-month cycles from the employee's start date

**What the Act says:** BCEA s22 gives every employee **30 days of paid sick leave per 36-month cycle**. The cycle starts when they begin employment (or when their previous cycle ends). For someone with a 5-day workweek, that's the legal minimum.

**What the system will do:** On the employee's first day, create a bucket of 30 sick days that's usable for 36 months. When that cycle ends, automatically create a fresh bucket of 30 for the next 36 months. And so on.

**Example — Thandi joined 1 May 2023:**

- Cycle 1: 1 May 2023 → 30 April 2026. 30 days available.
- Cycle 2: 1 May 2026 → 30 April 2029. Fresh 30 days.
- Cycle 3: 1 May 2029 → 30 April 2032. Fresh 30 days.

**This is per-employee.** Thandi and Siyabonga, who joined at different times, have different cycle boundaries. There's no "everyone's sick leave resets in January" event — each employee ticks over on their own DOJ anniversary.

**Alternative we rejected:** A company-wide sick leave cycle aligned to the calendar year. This is legally incorrect under BCEA, which is explicit that the cycle is per-employee.

**Confirm?** Yes / No — do you understand and accept that sick-leave rollovers happen on each employee's own schedule, not on a company-wide date?

---

### Decision 3 — Unused sick days at cycle end expire ("use or lose")

**What happens if Thandi uses only 22 of her 30 sick days in Cycle 1 (1 May 2023 → 30 April 2026)?**

On 1 May 2026, her Cycle 1 bucket closes. The 8 unused days are gone. She starts Cycle 2 with a fresh 30 days — not 38.

**What if she gets sick on day 29 of Cycle 1?**

Paid sick leave, as expected. If she's sick on day 31, that day is unpaid (or HR converts it to annual leave / unpaid absence — HR's call, per the Act).

**Why:** BCEA does not require employers to carry unused sick days forward. Standard SA practice is "use or lose". Carrying them forward would mean a 10-year veteran has potentially 100+ sick days stockpiled — not what the Act intends.

**What the system won't do:** automatically convert expired sick days to annual leave, cash, or anything else. They simply disappear at cycle end.

**Confirm?** Yes / No — is "use or lose" the right policy for Acme?

---

### Decision 4 — Termination automatically drafts a leave payout

**What the Act says:** BCEA s40 requires that on termination, accrued unused **annual** leave is paid out in cash. (Sick leave is not paid out — it was always contingent on actually being sick.)

**What the system will do:** When HR submits an Employee Separation record (or changes an employee's status to "Left"), the system automatically:

1. Looks at the employee's current Annual Leave balance on their last day.
2. Creates a **draft** Leave Encashment document (not submitted — HR reviews first).
3. The draft is pre-filled with: days owed × the employee's daily rate (pulled from their Salary Structure).
4. HR reviews, tweaks the daily rate if needed (the rate may need to include BCEA s35 items like housing or transport allowances that aren't in the basic rate), and submits.

**Example — Thandi resigns, last day 30 June 2027, balance is 4.5 days:**

- System drafts: 4.5 days × R850/day = R3,825.00.
- HR reviews. If Thandi's proper s35 daily rate is R950 (including allowances), HR edits to R4,275.00 and submits.
- The encashment flows into her Full & Final Statement automatically.

**Safety net:** If anything goes wrong (missing daily rate, Salary Structure problem), the system records a note on Thandi's record and does nothing else. HR can then click a "Generate Termination Encashment" button to retry once the problem is fixed.

**Control:** There's a knob to turn this off. If HR prefers to manually trigger encashment every time (rather than have the system do it on Separation submit), flip the knob and click the button instead.

**What the system won't do:** pay out **sick** leave. Under BCEA s40, only annual leave is encashable on termination.

**Confirm?** Yes / No — auto-draft on Separation submit, with manual fallback?

---

### Decision 5 — First 6 months of employment: we're giving MORE than the Act requires

**What the Act says:** BCEA s22(3) has a special rule for the **first 6 months** of employment: during that window, the employee is entitled to 1 day of sick leave per 26 days worked (not the full 30-day Cycle 1 bucket). And s22(4) lets the employer deduct s22(3) days from the Cycle 1 total.

**What we've decided:** **ignore this rule**. Employees can draw from the full 30-day Cycle 1 bucket from day 1. This is more generous than the Act requires.

**Why:**

- It's legally defensible — you're exceeding the minimum.
- It avoids wiring the system to track "days worked" via Attendance, which is a separate can of worms.
- "New employee gets sick in their first month, we paid them for it" is a better look than "we fought them for 3 days until they'd worked 78 days".

**The risk we accept:** Someone could join, call in sick for 30 days in their first 6 months, then resign. Under strict BCEA, they'd only have been entitled to ~6 days of paid sick leave (6 months × ~26 working days ÷ 26 per day). We've paid them 30.

**Mitigation:** The `applicable_after` knob lets HR set "no leave can be taken in the first N working days" (default 0). If you want to require, say, 30 working days before any leave can be taken, we can set that. It's a blunt instrument — all-or-nothing, not a graduated cap — but it's there.

**Confirm?** Yes / No — give new employees full access to Cycle 1 from day 1?

---

## Knobs HR can turn (summary)

These are configurable on the "SA Leave Settings" form. Each ships with a default; HR adjusts as policy evolves.

| Knob | Default | What it does |
|---|---|---|
| Cycle start (month/day) | 1 January | When the annual leave cycle starts company-wide |
| Sick cycle length | 36 months | BCEA default, usually don't change |
| Sick days per cycle | 30 | BCEA 5-day-week default; raise for a 6-day-week company |
| Annual leave carry-forward max | 5 days | Max unused annual leave that rolls to next year |
| Enforce sick cycle cap | On | If off, sick leave can go negative; HR reconciles manually |
| Auto-create encashment on termination | On | If off, HR clicks the button manually |
| Annual leave applicable after | 0 days | New-employee gating; 0 = available from day 1 |
| Low-balance email threshold | 3 days | Employees with less than this get a nudge email |

---

## Scenarios to sanity-check

Read these and ask "would the outcome here cause a problem at Acme?"

### Scenario A — The new hire who wants a week off

Lerato starts 1 June 2026. On 1 October 2026, she asks for 5 days off.

- Her Annual Leave balance on 1 October: 4 months × 1.25 = 5 days.
- The application succeeds — she's earned exactly what she's asking for.
- Her balance after leave: 0 days.
- She earns another 1.25 in November, another in December, so by year-end she's at 2.5 days.

Outcome: she got her week off, within what she'd earned. The company paid her for leave she actually accrued.

### Scenario B — The mid-term resignation

Siyabonga joins 1 March 2026, takes 5 days in June, resigns 30 September 2026.

- He earned: 7 months × 1.25 = 8.75 days.
- He took: 5 days.
- Final balance: 3.75 days.
- On Separation submit, the system drafts a Leave Encashment for 3.75 × his daily rate.
- HR reviews, adjusts rate for s35 if needed, submits. Payroll processes it.

### Scenario C — The long-tenured employee

Nomvula has worked at Acme since 2018. On 1 May 2027, her Cycle 4 sick-leave bucket closes.

- She used 18 of 30 in Cycle 4. 12 unused days disappear.
- Cycle 5 starts 2 May 2027 with a fresh 30 days.
- She sees on her ESS page: "Current Cycle: Cycle 5 of Your Employment. 30 days available. Cycle ends 1 May 2030."

No calendar-year "reset event" for the company. Each veteran employee has their own cycle boundary. HR gets a live dashboard showing who's in which cycle, not an annual wrap-up report.

### Scenario D — The chronic sick caller

Patrick has used 28 of his 30 Cycle 1 sick days by month 30 (out of 36). He then applies for 5 more days. The system blocks the application: "Insufficient sick leave balance (2.0 days available)."

- HR's options: (a) let him take the remaining 2 paid + 3 unpaid; (b) let him use annual leave for the other 3; (c) investigate whether there's a PILIR / temporary incapacity / medical review situation.
- If HR wants the system to stop blocking (i.e. let sick balance go negative and let HR reconcile on payroll), they flip the "enforce sick cycle cap" knob off. Then Patrick's 5-day application succeeds and his balance becomes -3.

Outcome: HR stays in control. The system enforces the rule by default but gets out of the way when HR wants it to.

---

## What we're explicitly NOT building in this phase

- **Automatic checking of sick notes / medical certificates.** System doesn't know whether an application for >2 consecutive sick days has a medical certificate attached. HR still reviews.
- **Sick leave during maternity / parental leave overlap.** If an employee is on maternity and falls ill, HRMS's existing leave-overlap logic handles it, but the edge cases are not custom-built. HR handles unusual cases manually.
- **Encashment mid-employment** (paying out unused leave without resigning). If Acme wants to buy back leave annually, that's a separate feature. The system only triggers encashment on termination.
- **Per-day-worked accrual tied to Attendance.** Monthly accrual is based on calendar months, not actual days worked. If an employee takes 3 weeks of unpaid leave, they still earn 1.25 days that month.
- **Two-step approval for large requests.** Phase 1 reserved a knob for "leave requests >10 days need two approvers" — it's not wired yet. Phase 3.
- **Anniversary-year sick cycle reporting.** If Acme's auditor asks "how many sick days did all employees take in 2027", the answer requires a custom report. The system shows per-employee per-cycle data natively; aggregate-by-calendar-year needs a report.

---

## Questions for HR before we build

Please confirm each of the five decisions above with a yes/no. On any "no", please tell us what you'd want instead — we can still re-open the design.

Also:

- **Any BCEA exposure we've missed?** Is there a specific Labour Relations Act or bargaining-council condition at your tenant (e.g. MEIBC, MIBCO, NBC) that imposes stricter minimums than BCEA?
- **Typical daily-rate computation.** When HR currently computes leave encashment manually, do they use basic salary only, or basic + allowances (s35 "remuneration")? The system's default is whatever is on the Salary Structure — confirm that matches your manual process.
- **Carry-forward max — is 5 the right default?** Some companies cap at 10 or 20; some don't cap at all. Your current policy may differ.
- **Leave during probation.** Is there a specific policy ("no leave in first 90 days" or similar)? If yes, what value should `annual_leave_applicable_after_days` be set to?

---

## Sign-off

Once all five decisions have a yes and the questions above have answers, engineering will:

1. Finalise the technical spec.
2. Write an implementation plan.
3. Build against the plan with tests.
4. Deploy to `crm.hostedsip.co.za` for live verification.
5. Leave it running for 2 weeks to gather real usage data before starting Phase 1b (dashboard tiles).

If you have questions that need a verbal walkthrough — paid scenarios, sample encashment letters, the math of monthly accrual — please say so. Getting this right once is much faster than patching it after launch.
