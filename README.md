# hrms_za

South African localisation for Frappe HRMS v16.

Adds SARS / UIF / BCEA fields, salary components, leave types, and (eventually)
statutory reports (EMP201, EMP501, IRP5/IT3(a), UI-19, OID W.As.8).

## Status

Early scaffold — custom fields, fixtures, salary components and a PAYE
calculator for the current SARS tax year. Statutory reports and advanced
leave cycles are still on the roadmap (see "Known gaps" below).

## Install

Custom apps on a Frappe v16 containerized deployment are baked into a
layered image, not installed live.

1. Push this repo to GitHub (or a fork) and add its URL + branch to your
   `frappe_docker/apps.json`.
2. Rebuild the layered image. **Important:** pass
   `--no-cache-filter=builder` to `docker build`, otherwise BuildKit caches
   the builder step by instruction text and silently ignores `apps.json`
   changes.
3. Restart the stack, then:

```bash
docker exec -u frappe frappe-backend-1 \
    bench --site <your-site> install-app hrms_za
```

App install runs `after_install`, which calls the SA regional setup for every
Company where `country == "South Africa"`.

## What it ships

- Custom fields on `Employee` (SARS tax reference, SA ID, UIF contributor flag,
  UIF reference) and on `Company` (employer PAYE/UIF/SDL references).
- Employment Type fixtures (Permanent, Fixed Term, Temporary, Casual, Director,
  Independent Contractor, Learner).
- Leave Type fixtures (Annual 15d, Family Responsibility 3d, Sick 30d,
  Maternity 120d, Parental 10d) aligned to BCEA minimums.
- Salary components: UIF Employee (1% capped), UIF Employer (statistical),
  SDL (1% statistical), PAYE (placeholder — real calc coming).
- SA Income Tax Slab (2025/26) — **shipped disabled**; user must verify against
  SARS and enable, and add the current tax-year slab before running payroll.

## Known gaps (deferred)

- PAYE calc with primary/secondary/tertiary rebates and medical aid credits.
- 36-month rolling sick leave cycle (BCEA s22).
- ETI (Employment Tax Incentive).
- RA / pension tax-deductibility caps.
- SARS statutory reports.
- Overtime BCEA compliance report.
- Leave liability provision.
