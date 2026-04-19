# hrms_za

South African localisation for Frappe HRMS v16.

Adds SARS / UIF / BCEA fields, salary components, leave types, and (eventually)
statutory reports (EMP201, EMP501, IRP5/IT3(a), UI-19, OID W.As.8).

## Status

Early scaffold. See `Evalution of HRMS 16.md` for the requirements-vs-existing matrix
and `INTEGRATION_MAP.md` for how this app plugs into HRMS + ERPNext.

## Install (on this host)

Custom apps are baked into the layered container image, not installed live.

1. Push this repo to GitHub and add its URL + branch to `~/frappe_docker/apps.json`.
2. Rebuild the image with `--no-cache-filter=builder` (see `docker-deployment.md`).
3. Restart the stack, then:

```bash
docker exec -u frappe frappe-backend-1 \
    bench --site crm.hostedsip.co.za install-app hrms_za
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

## Known gaps (deferred, see Evalution of HRMS 16.md)

- PAYE calc with primary/secondary/tertiary rebates and medical aid credits.
- 36-month rolling sick leave cycle (BCEA s22).
- ETI (Employment Tax Incentive).
- RA / pension tax-deductibility caps.
- SARS statutory reports.
- Overtime BCEA compliance report.
- Leave liability provision.
