#!/usr/bin/env bash
#
# redeploy.sh — rebuild the frappe_docker layered image with hrms_za baked in,
# rotate the stale anonymous /assets volumes, restart the stack, and migrate
# the site. Preserves the named volumes that hold DB + site files.
#
# Runs end-to-end without manual intervention, safe to re-run.
#
# ─────────────────────────────────────────────────────────────────────────
# Prerequisites (one-time per host)
#   - frappe_docker cloned to $FRAPPE_DOCKER_DIR (default: ~/frappe_docker)
#   - apps.json in that directory includes an entry for hrms_za (or the fork
#     you're deploying) on the target branch
#   - Rendered compose file + .env file in standard locations (see vars below)
#   - docker + python3 on the host
#
# Required environment
#   SITE                 Frappe site name, e.g. "crm.example.co.za"
#
# Optional environment (sensible defaults shown)
#   FRAPPE_DOCKER_DIR    ~/frappe_docker
#   COMPOSE_FILE         ~/frappe-compose.yml
#   ENV_FILE             ~/frappe.env
#   IMAGE_TAG            frappe-custom:v16
#   PROJECT              frappe              (compose project name)
#   FRAPPE_BRANCH        version-16
#   PYTHON_VERSION       3.14
#   NODE_VERSION         24
#   SKIP_BUILD           set to 1 to skip the image rebuild (fast-path when
#                        only the volume rotation / migrate is needed)
#
# Usage
#   SITE=crm.example.co.za ./redeploy.sh
#
# Exit codes
#   0  redeploy complete, smoke checks passed
#   1  build failed — tail the log noted in the output
#   2  preflight failure — referenced file missing
#   3  smoke check failed after redeploy
# ─────────────────────────────────────────────────────────────────────────

set -euo pipefail

: "${SITE:?SITE env var is required (e.g. crm.example.co.za)}"

FRAPPE_DOCKER_DIR="${FRAPPE_DOCKER_DIR:-$HOME/frappe_docker}"
COMPOSE_FILE="${COMPOSE_FILE:-$HOME/frappe-compose.yml}"
ENV_FILE="${ENV_FILE:-$HOME/frappe.env}"
IMAGE_TAG="${IMAGE_TAG:-frappe-custom:v16}"
PROJECT="${PROJECT:-frappe}"
FRAPPE_BRANCH="${FRAPPE_BRANCH:-version-16}"
PYTHON_VERSION="${PYTHON_VERSION:-3.14}"
NODE_VERSION="${NODE_VERSION:-24}"
BACKEND="${PROJECT}-backend-1"
LOG="/tmp/hrms_za_rebuild.log"
BACKUP_DIR="${BACKUP_DIR:-$HOME/frappe-backups}"

say() { printf '\n=== %s ===\n' "$*"; }
fail() { echo "FAIL: $*" >&2; exit "${2:-1}"; }

# ─── Preflight ──────────────────────────────────────────────────────────
[ -f "$FRAPPE_DOCKER_DIR/apps.json" ] || fail "apps.json missing at $FRAPPE_DOCKER_DIR/apps.json" 2
[ -f "$COMPOSE_FILE" ]                 || fail "compose file missing at $COMPOSE_FILE" 2
[ -f "$ENV_FILE" ]                     || fail "env file missing at $ENV_FILE" 2
command -v docker  >/dev/null          || fail "docker not on PATH" 2
command -v python3 >/dev/null          || fail "python3 not on PATH" 2

# ─── 1. Rebuild image ───────────────────────────────────────────────────
if [ "${SKIP_BUILD:-0}" != "1" ]; then
    say "1/5  Rebuild $IMAGE_TAG  (log: $LOG)"
    if ! ( cd "$FRAPPE_DOCKER_DIR" && docker build \
            --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \
            --build-arg=FRAPPE_BRANCH="$FRAPPE_BRANCH" \
            --build-arg=PYTHON_VERSION="$PYTHON_VERSION" \
            --build-arg=NODE_VERSION="$NODE_VERSION" \
            --secret=id=apps_json,src=apps.json \
            --no-cache-filter=builder \
            --tag="$IMAGE_TAG" \
            --file=images/layered/Containerfile . > "$LOG" 2>&1
       ); then
        echo "Last 40 lines of $LOG:"
        tail -40 "$LOG"
        fail "docker build failed" 1
    fi
    echo "build OK"

    if ! docker run --rm --entrypoint /bin/bash "$IMAGE_TAG" \
            -c 'ls /home/frappe/frappe-bench/apps/' 2>/dev/null | grep -q '^hrms_za$'; then
        fail "hrms_za not present in $IMAGE_TAG — check apps.json and $LOG" 1
    fi
    echo "hrms_za present in image"
else
    say "1/5  SKIP_BUILD=1 — reusing existing $IMAGE_TAG"
fi

# ─── 1b. Snapshot site_config.json BEFORE touching the stack ───────────
# encryption_key lives in this file. Losing it = every stored credential
# (email passwords, OAuth, LDAP, social login) becomes undecipherable.
if docker ps --format '{{.Names}}' | grep -q "^${BACKEND}$"; then
    mkdir -p "$BACKUP_DIR"
    SNAPSHOT="$BACKUP_DIR/site_config.${SITE}.$(date +%Y%m%dT%H%M%S).json"
    if docker exec -u frappe "$BACKEND" cat "sites/${SITE}/site_config.json" > "$SNAPSHOT" 2>/dev/null \
       && python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$SNAPSHOT" 2>/dev/null; then
        echo "site_config snapshot: $SNAPSHOT"
    else
        rm -f "$SNAPSHOT"
        echo "WARN  could not snapshot site_config.json — continuing"
    fi
fi

# ─── 2. Capture stale anonymous /assets volumes ─────────────────────────
# Must be done BEFORE `compose down` — once containers are removed, the
# mount info goes with them.
say "2/5  Enumerate stale anonymous /assets volumes"
running_ids=$(docker ps -aq --filter label=com.docker.compose.project="$PROJECT" || true)
if [ -z "$running_ids" ]; then
    STALE_VOLS=""
    echo "No containers found for project '$PROJECT' — first run?"
else
    STALE_VOLS=$(docker inspect $running_ids 2>/dev/null \
      | python3 -c 'import json,sys
data = json.load(sys.stdin)
out = set()
for c in data:
    for m in c.get("Mounts", []):
        if m.get("Destination") == "/home/frappe/frappe-bench/sites/assets" and m.get("Type") == "volume":
            out.add(m["Name"])
for n in sorted(out):
    print(n)')
    if [ -z "$STALE_VOLS" ]; then
        echo "No stale /assets volumes found (fresh stack or already rotated)."
    else
        echo "$STALE_VOLS"
    fi
fi

# ─── 3. Down + rm stale volumes + up ────────────────────────────────────
say "3/5  Down + rm /assets volumes + up"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down
if [ -n "$STALE_VOLS" ]; then
    # shellcheck disable=SC2086
    docker volume rm $STALE_VOLS
fi
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

# Wait for backend to answer bench commands
printf "waiting for backend"
for _ in $(seq 1 40); do
    if docker exec -u frappe "$BACKEND" bench --site "$SITE" list-apps >/dev/null 2>&1; then
        echo " ready"
        break
    fi
    printf "."
    sleep 3
done

# ─── 3b. Assert encryption_key survived the restart ─────────────────────
# If `up` started with an empty sites volume, Frappe auto-generates a new
# key on first request and silently orphans every previously-stored
# credential. Abort loudly before migrate rather than discover it later.
KEY_NOW=$(docker exec -u frappe "$BACKEND" python3 -c \
    "import json; print(json.load(open('sites/${SITE}/site_config.json')).get('encryption_key',''))" 2>/dev/null || true)
if [ -z "$KEY_NOW" ]; then
    fail "encryption_key missing from site_config.json on $SITE — aborting before migrate" 2
fi
if [ -n "${SNAPSHOT:-}" ] && [ -f "$SNAPSHOT" ]; then
    KEY_WAS=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('encryption_key',''))" "$SNAPSHOT" 2>/dev/null || true)
    if [ -n "$KEY_WAS" ] && [ "$KEY_NOW" != "$KEY_WAS" ]; then
        fail "encryption_key rotated during redeploy — stored credentials will not decrypt. Restore from $SNAPSHOT before continuing" 2
    fi
fi
echo "encryption_key preserved"

# ─── 4. Migrate + clear-cache ───────────────────────────────────────────
say "4/5  Migrate + clear-cache"
docker exec -u frappe "$BACKEND" bench --site "$SITE" migrate
docker exec -u frappe "$BACKEND" bench --site "$SITE" clear-cache

# ─── 5. Smoke checks ────────────────────────────────────────────────────
say "5/5  Smoke checks"
rc=0
if docker exec -u frappe "$BACKEND" bench --site "$SITE" list-apps | grep -q '^hrms_za'; then
    echo "PASS  hrms_za installed on $SITE"
else
    echo "FAIL  hrms_za not installed on $SITE"
    echo "      run: docker exec -u frappe $BACKEND bench --site $SITE install-app hrms_za"
    rc=3
fi

status=$(curl -skI -H "Host: $SITE" https://127.0.0.1/app/sa-payroll 2>/dev/null | head -1 | awk '{print $2}')
case "$status" in
    200|301|302) echo "PASS  /app/sa-payroll route resolves ($status)" ;;
    *)           echo "FAIL  /app/sa-payroll returned: ${status:-<empty>}"; rc=3 ;;
esac

if [ "$rc" -eq 0 ]; then
    say "Redeploy complete"
else
    exit "$rc"
fi
