# Laravel → Frappe — mental bridge

A reference map for navigating Frappe v16 with a Laravel mental model.

## Concept mapping

| Laravel | Frappe | Note |
|---|---|---|
| `app/Models/Employee.php` (Eloquent model) | `employee.py` (subclass of `frappe.model.document.Document`) | Business logic only. Schema lives elsewhere. |
| `database/migrations/*_create_employees_table.php` | `employee.json` (the DocType JSON) | **Declarative, not imperative.** You don't write `ALTER TABLE`. You edit the JSON; `bench migrate` diffs it against MariaDB and issues DDL for you. |
| `app/Http/Controllers/EmployeeController.php` | (mostly gone) | Replaced by auto-generated REST + `@frappe.whitelist()` functions for custom verbs. |
| `routes/web.php`, `routes/api.php` | Auto — no routing file | `/api/resource/Employee/<name>` = full CRUD. `/api/method/module.path.fn` = any whitelisted function. |
| Blade templates (`resources/views/employee.blade.php`) | Two worlds: **Desk** (auto-generated from JSON; you never write it) + Jinja `.html` (only for portal / print formats / website). | Desk is the magic — zero-HTML admin UI. |
| Form Request validation | `validate()` method on the Document class | Runs on every save. |
| Eloquent events (`saving`, `saved`, `deleted`) | Controller lifecycle: `before_insert`, `validate`, `before_save`, `on_submit`, `on_cancel`, `on_trash` | Same idea, richer vocabulary (submit/cancel comes from accounting). |
| Observers | `doc_events` in `hooks.py` | Lets your app intercept another app's doctype without editing it. Huge. |
| Policies / Gates | `permission_query_conditions` + `has_permission` hooks + Role Permissions DocType | Permissions are **data**, not code. |
| `artisan` | `bench` | Run inside the container on this host. |
| Seeders (`database/seeders`) | Fixtures (`<app>/fixtures/*.json`) or `after_install` code | |
| Tinker (`php artisan tinker`) | `bench --site X console` | Full Python REPL with `frappe` already imported. |
| `config/*.php` | `System Settings`, `<App> Settings` single-doctypes | Config is **data** in the DB, editable by admins. |
| `.env` | `common_site_config.json` + `site_config.json` | |
| Jobs / Queue | `frappe.enqueue()` + `scheduler_events` | Redis-backed. |
| Events / Listeners | Same — `doc_events` + signals | |
| `php artisan migrate` | `bench migrate` | |

## The "where do I look?" playbook

Laravel instinct: *model → migration → controller → route → view*. In Frappe, substitute:

1. **Schema & form layout** → `<doctype>.json`. Read this first. It's migration *and* form builder in one. You'll see every field, its type, and the form section it renders in.
2. **Business logic** → `<doctype>.py`. The Document class. Look for `validate()`, `before_save()`, `on_submit()`. That's where the "controller" code you're hunting for lives — triggered by lifecycle, not HTTP routes.
3. **Client-side behavior** → `<doctype>.js`. Form-level JS for the classic Desk (dynamic fields, fetch-from, custom buttons). You rarely need to touch this.
4. **Cross-doctype glue** → `hooks.py` at the app root. Every `doc_events`, scheduler cron, override, fixture, permission hook is declared here. The single file you `grep` when you ask *"where does X happen?"* and the answer isn't in the doctype.
5. **Custom API endpoints** → any function decorated with `@frappe.whitelist()`. Expose at `/api/method/<dotted.path>`. That's your `Route::post()` equivalent.

## The mindset shift

> In Laravel, **code defines the schema** (migrations) and **code defines the UI** (Blade).
> In Frappe, **JSON defines the schema** (DocType) and **Frappe generates the UI** automatically from it.

You stop writing CRUD — it just exists. Your code is only: validations, computed fields, lifecycle side-effects, and custom reports. That's why Frappe feels "complete" — 80% of what a Laravel app spends lines on is free.

## Custom Field — the "I want to extend a doctype" mechanism

Frappe splits **core doctype fields** (in `<doctype>.json` in the app source) from **Custom Fields** (rows in the `Custom Field` table).

| Aspect | Core field | Custom Field |
|---|---|---|
| Where defined | `employee.json` in the ERPNext source | Row in `tabCustom Field` |
| Who owns it | Upstream (Frappe / ERPNext team) | You / your app / your tenant |
| Survives `bench migrate`? | Overwritten from JSON on every migrate | Yes — it's data, migrate leaves data alone |
| Survives app upgrade? | Yes (it's theirs) | Yes (it's yours) |
| Visible on form | Always | Always — Frappe renders core + custom together |
| Stored in DB | Column on the doctype's table | Column on the doctype's table (Frappe's schema sync adds it) |

**Key trick:** at the SQL/UI layer they're indistinguishable. Frappe's meta layer merges core + custom at render time. Once added, your `sa_tax_reference` behaves exactly like the built-in `passport_number` — filterable, reportable, API-exposed, printable.

### Three ways to create one

1. **UI — Customize Form** (per-site, one-off, not reproducible).
2. **Fixtures** in `hooks.py` (works, but brittle — fixtures get stale).
3. **`create_custom_fields()` helper in code** ← the professional way. Declarative dict + idempotent upsert. This is what HRMS India uses for `pan_number`. `hrms_za` uses the same pattern for `sa_tax_reference`, `sa_id_number`, `uif_contributor`, etc.

```python
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

create_custom_fields({
    "Employee": [
        {"fieldname": "sa_tax_reference",
         "label":     "SARS Income Tax Number",
         "fieldtype": "Data",
         "insert_after": "payroll_cost_center"},
    ]
}, update=True)
```

Called from the regional `setup()` on app install and on `Company.country = "South Africa"` save.

## Quickest runtime introspection (when you're lost)

```bash
docker exec -it -u frappe frappe-backend-1 bench --site crm.hostedsip.co.za console
```

Then:

```python
# What fields are actually on Employee right now, core + custom?
[f.fieldname for f in frappe.get_meta("Employee").fields]

# What hooks does a given app declare?
frappe.get_hooks(app_name="hrms_za")

# Which doc_events fire on Employee?
frappe.get_hooks("doc_events").get("Employee")

# Full schema dump of a doctype
frappe.get_doc("DocType", "Employee").as_dict()
```

These four commands answer 90% of "where is this coming from?" questions.
