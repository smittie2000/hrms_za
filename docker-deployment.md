# Docker deployment — Frappe v16 stack (erpnext + hrms + crm + helpdesk)

Host: Ubuntu 24.04 VM, `/home/frappeadmin`. Deployed via `easy-install.py` (frappe_docker). Single site `crm.hostedsip.co.za`.

> **Who this is for.** Operator rebuilding or redeploying this stack. Includes the non-obvious failure modes we have already hit.

---

## 1. Inventory — where things live

| Thing | Path |
|---|---|
| frappe_docker clone | `~/frappe_docker/` |
| Custom apps manifest | `~/frappe_docker/apps.json` |
| Layered Containerfile | `~/frappe_docker/images/layered/Containerfile` |
| Generated compose file (in use) | `~/frappe-compose.yml` |
| Environment file (in use) | `~/frappe.env` |
| Custom image tag | `frappe-custom:v16` |
| Compose project name | `frappe` |

The **generated** compose file at `~/frappe-compose.yml` is what's actually running — not the template at `~/frappe_docker/compose.yaml`. `easy-install.py` renders the generated file from the template plus overrides. Edit the generated file directly only if you're sure you won't re-run easy-install.

Named volumes managed by compose: `frappe_sites`, `frappe_db-data`, `frappe_redis-queue-data`, `frappe_cert-data`.

MariaDB root password is **hard-coded in `~/frappe-compose.yml`** (`MYSQL_ROOT_PASSWORD: <pw>` on the `db` service), not in `frappe.env`. When creating sites, read it from the compose file.

---

## 2. apps.json

Current contents:

```json
[
  { "url": "https://github.com/frappe/erpnext",   "branch": "version-16" },
  { "url": "https://github.com/frappe/hrms",      "branch": "version-16" },
  { "url": "https://github.com/frappe/crm",       "branch": "main" },
  { "url": "https://github.com/frappe/telephony", "branch": "develop" },
  { "url": "https://github.com/frappe/helpdesk",  "branch": "main" }
]
```

- `telephony` is a runtime dependency of HRMS — keep it.
- When switching HRMS to the SA fork, change the hrms entry's `url` only; keep `"branch": "version-16"`.

---

## 3. Building the custom image

Canonical frappe_docker build command plus our two local conventions (`--no-cache-filter=builder` and pinning Python 3.14 / Node 24):

```bash
cd ~/frappe_docker

docker build \
  --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \
  --build-arg=FRAPPE_BRANCH=version-16 \
  --build-arg=PYTHON_VERSION=3.14 \
  --build-arg=NODE_VERSION=24 \
  --secret=id=apps_json,src=apps.json \
  --no-cache-filter=builder \
  --tag=frappe-custom:v16 \
  --file=images/layered/Containerfile .
```

Build time on this VM: ~12 minutes cold (`#7` app install ~8 min, `#8` asset bundle ~1 min, final export ~3 min).

**Gotcha — BuildKit secret cache.** `--secret=id=apps_json` mounts `apps.json` as a build secret. BuildKit caches the builder `RUN` by its instruction text only — not by the secret's bytes. So **editing `apps.json` without `--no-cache-filter=builder` is silently ignored**: the cached layer runs again against the old file. Always include `--no-cache-filter=builder` when rebuilding after an apps.json change. (Ref: memory `feedback_frappe_docker_buildkit_secret_cache`.)

**Gotcha — do NOT pass `apps.json` as `--build-arg`.** Build args are permanently visible via `docker image history`. Always use `--secret=id=apps_json,src=apps.json`.

---

## 4. The assets-volume gotcha (most important)

**Symptom:** after rebuilding the image with a new/updated app in apps.json and bringing the stack back up, the new app's UI renders with **missing icons and unstyled elements**. The app shows as installed and its DocTypes work, but `/assets/<app>/...` serves stale or missing files.

**Cause.** The layered `Containerfile` declares:

```dockerfile
VOLUME [
  "/home/frappe/frappe-bench/sites",
  "/home/frappe/frappe-bench/sites/assets",   # problem
  "/home/frappe/frappe-bench/logs"
]
```

`~/frappe-compose.yml` only binds a **named** volume `sites` → `/home/frappe/frappe-bench/sites`. For the other two VOLUME paths, Docker creates **anonymous** volumes (random UUID names). Those anonymous volumes are populated **once** with the image's contents the first time the container starts, and **persist thereafter**. On every subsequent `compose up` with a new image, Docker re-attaches the stale anonymous volume, which **shadows** the fresh assets baked into the new image. The image has `hrms.bundle.QS2GRVNQ.js` in the layer; the running container sees whatever was there on day one.

The official frappe_docker docs do not address this — it's a gap, not a misuse.

**Two remediation paths:**

### 4a. Nuke and rebuild fresh (current approach)

Safe when there's no data to preserve. Removes every volume including the database.

```bash
docker compose -f ~/frappe-compose.yml --env-file ~/frappe.env down -v --remove-orphans
docker volume prune -af   # mops up any stray anonymous volumes
docker image rm frappe-custom:v16 || true

# rebuild (section 3)
# bring up (section 5)
# new-site (section 6)
```

### 4b. Targeted volume removal (preserves DB + sites)

When you want to ship asset updates without wiping `crm.hostedsip.co.za`.

```bash
# find the anonymous assets volumes (one per service using the image — backend, frontend, workers, scheduler)
docker inspect $(docker ps -aq --filter label=com.docker.compose.project=frappe) \
  | python3 -c 'import json,sys; [print(m["Name"]) for c in json.load(sys.stdin) for m in c["Mounts"] if m.get("Destination")=="/home/frappe/frappe-bench/sites/assets" and m.get("Type")=="volume"]' \
  | sort -u

docker compose -f ~/frappe-compose.yml --env-file ~/frappe.env down
# rebuild (section 3) — do this BEFORE removing volumes or the image pull refs fail
docker volume rm <each-assets-volume-uuid>
docker compose -f ~/frappe-compose.yml --env-file ~/frappe.env up -d
```

After `up`, Docker recreates the anonymous volumes empty, then populates them from the new image. `frappe_sites` (site config, site-files, backups) is untouched.

### 4c. Permanent fix (recommended, not yet applied)

Remove `/home/frappe/frappe-bench/sites/assets` (and ideally `/home/frappe/frappe-bench/logs`) from the `VOLUME` declaration in `images/layered/Containerfile`. Assets are baked at build time and don't need to persist across container lifetimes — they should come from the image layer every rebuild. This requires one **final** run of 4b to clear the legacy anonymous volumes; all subsequent rebuilds are clean.

---

## 5. Bringing the stack up

```bash
docker compose -f ~/frappe-compose.yml --env-file ~/frappe.env up -d
```

Expected startup sequence: `db` → healthy → `configurator` runs once and exits 0 → `backend` / `queue-*` / `scheduler` / `websocket` → `frontend` → `cron`.

Verify:

```bash
docker ps --format '{{.Names}}\t{{.Status}}'
curl -sI -H "Host: crm.hostedsip.co.za" http://127.0.0.1/login    # expect 308 → https
```

Traefik owns ports 80/443. Nothing else may bind them.

---

## 6. Creating the site and installing apps

```bash
DB_ROOT_PASS=$(grep -E '^\s*MYSQL_ROOT_PASSWORD:' ~/frappe-compose.yml | awk '{print $2}')
ADMIN_PASS=$(grep '^SITE_ADMIN_PASS=' ~/frappe.env | cut -d= -f2)

docker exec -u frappe frappe-backend-1 bench new-site crm.hostedsip.co.za \
  --mariadb-user-host-login-scope='%' \
  --db-root-username=root \
  --db-root-password="$DB_ROOT_PASS" \
  --admin-password="$ADMIN_PASS" \
  --install-app erpnext \
  --install-app hrms \
  --install-app crm \
  --install-app helpdesk \
  --set-default

docker exec -u frappe frappe-backend-1 bench --site crm.hostedsip.co.za enable-scheduler
```

Notes:
- `--mariadb-user-host-login-scope='%'` is required because backend and db are on different docker network hosts.
- `telephony` is installed automatically as an HRMS dependency — do **not** pass `--install-app telephony`.
- **Scheduler is disabled by default on fresh sites.** Enable it explicitly.
- Browser hard-refresh (Ctrl+Shift+R) is needed the first time to bust the app-shell cache.

---

## 7. Post-install verification checklist

```bash
# apps installed on the site
docker exec -u frappe frappe-backend-1 bench --site crm.hostedsip.co.za list-apps

# asset bundles registered — look for hrms.bundle.js, hrms.bundle.css, erpnext.bundle.*
docker exec -u frappe frappe-backend-1 cat /home/frappe/frappe-bench/sites/assets/assets.json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); [print(f"  {k} -> {v}") for k,v in sorted(d.items()) if any(x in v for x in ["/hrms/","/erpnext/"])]'
```

Expected `list-apps` output (versions as of 2026-04-19): frappe 16.15.0, erpnext 16.14.0, hrms 16.5.0, crm 1.68.0, telephony 0.0.1, helpdesk 1.22.1.

Expected assets.json entries for HRMS: `hrms.bundle.js`, `hrms.bundle.css`, `hierarchy-chart.bundle.js`, `interview.bundle.js`, `performance.bundle.js`.

**crm and helpdesk do NOT appear in `assets.json`** — they're Frappe-UI Vue SPAs served under their own routes (`/crm`, `/helpdesk`) and don't register `app_include_js` hooks. Don't chase this as a bug.

---

## 8. Other gotchas

- **`bench build` (no `--app`) OOM-kills** on this VM (exit 137) at the final Vite step. Either build per-app:
  ```bash
  docker exec -u frappe frappe-backend-1 bench build --app hrms
  docker exec -u frappe frappe-backend-1 bench build --app crm
  docker exec -u frappe frappe-backend-1 bench build --app helpdesk
  ```
  or accept the partial manifest update the all-apps run leaves behind before it OOMs (most bundles get written; the crash happens late). For clean full rebuilds, bump container memory or just rebuild the image (section 3).
- **Never `timedatectl set-timezone` on this host.** Frappe stores UTC; changing the OS zone causes double-offset display bugs. OS stays on UTC always.
- **Do not edit files inside running containers** for anything you want to persist — all app code is baked at image build. Runtime edits vanish on `compose down && up` with a new image.
- **Do not run `bench` on the host** — there is no host bench. All bench invocations go through `docker exec -u frappe frappe-backend-1 bench …`.
- **Container name prefixes can change.** Before piping exec output anywhere, verify with `docker ps --format '{{.Names}}'`.
- **Logs volume is also anonymous** — same volume-shadow class of problem, but log staleness is usually self-healing because logs rotate. Lower priority than assets.

---

## 9. Troubleshooting — icons / styling missing after rebuild

1. Confirm the app is actually installed: `bench --site <site> list-apps`.
2. Check `assets.json`: does it map `<app>.bundle.js` → `/assets/<app>/dist/js/…`?
   - If the key is missing entirely → bundle wasn't built. Run `bench build --app <app>`.
   - If the key is present but points at a file that doesn't exist on disk → stale anonymous volume. Apply section 4b.
3. Verify the dist directory inside the container: `ls /home/frappe/frappe-bench/sites/assets/<app>/dist/{js,css}/`.
4. Verify the image layer's dist directory matches:
   ```bash
   docker run --rm --entrypoint ls frappe-custom:v16 /home/frappe/frappe-bench/sites/assets/<app>/dist/js/
   ```
   If image dist ≠ container dist → anonymous volume is shadowing the image. Apply section 4b.
5. Hard-refresh the browser after any of the above.

---

## 10. Reference — minimum clean-rebuild sequence

For when something is broken enough that you want to start over (no data to preserve):

```bash
docker compose -f ~/frappe-compose.yml --env-file ~/frappe.env down -v --remove-orphans
docker volume prune -af
docker image rm frappe-custom:v16 || true

cd ~/frappe_docker && docker build \
  --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \
  --build-arg=FRAPPE_BRANCH=version-16 \
  --build-arg=PYTHON_VERSION=3.14 \
  --build-arg=NODE_VERSION=24 \
  --secret=id=apps_json,src=apps.json \
  --no-cache-filter=builder \
  --tag=frappe-custom:v16 \
  --file=images/layered/Containerfile .

docker compose -f ~/frappe-compose.yml --env-file ~/frappe.env up -d

DB_ROOT_PASS=$(grep -E '^\s*MYSQL_ROOT_PASSWORD:' ~/frappe-compose.yml | awk '{print $2}')
ADMIN_PASS=$(grep '^SITE_ADMIN_PASS=' ~/frappe.env | cut -d= -f2)
docker exec -u frappe frappe-backend-1 bench new-site crm.hostedsip.co.za \
  --mariadb-user-host-login-scope='%' \
  --db-root-username=root --db-root-password="$DB_ROOT_PASS" \
  --admin-password="$ADMIN_PASS" \
  --install-app erpnext --install-app hrms --install-app crm --install-app helpdesk \
  --set-default
docker exec -u frappe frappe-backend-1 bench --site crm.hostedsip.co.za enable-scheduler
```

~15 minutes end-to-end on this VM.
