#!/usr/bin/env bash
# Ubuntu single-VM deployment. Copy this file and the Windows-built zip to the VM.
set -Eeuo pipefail
umask 077

APP=/opt/pms-platform
CONFIG=/etc/pms-platform
BACKUPS=/var/backups/pms-platform
SITE=/etc/nginx/sites-available/pms-platform.conf
SITE_LINK=/etc/nginx/sites-enabled/pms-platform.conf
ACME_ROOT=/var/www/pms-platform-acme
SERVICE_USER=pmsplatform
MEDIA_GROUP=pmsmedia
MEDIA_ROOT=/var/lib/pms-media
DOWNLOADS_ROOT=/var/lib/pms-downloads
API_USER=pmsapi
WORKER_USER=pmsworker
RETENTION_USER=pmsretention
SERVICES=(pms-api.service pms-web.service pms-worker.service pms-retention.service)
HOST=eval.centralindia.cloudapp.azure.com
EMAIL=net.pratham@hotmail.com
ARCHIVE=
POSTGRES_ADMIN_USER=postgres
ALLOW_SCHEMA_UPGRADE=0
ALLOW_DATA_LOSS=0
RESTORE_BACKUP=
COMMAND=${1:-}
OLD_RELEASE=
NEW_RELEASE=
BACKUP_FILE=
BACKUP_READY=0
SITE_SAVED=
SITE_CHANGED=0
SERVICES_STOPPED=0
SWITCHED=0
SCHEMA_CHANGED=0
DATABASE_MUTATION=0
RECOVERING=0
WORK=
ROLE_CONFIG_CHANGED=0

usage() {
  cat <<'EOF'
Usage:
  sudo bash deploy-platform.sh init-config [--host DNS_NAME] [--postgres-admin-user USER]
  sudo bash deploy-platform.sh deploy --archive /path/pms-platform.zip [--email EMAIL] [--host DNS_NAME]
       [--allow-schema-upgrade --allow-data-loss]
  sudo bash deploy-platform.sh rollback [--restore-backup /var/backups/pms-platform/FILE.dump --allow-data-loss]
  sudo bash deploy-platform.sh setup-key
  sudo bash deploy-platform.sh status

The defaults are eval.centralindia.cloudapp.azure.com and
net.pratham@hotmail.com. init-config creates the database, separate roles and
private environment files with generated passwords and application keys. The
default VM-local mode enables password sign-in and bounded private VM media;
email and external OIDC are disabled until real providers are configured.
New VM-local configurations enable Platform Admin model management, while
external model calls remain disabled until the operator explicitly enables them.
An upgrade that changes Alembic revision requires both explicit flags. The
script blocks public traffic, backs up PostgreSQL, and restores that backup if
the new release fails. A manual rollback across revisions requires its matching
backup and --allow-data-loss because later writes will be lost.
EOF
}

log() { printf '[pms-deploy] %s\n' "$*"; }
die() { printf '[pms-deploy] ERROR: %s\n' "$*" >&2; exit 1; }

shift || true
while (($#)); do
  case "$1" in
    --archive|--email|--host|--restore-backup|--postgres-admin-user)
      (($# >= 2)) || die "Missing value for $1"
      case "$1" in
        --archive) ARCHIVE=$2 ;;
        --email) EMAIL=$2 ;;
        --host) HOST=$2 ;;
        --restore-backup) RESTORE_BACKUP=$2 ;;
        --postgres-admin-user) POSTGRES_ADMIN_USER=$2 ;;
      esac
      shift 2 ;;
    --allow-schema-upgrade) ALLOW_SCHEMA_UPGRADE=1; shift ;;
    --allow-data-loss) ALLOW_DATA_LOSS=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done
[[ $COMMAND == init-config || $COMMAND == deploy || $COMMAND == rollback || $COMMAND == setup-key || $COMMAND == status ]] || { usage; exit 2; }
[[ $EUID == 0 ]] || die "Run with sudo or as root."
[[ -r /etc/os-release ]] || die "Ubuntu could not be identified."
# shellcheck disable=SC1091
. /etc/os-release
[[ ${ID:-} == ubuntu ]] || die "This script supports Ubuntu only."
[[ $HOST =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]$ ]] || die "Invalid DNS hostname."
[[ -z $EMAIL || $EMAIL =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]] || die "Invalid certificate email."
[[ $POSTGRES_ADMIN_USER =~ ^[a-z_][a-z0-9_]*$ ]] || die "Invalid PostgreSQL administrator name."
for variable in ${!PMS_@}; do unset "$variable"; done
for variable in ${!PG@}; do unset "$variable"; done
exec 9>/run/pms-platform-deploy.lock
flock -n 9 || die "Another platform deployment is already running."

ensure_user() {
  if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /var/lib/pms-platform --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
  fi
  getent group "$MEDIA_GROUP" >/dev/null || groupadd --system "$MEDIA_GROUP"
  ! id -nG "$SERVICE_USER" | tr ' ' '\n' | grep -Fxq "$MEDIA_GROUP" \
    || die "The web/build account must not belong to the private media group."
  local account
  for account in "$API_USER" "$WORKER_USER" "$RETENTION_USER"; do
    if ! id "$account" >/dev/null 2>&1; then
      useradd --system --user-group --groups "$SERVICE_USER,$MEDIA_GROUP" --home-dir /var/lib/pms-platform --shell /usr/sbin/nologin "$account"
    fi
    [[ $(id -gn "$account") == "$account" ]] && id -nG "$account" | tr ' ' '\n' | grep -Fxq "$SERVICE_USER" \
      || die "Service account $account must have its own primary group and belong to $SERVICE_USER."
    id -nG "$account" | tr ' ' '\n' | grep -Fxq "$MEDIA_GROUP" || usermod -a -G "$MEDIA_GROUP" "$account"
  done
  [[ ! -L $MEDIA_ROOT ]] || die "Private media storage cannot be a symlink."
  install -d -m 2770 -o root -g "$MEDIA_GROUP" "$MEDIA_ROOT"
  if [[ ! -e $MEDIA_ROOT/.quota.lock ]]; then
    install -m 0660 -o root -g "$MEDIA_GROUP" /dev/null "$MEDIA_ROOT/.quota.lock"
  fi
  [[ -f $MEDIA_ROOT/.quota.lock && ! -L $MEDIA_ROOT/.quota.lock && $(stat -c %u "$MEDIA_ROOT/.quota.lock") == 0 && $(stat -c %G "$MEDIA_ROOT/.quota.lock") == "$MEDIA_GROUP" ]] \
    || die "Private media quota lock is unsafe."
  install -d -m 0750 -o root -g "$SERVICE_USER" "$CONFIG" "$APP" "$APP/releases"
  [[ ! -L $DOWNLOADS_ROOT ]] || die "Desktop downloads cannot be a symlink."
  install -d -m 0750 -o root -g "$API_USER" "$DOWNLOADS_ROOT"
  install -d -m 0700 -o root -g root "$BACKUPS"
  install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" /var/lib/pms-platform /var/cache/pms-platform
}

init_config() {
  command -v python3.12 >/dev/null || die "Install Python 3.12 before creating configuration."
  ensure_user
  if [[ -e $CONFIG/api.env || -e $CONFIG/migration.url ]]; then
    [[ -f $CONFIG/api.env && ! -L $CONFIG/api.env && -f $CONFIG/migration.url && ! -L $CONFIG/migration.url ]] || die "Incomplete private configuration in $CONFIG."
    [[ $(stat -c %u "$CONFIG/api.env") == 0 && $(stat -c %u "$CONFIG/migration.url") == 0 ]] || die "Private configuration must be owned by root."
    chown root:root "$CONFIG/api.env"
    chmod 0600 "$CONFIG/api.env"
    chmod 0600 "$CONFIG/migration.url"
    log "Existing configuration retained in $CONFIG"
  else
    python3.12 - "$CONFIG/api.env" "$CONFIG/migration.url" "$HOST" <<'PY'
import base64
import os
import secrets
import sys

api_path, migration_path, host = sys.argv[1:]
key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
api_password, worker_password, retention_password, owner_password = (secrets.token_urlsafe(32) for _ in range(4))
config = f"""# Private PMS runtime configuration; no migration-owner URL in this file.
PMS_ENVIRONMENT=production
PMS_BIND_HOST=127.0.0.1
PMS_PORT=8000
PMS_DATABASE_URL=postgresql+psycopg://pms_api:{api_password}@127.0.0.1:5432/device_platform
PMS_WORKER_DATABASE_URL=postgresql+psycopg://pms_worker:{worker_password}@127.0.0.1:5432/device_platform
PMS_RETENTION_DATABASE_URL=postgresql+psycopg://pms_retention:{retention_password}@127.0.0.1:5432/device_platform
PMS_TOKEN_PEPPER={secrets.token_urlsafe(48)}
PMS_MEDIA_SIGNING_KEY={secrets.token_urlsafe(48)}
PMS_ACTIVE_CREDENTIAL_KEY=v1
PMS_CREDENTIAL_KEYS={{"v1":"{key}"}}
PMS_VM_LOCAL_MODE=true
PMS_OIDC_ISSUER=
PMS_OIDC_AUDIENCE=
PMS_LOCAL_AUTH_ENABLED=true
PMS_LOCAL_TOKEN_SIGNING_KEY={secrets.token_urlsafe(48)}
PMS_LOCAL_BROWSER_SESSION_HOURS=24
PMS_INITIAL_SETUP_KEY={secrets.token_urlsafe(48)}
PMS_SMTP_HOST=
PMS_SMTP_PORT=587
PMS_SMTP_USERNAME=
PMS_SMTP_PASSWORD=
PMS_SMTP_SENDER=
PMS_ACCOUNT_ACTION_BASE_URL=https://{host}/account
PMS_INVITATION_BASE_URL=https://{host}/invitations/accept
PMS_PUBLIC_BASE_URL=https://{host}
PMS_CORS_ORIGINS=[]
PMS_STORAGE_BACKEND=local
PMS_STORAGE_ROOT=/var/lib/pms-media
PMS_DOWNLOADS_ROOT=/var/lib/pms-downloads
PMS_VM_LOCAL_STORAGE_LIMIT_BYTES=5000000000
PMS_LLM_ENABLED=true
PMS_EXTERNAL_CALLS_ENABLED=false
PMS_EXPOSE_DOCS=false
"""
for path, content in (
    (api_path, config),
    (migration_path, f"postgresql+psycopg://pms_owner:{owner_password}@127.0.0.1:5432/device_platform\n"),
):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write(content)
PY
    chown root:root "$CONFIG/api.env"
    chmod 0600 "$CONFIG/api.env"
    log "Created private application keys and database passwords in $CONFIG."
  fi
  if ! grep -q '^PMS_DOWNLOADS_ROOT=' "$CONFIG/api.env"; then
    printf '\nPMS_DOWNLOADS_ROOT=/var/lib/pms-downloads\n' >> "$CONFIG/api.env"
  fi
  bootstrap_database
  log "Generated VM-local configuration in $CONFIG/api.env; no manual environment edit is required."
}

postgres_admin() {
  if [[ ${POSTGRES_ADMIN_MODE:-} == peer ]]; then
    runuser -u postgres -- psql -X -w -v ON_ERROR_STOP=1 -h /var/run/postgresql -d postgres "$@"
  else
    psql -X -w -v ON_ERROR_STOP=1 -h 127.0.0.1 -U "$POSTGRES_ADMIN_USER" -d postgres "$@"
  fi
}

bootstrap_database() (
  set -Eeuo pipefail
  command -v psql >/dev/null || { apt-get update -qq; apt-get install -y postgresql-client; }
  local boot_dir
  boot_dir=$(mktemp -d /run/pms-platform-db.XXXXXX)
  trap 'rm -rf -- "$boot_dir"' EXIT
  if id postgres >/dev/null 2>&1 && runuser -u postgres -- psql -X -w -Atqc 'SELECT 1' -d postgres >/dev/null 2>&1; then
    POSTGRES_ADMIN_MODE=peer
  else
    [[ -r /dev/tty ]] || die "Local PostgreSQL peer access failed; run from a terminal to enter the administrator password."
    read -r -s -p "PostgreSQL administrator password for $POSTGRES_ADMIN_USER: " PGPASSWORD </dev/tty
    printf '\n' >/dev/tty
    export PGPASSWORD
    POSTGRES_ADMIN_MODE=tcp
    postgres_admin -Atqc 'SELECT 1' >/dev/null || die "PostgreSQL administrator login failed."
  fi
  local existing_owner
  existing_owner=$(postgres_admin -Atqc "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='device_platform'")
  [[ -z $existing_owner || $existing_owner == pms_owner ]] \
    || die "Existing application database has a different owner; it was not changed."
  if [[ -n $existing_owner ]]; then
    [[ $(postgres_admin -Atqc "SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname='device_platform'") == UTF8 ]] \
      || die "Existing application database must use UTF8 encoding; it was not changed."
  fi
  [[ $(postgres_admin -Atqc "SELECT coalesce(bool_and(NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls), true) AND NOT EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname IN ('pms_owner','pms_api','pms_worker','pms_retention')) FROM pg_roles WHERE rolname IN ('pms_owner','pms_api','pms_worker','pms_retention')") == t ]] \
    || die "Existing platform roles have elevated privileges or other role memberships; nothing was changed."
  python3.12 - "$CONFIG/api.env" "$CONFIG/migration.url" "$boot_dir/bootstrap.sql" "$boot_dir/runtime.pgpass" <<'PY'
import os
import sys
from urllib.parse import unquote, urlsplit

env_path, migration_path, sql_path, pass_path = sys.argv[1:]
values = {}
for line in open(env_path, encoding="utf-8"):
    if line.startswith("PMS_") and "=" in line:
        name, value = line.rstrip("\n").split("=", 1)
        values[name] = value
values["PMS_MIGRATION_DATABASE_URL"] = open(migration_path, encoding="utf-8").read().strip()
roles = (("PMS_DATABASE_URL", "pms_api"), ("PMS_WORKER_DATABASE_URL", "pms_worker"),
         ("PMS_RETENTION_DATABASE_URL", "pms_retention"), ("PMS_MIGRATION_DATABASE_URL", "pms_owner"))
passwords = {}
for name, expected in roles:
    url = urlsplit(values.get(name, ""))
    if (url.scheme != "postgresql+psycopg" or url.hostname != "127.0.0.1" or
        url.port != 5432 or unquote(url.username or "") != expected or
        url.path != "/device_platform" or not url.password):
        raise SystemExit("Database URLs must use the generated local role and database names")
    passwords[expected] = unquote(url.password)
def literal(value):
    return "'" + value.replace("'", "''") + "'"
with open(sql_path, "x", encoding="utf-8") as output:
    output.write("\\set ON_ERROR_STOP on\n")
    for role, password in passwords.items():
        output.write(f"SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', {literal(role)}, {literal(password)}) "
                     f"WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname={literal(role)})\\gexec\n")
    output.write("SELECT format('CREATE DATABASE %I OWNER %I TEMPLATE template0 ENCODING %L', "
                 "'device_platform', 'pms_owner', 'UTF8') "
                 "WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname='device_platform')\\gexec\n")
    output.write("ALTER DATABASE device_platform SET timezone TO 'UTC';\n")
    output.write("ALTER DATABASE device_platform SET client_encoding TO 'UTF8';\n")
    output.write("REVOKE ALL ON DATABASE device_platform FROM PUBLIC;\n")
    output.write("GRANT CONNECT ON DATABASE device_platform TO pms_api, pms_worker, pms_retention;\n")
    output.write("GRANT CONNECT ON DATABASE postgres TO pms_owner;\n")
with open(pass_path, "x", encoding="utf-8") as output:
    for role, password in passwords.items():
        escaped = password.replace("\\", "\\\\").replace(":", "\\:")
        output.write(f"127.0.0.1:5432:device_platform:{role}:{escaped}\n")
os.chmod(sql_path, 0o600)
os.chmod(pass_path, 0o600)
PY
  postgres_admin < "$boot_dir/bootstrap.sql" >/dev/null
  [[ $(postgres_admin -Atqc "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='device_platform'") == pms_owner ]] \
    || die "Existing application database has a different owner; it was not changed."
  [[ $(postgres_admin -Atqc "SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname='device_platform'") == UTF8 ]] \
    || die "Application database must use UTF8 encoding."
  [[ $(postgres_admin -Atqc "SELECT count(*)=4 AND bool_and(NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls) AND NOT EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname IN ('pms_owner','pms_api','pms_worker','pms_retention')) FROM pg_roles WHERE rolname IN ('pms_owner','pms_api','pms_worker','pms_retention')") == t ]] \
    || die "Platform database roles are missing, elevated or members of other roles; they were not changed."
  unset PGPASSWORD || true
  local role
  for role in pms_owner pms_api pms_worker pms_retention; do
    PGPASSFILE="$boot_dir/runtime.pgpass" psql -X -w -Atqc 'SELECT 1' -h 127.0.0.1 -p 5432 -U "$role" -d device_platform >/dev/null \
      || die "Generated credentials could not connect as $role. Existing role passwords were not changed."
  done
  log "Local PostgreSQL database and separate owner/API/worker/retention roles are ready."
)

show_setup_key() {
  [[ -f $CONFIG/api.env && ! -L $CONFIG/api.env && $(stat -c %u "$CONFIG/api.env") == 0 ]] \
    || die "The root-owned platform configuration does not exist. Deploy the platform first."
  [[ -w /dev/tty ]] || die "Run setup-key from an interactive terminal; the key is never written to redirected output."
  python3.12 - "$CONFIG/api.env" >/dev/tty <<'PY'
import sys

matches = []
for line in open(sys.argv[1], encoding="utf-8"):
    if line.startswith("PMS_INITIAL_SETUP_KEY="):
        matches.append(line.rstrip("\n").split("=", 1)[1])
if len(matches) != 1 or not matches[0]:
    raise SystemExit("The initial setup key is missing or duplicated")
print(matches[0])
PY
}

check_config_files() {
  [[ -f $CONFIG/api.env && ! -L $CONFIG/api.env ]] || die "Run init-config and fill $CONFIG/api.env."
  [[ -f $CONFIG/migration.url && ! -L $CONFIG/migration.url ]] || die "Run init-config and fill $CONFIG/migration.url."
  ! grep -q 'REPLACE_' "$CONFIG/api.env" "$CONFIG/migration.url" || die "Configuration still contains REPLACE_ placeholders."
  [[ $(stat -c %u "$CONFIG/api.env") == 0 && $(stat -c %u "$CONFIG/migration.url") == 0 ]] || die "Configuration must be owned by root."
  chown root:root "$CONFIG/api.env"
  chmod 0600 "$CONFIG/api.env"
  chmod 0600 "$CONFIG/migration.url"
  ! grep -q '^PMS_MIGRATION_DATABASE_URL=' "$CONFIG/api.env" || die "Keep the migration-owner URL out of api.env."
  if [[ $COMMAND == deploy ]] && ! grep -q '^PMS_DOWNLOADS_ROOT=' "$CONFIG/api.env"; then
    printf '\nPMS_DOWNLOADS_ROOT=/var/lib/pms-downloads\n' >> "$CONFIG/api.env"
  fi
}

sync_role_configs() {
  local role account destination
  for role in api worker retention; do
    case "$role" in
      api) account=$API_USER ;;
      worker) account=$WORKER_USER ;;
      retention) account=$RETENTION_USER ;;
    esac
    install -d -m 0750 -o root -g "$account" "$CONFIG/$role"
    destination="$CONFIG/$role/.env"
    [[ ! -L $destination ]] || die "Refusing a symlink in role configuration: $destination"
    if [[ -e $destination ]]; then
      [[ -f $destination && $(stat -c %u "$destination") == 0 ]] || die "Role configuration must be a root-owned file: $destination"
      cp -a "$destination" "$WORK/$role.env.previous"
    fi
  done
  ROLE_CONFIG_CHANGED=1
  python3.12 - "$CONFIG/api.env" "$CONFIG" <<'PY'
import os
import pathlib
import re
import sys
import tempfile

source, directory = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
db_keys = {
    "api": "PMS_DATABASE_URL",
    "worker": "PMS_WORKER_DATABASE_URL",
    "retention": "PMS_RETENTION_DATABASE_URL",
}
lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
seen = set()
for line in lines:
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    name = line.split("=", 1)[0]
    if not re.fullmatch(r"PMS_[A-Z0-9_]+", name) or name in seen:
        raise SystemExit("Configuration must contain unique PMS_NAME=value entries")
    seen.add(name)
if not set(db_keys.values()).issubset(seen):
    raise SystemExit("Runtime database URLs are incomplete")
for role, db_key in db_keys.items():
    destination = directory / role / ".env"
    account = {"api": "pmsapi", "worker": "pmsworker", "retention": "pmsretention"}[role]
    content = "".join(
        line for line in lines
        if not line.startswith("PMS_") or line.split("=", 1)[0] not in set(db_keys.values()) - {db_key}
    )
    if role != "api":
        content = "".join(line for line in content.splitlines(keepends=True)
                          if not line.startswith("PMS_TRAINING_KEY_FILE="))
    fd, temporary = tempfile.mkstemp(prefix=".env.next.", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        if hasattr(os, "chown"):
            import grp
            os.chown(temporary, 0, grp.getgrnam(account).gr_gid)
        os.chmod(temporary, 0o640)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
PY
}

restore_role_configs() {
  if [[ -f $WORK/training-master.env.previous ]]; then
    cp -a "$WORK/training-master.env.previous" "$CONFIG/api.env"
  fi
  ((ROLE_CONFIG_CHANGED)) || return 0
  local role destination
  for role in api worker retention; do
    destination="$CONFIG/$role/.env"
    if [[ -f $WORK/$role.env.previous ]]; then
      cp -a "$WORK/$role.env.previous" "$destination"
    else
      rm -f -- "$destination"
    fi
  done
}

prepare_pgpass() {
  export PGPASSFILE="$WORK/pgpass"
  mapfile -t DB_PARTS < <(python3.12 - "$CONFIG/migration.url" "$PGPASSFILE" <<'PY'
import os
import sys
from urllib.parse import unquote, urlsplit

lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
if len(lines) != 1 or not lines[0].startswith("postgresql+psycopg://"):
    raise SystemExit("migration.url must contain one postgresql+psycopg URL")
url = urlsplit(lines[0])
host, port = url.hostname, url.port or 5432
user, password, database = unquote(url.username or ""), unquote(url.password or ""), url.path.lstrip("/")
if host not in {"127.0.0.1", "localhost"} or not user or not password or not database or url.fragment:
    raise SystemExit("Use a complete local migration-owner URL")
def escape(value):
    return value.replace("\\", "\\\\").replace(":", "\\:")
with open(sys.argv[2], "x", encoding="utf-8") as output:
    output.write(":".join(map(escape, (host, str(port), database, user, password))) + "\n")
os.chmod(sys.argv[2], 0o600)
print(host, port, database, user, sep="\n")
PY
  )
  ((${#DB_PARTS[@]} == 4)) || die "Invalid migration-owner URL."
  DB_HOST=${DB_PARTS[0]}
  DB_PORT=${DB_PARTS[1]}
  DB_NAME=${DB_PARTS[2]}
  DB_USER=${DB_PARTS[3]}
}

psql_owner() {
  psql -X -w -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" "$@"
}

check_archive_and_extract() {
  local archive=$1 destination=$2
  python3.12 - "$archive" "$destination" <<'PY'
import hashlib
import json
import os
import pathlib
import stat
import sys
import zipfile

archive_path, target = sys.argv[1:]
required = {
    "platform/api/pyproject.toml", "platform/api/uv.lock",
    "platform/api/deploy/grant-runtime-access.sql", "platform/ui/package-lock.json",
    "platform/ui/apps/web/.next/BUILD_ID", "shared/training-contracts/pyproject.toml",
}
with zipfile.ZipFile(archive_path) as archive:
    infos = archive.infolist()
    names = [entry.filename for entry in infos]
    if len(names) != len(set(names)) or "manifest.json" not in names:
        raise SystemExit("Archive has duplicate entries or no manifest")
    if archive.getinfo("manifest.json").file_size > 2_000_000:
        raise SystemExit("Archive manifest is too large")
    manifest = json.loads(archive.read("manifest.json"))
    hashes = manifest.get("sha256")
    if manifest.get("format") != 1 or not isinstance(hashes, dict) or set(hashes) != set(names) - {"manifest.json"}:
        raise SystemExit("Archive manifest does not match its entries")
    if not required.issubset(hashes) or len([n for n in hashes if n.startswith("wheels/") and n.endswith("-py3-none-any.whl")]) != 2:
        raise SystemExit("Archive is missing platform components")
    total = 0
    for entry in infos:
        name = entry.filename
        path = pathlib.PurePosixPath(name)
        mode = (entry.external_attr >> 16) & 0o170000
        if (
            name != "manifest.json" and path.parts[0] not in {"platform", "shared", "wheels"}
            or name.startswith("/") or "\\" in name or any(p in {"", ".", ".."} for p in path.parts)
            or any(p in {"node_modules", ".venv"} or p.startswith(".env") and p != ".env.example" for p in path.parts)
            or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}
            or entry.is_dir() or mode not in {0, stat.S_IFREG} or entry.file_size > 200_000_000
        ):
            raise SystemExit("Archive contains an unsafe path or file")
        total += entry.file_size
        if total > 1_000_000_000:
            raise SystemExit("Archive expands beyond the size limit")
    for entry in infos:
        output = pathlib.Path(target) / entry.filename
        output.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with archive.open(entry) as source, open(output, "xb") as stream:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                stream.write(chunk)
        if entry.filename != "manifest.json" and digest.hexdigest() != hashes[entry.filename]:
            raise SystemExit("Archive checksum mismatch")
PY
}

install_prerequisites() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y ca-certificates curl gnupg ffmpeg certbot nginx postgresql-client iproute2
  if [[ ! -x /usr/bin/node ]] || [[ $(/usr/bin/node -p 'process.versions.node.split(".")[0]') -lt 24 ]]; then
    local architecture
    architecture=$(dpkg --print-architecture)
    [[ $architecture == amd64 || $architecture == arm64 ]] || die "NodeSource supports amd64/arm64 for this script."
    install -d -m 0755 /usr/share/keyrings
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key -o "$WORK/nodesource.key"
    gpg --batch --yes --dearmor -o /usr/share/keyrings/nodesource.gpg "$WORK/nodesource.key"
    chmod 0644 /usr/share/keyrings/nodesource.gpg
    printf 'Types: deb\nURIs: https://deb.nodesource.com/node_24.x\nSuites: nodistro\nComponents: main\nArchitectures: %s\nSigned-By: /usr/share/keyrings/nodesource.gpg\n' "$architecture" > /etc/apt/sources.list.d/nodesource.sources
    apt-get update -qq
    apt-get install -y nodejs
  fi
  [[ -x /usr/bin/node && $(/usr/bin/node -p 'process.versions.node.split(".")[0]') -ge 24 ]] || die "Node.js 24 installation failed."
  command -v npm >/dev/null || die "npm is missing."
  command -v python3.12 >/dev/null || die "Python 3.12 is missing."
  if [[ ! -x $APP/tools/bin/uv ]]; then
    if ! python3.12 -m venv "$APP/tools"; then
      apt-get install -y python3.12-venv
      python3.12 -m venv "$APP/tools"
    fi
    "$APP/tools/bin/python" -m pip install --no-input --disable-pip-version-check 'uv==0.12.9'
  fi
  chown -R root:"$SERVICE_USER" "$APP/tools"
  chmod -R u+rwX,g+rX,g-w,o-rwx "$APP/tools"
}

build_release() {
  chown -R "$SERVICE_USER:$SERVICE_USER" "$NEW_RELEASE"
  local api="$NEW_RELEASE/platform/api" ui="$NEW_RELEASE/platform/ui"
  log "Installing locked Python dependencies and building the UI on Ubuntu."
  runuser -u "$SERVICE_USER" -- env -i PATH=/usr/bin:/bin HOME=/var/lib/pms-platform UV_CACHE_DIR=/var/cache/pms-platform/uv UV_PYTHON_DOWNLOADS=never \
    "$APP/tools/bin/uv" sync --frozen --no-dev --python "$(command -v python3.12)" --project "$api"
  runuser -u "$SERVICE_USER" -- env -i PATH=/usr/bin:/bin HOME=/var/lib/pms-platform npm ci --no-audit --no-fund --prefix "$ui"
  runuser -u "$SERVICE_USER" -- env -i PATH=/usr/bin:/bin HOME=/var/lib/pms-platform NEXT_TELEMETRY_DISABLED=1 npm run build --prefix "$ui"
  runuser -u "$SERVICE_USER" -- env -i PATH=/usr/bin:/bin HOME=/var/lib/pms-platform npm prune --omit=dev --no-audit --no-fund --prefix "$ui"
  [[ -f $ui/apps/web/.next/BUILD_ID && -x $api/.venv/bin/pms-api ]] || die "The Linux build is incomplete."
  chown -R root:"$SERVICE_USER" "$NEW_RELEASE"
  chmod -R u+rwX,g+rX,g-w,o-rwx "$NEW_RELEASE"
  install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$ui/apps/web/.next/cache"
}

provision_training_key() {
  local api="$NEW_RELEASE/platform/api"
  cp -a "$CONFIG/api.env" "$WORK/training-master.env.previous"
  "$api/.venv/bin/python" - "$CONFIG" "$API_USER" <<'PY'
import sys
from pathlib import Path
from pms_api.security.training_keys import TrainingKeyError, ensure_training_configuration

directory, group = Path(sys.argv[1]), sys.argv[2] or None
try:
    key = ensure_training_configuration(
        directory / "api.env",
        default_key=directory / "api/training-private.pem",
        runtime_directory=directory / "api",
        key_group=group,
    )
    ensure_training_configuration(
        directory / "api/.env", default_key=key,
        runtime_directory=directory / "api", key_group=group,
    )
except TrainingKeyError as error:
    raise SystemExit(str(error)) from None
print("Training signing key provisioned; existing signing identity preserved.")
PY
}

validate_runtime() {
  local api="$NEW_RELEASE/platform/api"
  local role account field
  for role in api worker retention; do
    case "$role" in
      api) account=$API_USER; field=database_url ;;
      worker) account=$WORKER_USER; field=worker_database_url ;;
      retention) account=$RETENTION_USER; field=retention_database_url ;;
    esac
    runuser -u "$account" -- env -i PATH=/usr/bin:/bin HOME=/var/lib/pms-platform sh -c 'cd "$1" && exec "$2/.venv/bin/python" - "$3" "$4" "$5" "$6" <<"PY"
import sys
try:
    from sqlalchemy.engine import make_url
    from pms_api.core.config import Settings
    from pms_api.cli import migration_config
    from pms_api.database.session import REVISION
    from alembic.script import ScriptDirectory
    settings = Settings()
    assert settings.environment == "production"
    assert settings.bind_host == "127.0.0.1" and settings.port == 8000
    assert settings.public_base_url.rstrip("/") == "https://" + sys.argv[1]
    if settings.vm_local_mode:
        assert settings.storage_backend == "local" and settings.storage_root.as_posix() == "/var/lib/pms-media"
    else:
        assert settings.storage_backend in {"azure", "s3"} and settings.storage_bucket
        assert settings.storage_backend != "azure" or settings.azure_storage_account
    assert settings.migration_database_url is None
    assert ScriptDirectory.from_config(migration_config()).get_current_head() == REVISION
    role, field = sys.argv[3:5]
    url = make_url(getattr(settings, field).get_secret_value())
    assert url.drivername == "postgresql+psycopg" and url.username == role and url.password
    assert url.host == "127.0.0.1" and url.port == 5432 and url.database == sys.argv[2]
    assert all(
        getattr(settings, other) is None
        for other in {"worker_database_url", "retention_database_url"} - {field}
    )
    if field != "database_url":
        assert not make_url(settings.database_url.get_secret_value()).password
    else:
        from pms_api.security.training_keys import load_training_key
        assert settings.training_key_file is not None
        load_training_key(settings.training_key_file)
except Exception:
    raise SystemExit("Invalid production runtime configuration; check the private env file")
PY' sh "$CONFIG/$role" "$api" "$HOST" "$DB_NAME" "pms_$role" "$field"
  done
}

release_revision() {
  local release=$1
  "$release/platform/api/.venv/bin/python" -c 'from pms_api.database.session import REVISION; print(REVISION)'
}

database_revision() {
  psql_owner -Atc 'SELECT version_num FROM public.alembic_version'
}

require_exclusive_database() {
  local others
  others=$(psql_owner -Atc "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND backend_type='client backend' AND pid<>pg_backend_pid()")
  if [[ $others != 0 ]]; then
    log "Other sessions are connected to the application database; stop them before migration or restore."
    return 1
  fi
}

grant_roles() {
  local release=$1
  psql_owner -v db_name="$DB_NAME" -v api_role=pms_api -v worker_role=pms_worker -v maintenance_role=pms_retention \
    -f "$release/platform/api/deploy/grant-runtime-access.sql" >/dev/null
}

migrate_database() (
  cd "$NEW_RELEASE/platform/api"
  .venv/bin/python - "$CONFIG/api.env" "$CONFIG/migration.url" <<'PY'
import os
import sys

from dotenv import dotenv_values
from pms_api.cli import admin

for name, value in dotenv_values(sys.argv[1]).items():
    if name.startswith("PMS_") and value is not None:
        os.environ[name] = value
os.environ["PMS_MIGRATION_DATABASE_URL"] = open(sys.argv[2], encoding="utf-8").read().strip()
sys.argv = ["pms-admin", "init-database"]
admin()
PY
)

backfill_tenant_catalog() (
  cd "$NEW_RELEASE/platform/api"
  .venv/bin/python - "$CONFIG/api.env" "$CONFIG/migration.url" <<'PY'
import os
import sys

from dotenv import dotenv_values
from pms_api.core.config import Settings
from pms_api.database.tenant_catalog_backfill import backfill

for name, value in dotenv_values(sys.argv[1]).items():
    if name.startswith("PMS_") and value is not None:
        os.environ[name] = value
os.environ["PMS_MIGRATION_DATABASE_URL"] = open(sys.argv[2], encoding="utf-8").read().strip()
settings = Settings()
after = None
totals = [0, 0, 0]
while True:
    rows = backfill(settings, apply=True, after=after, limit=25)
    if not rows:
        break
    for row in rows:
        if row.legacy_selections != row.mapped_selections:
            raise RuntimeError("A legacy rehearsal selection has no tenant mapping")
        totals[0] += 1
        totals[1] += row.legacy_selections
        totals[2] += row.cases
    after = rows[-1].organization_id
print(f"Tenant catalog mapping: {totals[0]} tenants, {totals[1]} selections, {totals[2]} cases")
PY
)

backup_database() {
  require_exclusive_database
  BACKUP_FILE="$BACKUPS/pms-platform-$(date -u +%Y%m%d-%H%M%S)-$$.dump"
  pg_dump -w -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -Fc -f "$BACKUP_FILE"
  chmod 0600 "$BACKUP_FILE"
  printf '%s\n' "$(release_revision "$OLD_RELEASE")" > "$BACKUP_FILE.revision"
  chmod 0600 "$BACKUP_FILE.revision"
  BACKUP_READY=1
  log "Database backup saved at $BACKUP_FILE"
}

restore_database() {
  local file=$1 release=$2 restore_sql
  [[ -f $file && ! -L $file ]] || return 1
  require_exclusive_database || return 1
  log "Restoring the explicitly authorized database backup."
  restore_sql=$(mktemp "$WORK/restore.XXXXXX.sql") || return 1
  chmod 0600 "$restore_sql"
  pg_restore --clean --if-exists --exit-on-error --file "$restore_sql" "$file" || return 1
  # New tables can reference old tables but be absent from the backup. Remove
  # the managed schema and replay the dump in one transaction so those newer
  # dependencies cannot block recovery; a failed restore rolls everything back.
  psql_owner --single-transaction \
    -c 'DROP SCHEMA IF EXISTS device_platform CASCADE' -f "$restore_sql" >/dev/null || return 1
  grant_roles "$release" || return 1
  [[ $(database_revision) == "$(release_revision "$release")" ]] || return 1
}

write_site() {
  local mode=$1
  install -d -m 0755 "$ACME_ROOT" /etc/nginx/sites-available /etc/nginx/sites-enabled
  if [[ -e $SITE && $SITE_CHANGED == 0 ]]; then
    grep -q 'Managed by pms-platform deploy-platform.sh' "$SITE" || die "Refusing to replace an unmanaged Nginx site."
    cp -a "$SITE" "$WORK/site.previous"
    SITE_SAVED="$WORK/site.previous"
  fi
  SITE_CHANGED=1
  if [[ $mode == acme ]]; then
    cat > "$SITE" <<EOF
# Managed by pms-platform deploy-platform.sh
server {
    listen 80;
    server_name $HOST;
    access_log off;
    location /.well-known/acme-challenge/ { root $ACME_ROOT; }
    location / { return 503; }
}
EOF
  else
    local response='return 503;'
    local api_response='return 503;'
    if [[ $mode == active ]]; then
      response='proxy_pass http://127.0.0.1:3000;'
      api_response='proxy_pass http://127.0.0.1:8000;'
    fi
    cat > "$SITE" <<EOF
# Managed by pms-platform deploy-platform.sh
server {
    listen 80;
    server_name $HOST;
    access_log off;
    location /.well-known/acme-challenge/ { root $ACME_ROOT; }
    location / { return 301 https://\$host\$request_uri; }
}
server {
    listen 443 ssl;
    server_name $HOST;
    ssl_certificate /etc/letsencrypt/live/$HOST/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$HOST/privkey.pem;
    access_log off;
    client_max_body_size 105m;
    location /api/v1/ {
        $api_response
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
    location / {
        $response
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_read_timeout 300s;
    }
}
EOF
  fi
  if [[ -L $SITE_LINK ]]; then
    [[ $(readlink -f "$SITE_LINK") == "$SITE" ]] || die "Nginx site link points elsewhere."
  elif [[ -e $SITE_LINK ]]; then
    die "Nginx site link is not managed by this script."
  else
    ln -s "$SITE" "$SITE_LINK"
  fi
  nginx -t >/dev/null
  systemctl reload nginx
}

ensure_certificate() {
  if [[ ! -f /etc/letsencrypt/live/$HOST/fullchain.pem || ! -f /etc/letsencrypt/live/$HOST/privkey.pem ]]; then
    [[ -n $EMAIL ]] || die "Pass --email for the first Let's Encrypt certificate."
    write_site acme
    log "Requesting a Let's Encrypt certificate. DNS and inbound port 80 must reach this VM."
    certbot certonly --webroot -w "$ACME_ROOT" -d "$HOST" --email "$EMAIL" \
      --agree-tos --non-interactive --keep-until-expiring
  fi
  [[ -s /etc/letsencrypt/live/$HOST/fullchain.pem && -s /etc/letsencrypt/live/$HOST/privkey.pem ]] || die "TLS certificate is unavailable."
  install -d -m 0755 /etc/letsencrypt/renewal-hooks/deploy
  printf '#!/bin/sh\nsystemctl reload nginx\n' > /etc/letsencrypt/renewal-hooks/deploy/pms-nginx-reload.sh
  chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/pms-nginx-reload.sh
  systemctl list-unit-files certbot.timer --no-legend | grep -q certbot.timer || die "Certbot renewal timer is unavailable."
  systemctl enable --now certbot.timer >/dev/null
}

install_services() {
  local unit
  for unit in "${SERVICES[@]}"; do
    if [[ -e /etc/systemd/system/$unit ]]; then
      grep -q 'Managed by pms-platform deploy-platform.sh' "/etc/systemd/system/$unit" || die "Refusing to replace unmanaged $unit."
    fi
  done
  for unit in "${SERVICES[@]}"; do
    local executable working environment= account=$SERVICE_USER supplementary=$SERVICE_USER unit_umask=0027
    case "$unit" in
      pms-api.service) executable="$APP/current/platform/api/.venv/bin/pms-api"; working="$CONFIG/api"; account=$API_USER; supplementary="$SERVICE_USER $MEDIA_GROUP"; unit_umask=0007 ;;
      pms-web.service) executable="/usr/bin/node $APP/current/platform/ui/node_modules/next/dist/bin/next start -H 127.0.0.1 -p 3000"; working="$APP/current/platform/ui/apps/web"; environment='Environment=NODE_ENV=production PMS_API_BASE_URL=http://127.0.0.1:8000/api/v1 NEXT_TELEMETRY_DISABLED=1' ;;
      pms-worker.service) executable="$APP/current/platform/api/.venv/bin/pms-worker"; working="$CONFIG/worker"; account=$WORKER_USER; supplementary="$SERVICE_USER $MEDIA_GROUP"; unit_umask=0007 ;;
      pms-retention.service) executable="$APP/current/platform/api/.venv/bin/pms-worker --retention"; working="$CONFIG/retention"; account=$RETENTION_USER; supplementary="$SERVICE_USER $MEDIA_GROUP"; unit_umask=0007 ;;
    esac
    cat > "/etc/systemd/system/$unit" <<EOF
# Managed by pms-platform deploy-platform.sh
[Unit]
Description=PMS platform $unit
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=$account
Group=$account
SupplementaryGroups=$supplementary
WorkingDirectory=$working
ExecStart=$executable
$environment
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=full
UMask=$unit_umask

[Install]
WantedBy=multi-user.target
EOF
  done
  systemctl daemon-reload
  systemctl enable "${SERVICES[@]}" >/dev/null
}

stop_services() {
  systemctl stop "${SERVICES[@]}" 2>/dev/null || true
  local unit
  for unit in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$unit"; then
      log "Service $unit is still active; stopping deployment."
      return 1
    fi
  done
  SERVICES_STOPPED=1
}

start_services() {
  systemctl start "${SERVICES[@]}" || return 1
  SERVICES_STOPPED=0
}

unit_listener() {
  local unit=$1 port=$2 pid listeners
  systemctl is-active --quiet "$unit" || return 1
  pid=$(systemctl show -P MainPID "$unit")
  [[ $pid =~ ^[1-9][0-9]*$ ]] || return 1
  listeners=$(ss -H -ltnp "sport = :$port") || return 1
  [[ -n $listeners && $listeners == *"pid=$pid,"* ]]
}

wait_ready() {
  local attempt
  for attempt in {1..40}; do
    if unit_listener pms-api.service 8000 \
      && unit_listener pms-web.service 3000 \
      && systemctl is-active --quiet pms-worker.service \
      && systemctl is-active --quiet pms-retention.service \
      && curl -fsS --max-time 3 -o /dev/null http://127.0.0.1:8000/health/ready \
      && curl -fsS --max-time 3 -o /dev/null 'http://127.0.0.1:3000/health/ready?api_port=8000'; then
      return 0
    fi
    sleep 2
  done
  return 1
}

wait_https_ready() {
  local attempt
  for attempt in {1..15}; do
    if curl -fsS --max-time 3 --resolve "$HOST:443:127.0.0.1" -o /dev/null \
      "https://$HOST/health/ready?api_port=8000" 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

switch_release() {
  local target=$1
  local temporary="$APP/current.next.$$.$RANDOM"
  ln -s "$target" "$temporary"
  mv -Tf "$temporary" "$APP/current"
  SWITCHED=1
}

on_error() {
  local code=$1
  ((RECOVERING == 0)) || return
  RECOVERING=1
  set +e
  log "Deployment failed (exit $code); starting recovery."
  local recovery_ready=0 safe_to_recover=1
  restore_role_configs || { log "Role configuration recovery failed; manual attention is required."; safe_to_recover=0; }
  if ((SERVICES_STOPPED || SWITCHED)); then
    stop_services || { log "A service may still be active; database recovery requires manual attention."; safe_to_recover=0; }
    if [[ -n $OLD_RELEASE ]] && ((safe_to_recover)); then
      if ((SCHEMA_CHANGED && DATABASE_MUTATION)); then
        if ((ALLOW_DATA_LOSS && BACKUP_READY)) && [[ -n $BACKUP_FILE ]]; then
          restore_database "$BACKUP_FILE" "$OLD_RELEASE" || { log "Database restore failed; manual recovery required."; safe_to_recover=0; }
        else
          log "Database revision may have changed. Old code cannot start until a compatible backup is restored."
          safe_to_recover=0
        fi
      fi
      if ((safe_to_recover)); then
        if switch_release "$OLD_RELEASE" && start_services && wait_ready; then
          recovery_ready=1
        else
          log "Old release did not become ready; inspect journalctl."
        fi
      fi
    fi
  else
    recovery_ready=1
  fi
  if ((SITE_CHANGED && recovery_ready)); then
    if [[ -n $SITE_SAVED ]]; then cp -a "$SITE_SAVED" "$SITE"; else rm -f "$SITE" "$SITE_LINK"; fi
    nginx -t >/dev/null && systemctl reload nginx || log "Nginx recovery needs manual attention."
  elif ((SITE_CHANGED)); then
    write_site maintenance || log "Nginx maintenance mode needs manual attention."
  fi
  [[ -z $BACKUP_FILE ]] || log "Database backup: $BACKUP_FILE"
  log "See journalctl -u pms-api -u pms-web -u pms-worker -u pms-retention for service errors."
}

on_exit() {
  local code=$1
  trap - EXIT
  if ((code != 0)); then on_error "$code"; fi
  [[ -z $WORK ]] || rm -rf -- "$WORK"
  exit "$code"
}

if [[ $COMMAND == init-config ]]; then
  init_config
  exit 0
fi
if [[ $COMMAND == setup-key ]]; then
  show_setup_key
  exit 0
fi
if [[ $COMMAND == status ]]; then
  log "Current: $(readlink -f "$APP/current" 2>/dev/null || echo none)"
  log "Previous: $(readlink -f "$APP/previous" 2>/dev/null || echo none)"
  systemctl --no-pager --plain status "${SERVICES[@]}" || true
  exit 0
fi

ensure_user
if [[ $COMMAND == deploy && ( ! -f $CONFIG/api.env || ! -f $CONFIG/migration.url ) ]]; then
  init_config
fi
check_config_files
WORK=$(mktemp -d /run/pms-platform-deploy.XXXXXX)
trap 'on_exit $?' EXIT
prepare_pgpass
sync_role_configs
if [[ -L $APP/current ]]; then OLD_RELEASE=$(readlink -f "$APP/current"); fi
if [[ -n $OLD_RELEASE ]]; then
  [[ $OLD_RELEASE == "$APP/releases/"* && -d $OLD_RELEASE ]] || die "Current release points outside the managed releases directory."
fi

if [[ $COMMAND == rollback ]]; then
  [[ -n $OLD_RELEASE ]] || die "No current release is recorded."
  [[ -L $APP/previous ]] || die "No previous release is recorded."
  NEW_RELEASE=$(readlink -f "$APP/previous")
  [[ $NEW_RELEASE == "$APP/releases/"* && -d $NEW_RELEASE ]] || die "The previous release is missing or outside the managed releases directory."
  local_revision=$(release_revision "$NEW_RELEASE")
  current_revision=$(database_revision)
  if [[ $local_revision != "$current_revision" ]]; then
    [[ -n $RESTORE_BACKUP && $ALLOW_DATA_LOSS == 1 ]] || die "Schema mismatch. Supply the matching --restore-backup and --allow-data-loss."
    [[ -f $RESTORE_BACKUP && ! -L $RESTORE_BACKUP ]] || die "Backup must be a regular file."
    RESTORE_BACKUP=$(realpath -e -- "$RESTORE_BACKUP")
    [[ $(dirname "$RESTORE_BACKUP") == "$BACKUPS" && $(basename "$RESTORE_BACKUP") == pms-platform-*.dump ]] || die "Backup must be directly under $BACKUPS."
    [[ -f $RESTORE_BACKUP.revision && $(cat "$RESTORE_BACKUP.revision") == "$local_revision" ]] || die "Backup revision does not match the previous release."
    SCHEMA_CHANGED=1
  fi
  ensure_certificate
  write_site maintenance
  stop_services
  if ((SCHEMA_CHANGED)); then
    backup_database
    DATABASE_MUTATION=1
    restore_database "$RESTORE_BACKUP" "$NEW_RELEASE"
  fi
  switch_release "$NEW_RELEASE"
  start_services
  wait_ready || die "Previous release failed readiness checks."
  write_site active
  ln -sfn "$OLD_RELEASE" "$APP/previous"
  log "Rollback complete: $NEW_RELEASE"
  exit 0
fi

[[ -f $ARCHIVE ]] || die "Pass --archive with the Windows-built zip."
ARCHIVE=$(realpath "$ARCHIVE")
install_prerequisites
if [[ -z $OLD_RELEASE ]]; then bootstrap_database; fi
NEW_RELEASE="$APP/releases/$(date -u +%Y%m%d-%H%M%S)-$$"
install -d -m 0700 "$NEW_RELEASE"
check_archive_and_extract "$ARCHIVE" "$NEW_RELEASE"
build_release
provision_training_key
validate_runtime
new_revision=$(release_revision "$NEW_RELEASE")
if [[ -n $OLD_RELEASE ]]; then
  old_revision=$(release_revision "$OLD_RELEASE")
  [[ $(database_revision) == "$old_revision" ]] || die "Current database revision differs from the running release; review it before upgrading."
  if [[ $old_revision != "$new_revision" ]]; then
    SCHEMA_CHANGED=1
    ((ALLOW_SCHEMA_UPGRADE && ALLOW_DATA_LOSS)) || die "Schema changes require --allow-schema-upgrade and --allow-data-loss for protected rollback."
  fi
fi
ensure_certificate
write_site maintenance
install_services
stop_services
require_exclusive_database
if ((SCHEMA_CHANGED)); then backup_database; fi
DATABASE_MUTATION=1
migrate_database
backfill_tenant_catalog
grant_roles "$NEW_RELEASE"
switch_release "$NEW_RELEASE"
start_services
wait_ready || die "New release failed API or web readiness checks."
curl -fsS --max-time 5 -o /dev/null http://127.0.0.1:8000/api/v1/training/verification-key \
  || die "Training signing verification failed after API startup."
write_site active
wait_https_ready || die "Public HTTPS readiness check failed after Nginx reload."
if [[ -n $OLD_RELEASE ]]; then ln -sfn "$OLD_RELEASE" "$APP/previous"; fi
log "Deployment complete: $NEW_RELEASE"
log "Public URL: https://$HOST/"
