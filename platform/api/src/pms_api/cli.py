import argparse
import asyncio
import base64
import json
import os
import secrets
import sys
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import select

from pms_api.core.common import AppError, now, require, required
from pms_api.core.config import Settings
from pms_api.database.models import LocalCredential, User
from pms_api.database.session import engine_for, lock_administration, sessions_for
from pms_api.integrations.vault import CredentialVault
from pms_api.modules.common import audit
from pms_api.modules.schemas import LocalUserCreate
from pms_api.security.local_auth import create_action_token, hash_password, normalize_email


def configure_event_loop():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def selector_loop_factory(use_subprocess=False):
    return asyncio.SelectorEventLoop()


def serve():
    configure_event_loop()
    import uvicorn

    from pms_api.core.logging import configure_logging
    from pms_api.security.training_keys import TrainingKeyError, load_training_key, prepare_local_training

    configure_logging()
    settings = Settings()
    try:
        if settings.environment == "local":
            prepare_local_training(Path(".env"))
        elif settings.training_key_file is not None:
            load_training_key(settings.training_key_file)
    except TrainingKeyError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    uvicorn.run(
        "pms_api.main:create_app",
        factory=True,
        loop="pms_api.cli:selector_loop_factory" if sys.platform == "win32" else "auto",
        host=settings.bind_host,
        port=settings.port,
        access_log=False,
        log_config=None,
    )


def migration_config():
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini")) if (root / "alembic.ini").exists() else Config()
    from importlib.resources import files

    path = root / "migrations" if (root / "migrations").exists() else files("pms_api").joinpath("migrations")
    config.set_main_option("script_location", str(path))
    return config


async def bootstrap(args):
    settings = Settings()
    engine = engine_for(settings, "migration")
    sessions = sessions_for(engine)
    try:
        async with sessions() as session:
            await lock_administration(session)
            require(
                args.verified_identity,
                "verify_identity",
                "Deployment operator must verify the issuer and subject first",
            )
            require(
                not await session.scalar(
                    select(User.id).where(User.platform_role == "platform_admin").limit(1)
                ),
                "bootstrap_completed",
                "Use the audited administrator API after bootstrap",
                409,
            )
            user = await session.scalar(
                select(User).where(User.identity_issuer == args.issuer, User.identity_subject == args.subject)
            )
            if user is None:
                user = User(
                    id=uuid4(),
                    identity_issuer=args.issuer,
                    identity_subject=args.subject,
                    email=args.email,
                    email_verified=True,
                    display_name=args.name,
                    platform_role="platform_admin",
                )
                session.add(user)
            else:
                user.platform_role = "platform_admin"
                user.is_active = True
            await session.flush()
            await audit(
                session,
                None,
                "platform.admin_bootstrapped",
                "user",
                user.id,
                details={"source": "trusted_deployment"},
            )
            await session.commit()
            print("First platform administrator provisioned.")
    finally:
        await engine.dispose()


async def bootstrap_local(args):
    settings = Settings()
    require(settings.local_auth_enabled, "local_auth_disabled", "Enable local authentication first")
    password_stdin = getattr(args, "local_password_stdin", False)
    require(
        not password_stdin or settings.environment == "local",
        "local_environment_required",
        "Password bootstrap without email is available only in the local environment",
    )
    require(
        password_stdin or bool(settings.smtp_host and settings.smtp_sender),
        "account_delivery_unavailable",
        "Configure SMTP before creating the local administrator",
    )
    require(
        args.verified_operator,
        "verify_operator",
        "Deployment operator approval is required",
    )
    try:
        identity = LocalUserCreate(email=args.email, display_name=args.name)
    except ValidationError:
        raise AppError(422, "invalid_admin_identity", "Enter a valid administrator name and email") from None
    password_hash = None
    if password_stdin:
        require(not sys.stdin.isatty(), "password_input_required", "Pipe the local password through stdin")
        # Bound input before hashing; never put a password in command arguments or output.
        password = sys.stdin.read(1027).removesuffix("\n").removesuffix("\r")
        password_hash = await hash_password(password)
    engine = engine_for(settings, "migration")
    sessions = sessions_for(engine)
    try:
        async with sessions() as session:
            await lock_administration(session)
            require(
                not await session.scalar(
                    select(User.id).where(User.platform_role == "platform_admin").limit(1)
                ),
                "bootstrap_completed",
                "Use the audited administrator API after bootstrap",
                409,
            )
            email = normalize_email(str(identity.email))
            require(
                not await session.scalar(
                    select(LocalCredential.user_id).where(LocalCredential.login_email == email)
                ),
                "local_identity_exists",
                "A local account already uses this email",
                409,
            )
            user = User(
                id=uuid4(),
                auth_method="local",
                identity_issuer=None,
                identity_subject=None,
                email=email,
                email_verified=password_stdin,
                display_name=identity.display_name,
                platform_role="platform_admin",
            )
            session.add(user)
            await session.flush()
            session.add(
                LocalCredential(
                    user_id=user.id,
                    login_email=email,
                    password_hash=password_hash,
                    setup_completed_at=now() if password_stdin else None,
                )
            )
            await session.flush()
            if not password_stdin:
                await create_action_token(session, settings, user, "setup")
            await audit(
                session,
                None,
                "platform.local_admin_bootstrapped",
                "user",
                user.id,
                details={"source": "local_development" if password_stdin else "trusted_deployment"},
            )
            await session.commit()
            print(
                "First local platform administrator provisioned with the supplied development password."
                if password_stdin
                else "First local platform administrator provisioned; setup email queued."
            )
    finally:
        await engine.dispose()


async def rotate():
    settings = Settings()
    vault = CredentialVault(settings)
    vault.key(settings.active_credential_key)
    engine = engine_for(settings)
    sessions = sessions_for(engine)
    count = 0
    try:
        from pms_api.database.models import RuntimeModel

        for connection_model in (RuntimeModel,):
            while True:
                async with sessions() as session:
                    rows = (
                        await session.scalars(
                            select(connection_model)
                            .where(
                                connection_model.encrypted_credentials.is_not(None),
                                connection_model.credential_key_id != settings.active_credential_key,
                            )
                            .limit(50)
                            .with_for_update()
                        )
                    ).all()
                    if not rows:
                        break
                    for row in rows:
                        payload = vault.decrypt(row)
                        row.encrypted_credentials, row.credential_key_id = vault.encrypt(
                            getattr(row, "credential_owner_org", None) or row.organization_id,
                            getattr(row, "credential_owner_id", None) or row.id,
                            payload,
                        )
                        await audit(
                            session,
                            None,
                            "connection.credentials_reencrypted",
                            "connection",
                            row.id,
                            row.organization_id,
                        )
                    await session.commit()
                    count += len(rows)
        print(f"Reencrypted credentials for {count} models.")
    finally:
        await engine.dispose()


def adopt():
    from psycopg import sql
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    from pms_api.database.verification import verify_baseline

    settings = Settings()
    # Use the same URL parsing as migrations, preserving spaces and escaped query
    # options instead of re-encoding a SQLAlchemy URL as a libpq URI.
    engine = create_engine(
        (settings.migration_database_url or settings.database_url).get_secret_value(),
        isolation_level="READ COMMITTED",
        poolclass=NullPool,
    )
    try:
        with engine.begin() as transaction:
            connection = transaction.connection.driver_connection
            assert connection is not None
            connection.execute("SELECT pg_advisory_xact_lock(hashtext('pms_migrations'))")
            if required(connection.execute("SELECT to_regclass('public.alembic_version')").fetchone())[0]:
                raise RuntimeError("Database already has Alembic history")
            tables = connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='device_platform' ORDER BY tablename"
            ).fetchall()
            if not tables:
                raise RuntimeError("Use migrate for an empty database")
            connection.execute(
                sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(
                    sql.SQL(",").join(sql.Identifier("device_platform", name[0]) for name in tables)
                )
            )
            verify_baseline(connection)
            connection.execute(
                "CREATE TABLE public.alembic_version (version_num varchar(32) NOT NULL PRIMARY KEY)"
            )
            connection.execute("INSERT INTO public.alembic_version VALUES ('0001_baseline')")
    finally:
        engine.dispose()
    print("Verified SQL baseline adopted. Run pms-admin migrate to apply later migrations.")


def init_local(path):
    from training_contracts.privacy import private_directory

    from pms_api.security.training_keys import ensure_training_configuration

    path = Path(path)
    if path.exists():
        raise RuntimeError("Refusing to overwrite an existing environment file")
    key = base64.b64encode(secrets.token_bytes(32)).decode()
    text = "\n".join(
        [
            "PMS_ENVIRONMENT=local",
            "PMS_DATABASE_URL=postgresql+psycopg://pms_api@127.0.0.1:5432/device_platform",
            "PMS_TOKEN_PEPPER=" + secrets.token_urlsafe(48),
            "PMS_MEDIA_SIGNING_KEY=" + secrets.token_urlsafe(48),
            "PMS_LOCAL_AUTH_ENABLED=true",
            "# Paste this private installation key into the web setup wizard once.",
            "PMS_INITIAL_SETUP_KEY=" + secrets.token_urlsafe(48),
            "PMS_LOCAL_TOKEN_SIGNING_KEY=" + secrets.token_urlsafe(48),
            "PMS_ACTIVE_CREDENTIAL_KEY=local-v1",
            "PMS_CREDENTIAL_KEYS=" + json.dumps({"local-v1": key}),
            "PMS_EXTERNAL_CALLS_ENABLED=false",
            "PMS_STORAGE_BACKEND=local",
            "PMS_EXPOSE_DOCS=true",
            "",
        ]
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        private_directory(path)
        output.write(text)
    ensure_training_configuration(path)
    print(
        "Created local environment file. Configure the database, then open the web setup wizard; keep this file private."
    )


def admin():
    configure_event_loop()
    parser = argparse.ArgumentParser(description="Trusted PMS deployment administration")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate")
    initialize = commands.add_parser(
        "init-database", help="Create a missing database, then apply migrations and defaults"
    )
    initialize.add_argument("--maintenance-database", default="postgres")
    commands.add_parser("adopt-baseline")
    commands.add_parser("rotate-credentials")
    tenant_backfill = commands.add_parser(
        "tenant-catalog-backfill",
        help="Inspect or copy currently selected legacy cases into inactive tenant catalogs",
    )
    tenant_backfill.add_argument("--apply", action="store_true", help="Write the reviewed backfill")
    tenant_backfill.add_argument("--confirmed-backup", action="store_true")
    tenant_backfill.add_argument("--confirmed-write-pause", action="store_true")
    tenant_backfill.add_argument("--after-organization", type=UUID)
    tenant_backfill.add_argument("--limit-organizations", type=int, default=25)
    local = commands.add_parser("init-local")
    local.add_argument("--path", default=".env")
    training = commands.add_parser(
        "init-training", help="Provision training signing once; preserve existing keys"
    )
    training.add_argument("--env-file", type=Path, default=Path(".env"))
    training.add_argument("--default-key", type=Path)
    training.add_argument("--runtime-directory", type=Path)
    training.add_argument("--key-group", help="Unix API group for a newly generated private key")
    boot = commands.add_parser("bootstrap-admin")
    for name in ("issuer", "subject", "email", "name"):
        boot.add_argument("--" + name, required=True)
    boot.add_argument("--verified-identity", action="store_true")
    local_boot = commands.add_parser("bootstrap-local-admin")
    local_boot.add_argument("--email", required=True)
    local_boot.add_argument("--name", required=True)
    local_boot.add_argument("--verified-operator", action="store_true")
    local_boot.add_argument(
        "--local-password-stdin",
        action="store_true",
        help="Local environment only: read the first administrator password from stdin without SMTP",
    )
    args = parser.parse_args()
    if args.command == "init-training":
        from pms_api.security.training_keys import TrainingKeyError, ensure_training_configuration

        try:
            ensure_training_configuration(
                args.env_file,
                default_key=args.default_key,
                runtime_directory=args.runtime_directory,
                key_group=args.key_group,
            )
        except TrainingKeyError as error:
            print(str(error), file=sys.stderr)
            raise SystemExit(1) from None
        print("Training signing key ready; existing signing identity preserved.")
    elif args.command == "migrate":
        command.upgrade(migration_config(), "head")
    elif args.command == "init-database":
        from pms_api.database.initialization import initialize_database

        try:
            created = initialize_database(
                Settings(), lambda: command.upgrade(migration_config(), "head"), args.maintenance_database
            )
        except ValueError:
            print(
                "Invalid initialization settings. Configure the deployment-owner URL and a dedicated database; adopt an existing SQL baseline before upgrading.",
                file=sys.stderr,
            )
            raise SystemExit(1) from None
        except Exception as error:
            # Never print a DSN, provider credentials or raw database exception details.
            print(
                f"Database initialization failed ({type(error).__name__}); check owner access and database state.",
                file=sys.stderr,
            )
            raise SystemExit(1) from None
        print(
            "Database created and initialized."
            if created
            else "Existing database upgraded; existing records preserved."
        )
    elif args.command == "adopt-baseline":
        adopt()
    elif args.command == "rotate-credentials":
        asyncio.run(rotate())
    elif args.command == "tenant-catalog-backfill":
        from pms_api.database.tenant_catalog_backfill import backfill

        if args.apply and not (args.confirmed_backup and args.confirmed_write_pause):
            parser.error("--apply requires --confirmed-backup and --confirmed-write-pause")
        try:
            rows = backfill(
                Settings(),
                apply=args.apply,
                after=args.after_organization,
                limit=args.limit_organizations,
            )
        except Exception as error:
            print(
                f"Tenant catalog backfill failed ({type(error).__name__}); no document was printed."
                " Review database state and retry only after correction.",
                file=sys.stderr,
            )
            raise SystemExit(1) from None
        for row in rows:
            print(
                f"organization={row.organization_id} selections={row.selections} "
                f"legacy={row.legacy_selections} mapped={row.mapped_selections} "
                f"specialties={row.specialties} profiles={row.profiles} cases={row.cases}"
            )
        print(f"{'Applied' if args.apply else 'Dry run'}: {len(rows)} organizations.")
        if len(rows) == args.limit_organizations:
            print(f"Resume with --after-organization {rows[-1].organization_id}")
    elif args.command == "bootstrap-admin":
        asyncio.run(bootstrap(args))
    elif args.command == "bootstrap-local-admin":
        asyncio.run(bootstrap_local(args))
    else:
        init_local(args.path)


if __name__ == "__main__":
    admin()
