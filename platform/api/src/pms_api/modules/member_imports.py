"""Tenant-only validate, review and commit workflow for role-specific Excel imports."""

import secrets
from datetime import timedelta
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from pms_api.core.common import AppError, now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import InvitationEmailOutbox, LocalCredential, MemberImport, User
from pms_api.database.session import lock_administration
from pms_api.modules.common import audit
from pms_api.modules.invitation_delivery import queue_invitation
from pms_api.modules.management import create_invitation, validate_department
from pms_api.modules.member_import_passwords import open_passwords, seal
from pms_api.modules.member_workbooks import MIME, parse_workbook, template_bytes, workbook_bytes
from pms_api.modules.schemas import InvitationCreate
from pms_api.modules.subscriptions import subscription_view
from pms_api.security.access import Actor, organization_access
from pms_api.security.local_auth import hash_password

router = APIRouter(prefix="/organizations/{organization_id}/member-imports", tags=["Member imports"])
Role = Literal["org_admin", "org_user", "org_read_only", "org_trainee"]
AuthMethod = Literal["local", "oidc"]


async def access_for(session, actor, organization_id, *, history=False):
    access = await organization_access(
        session, actor, organization_id, "org.members.manage", allow_inactive=history
    )
    require(
        access.department_id is None, "permission_denied", "Tenant-wide member management is required", 403
    )
    return access


def counts(row):
    return {
        "total": len(row.rows),
        "ready": sum(r["status"] == "ready" for r in row.rows),
        "succeeded": sum(r["status"] == "succeeded" for r in row.rows),
        "failed": sum(r["status"] in {"invalid", "failed"} for r in row.rows),
    }


async def view(session, row, settings, *, detail=True):
    result = {
        "id": row.id,
        "role": row.role,
        "auth_method": row.auth_method,
        "department_id": row.department_id,
        "status": row.status,
        "created_at": row.created_at,
        "validated_until": row.validated_until,
        "completed_at": row.completed_at,
        "expires_at": row.expires_at,
        "counts": counts(row),
        "password_count": sum(r["status"] == "succeeded" and r.get("has_password", False) for r in row.rows),
        "email_configured": bool(settings.smtp_host and settings.smtp_sender),
    }
    if detail:
        passwords = open_passwords(row, settings) if row.status == "completed" else {}
        ids = [UUID(r["membership_id"]) for r in row.rows if r["membership_id"]]
        delivery = (
            dict(
                (
                    await session.execute(
                        select(InvitationEmailOutbox.membership_id, InvitationEmailOutbox.status).where(
                            InvitationEmailOutbox.membership_id.in_(ids)
                        )
                    )
                ).all()
            )
            if ids
            else {}
        )
        result["rows"] = [
            {
                **r,
                "password": passwords.get(str(r["row_number"])) if r["status"] == "succeeded" else None,
                "email_status": delivery.get(UUID(r["membership_id"]), "expired")
                if r["membership_id"]
                else None,
            }
            for r in row.rows
        ]
    return result


async def get_import(session, organization_id, import_id):
    return required(
        await session.scalar(
            select(MemberImport).where(
                MemberImport.id == import_id,
                MemberImport.organization_id == organization_id,
                MemberImport.expires_at > now(),
            )
        )
    )


def download(data, name):
    return Response(
        data,
        media_type=MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{name}.xlsx"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/template")
async def template(
    organization_id: UUID,
    role: Role,
    auth_method: AuthMethod,
    session: Session,
    actor: Actor,
    department_id: UUID | None = None,
):
    await access_for(session, actor, organization_id)
    await validate_department(session, organization_id, department_id)
    require(
        role != "org_admin" or department_id is None, "invalid_scope", "Administrators cover the whole tenant"
    )
    return download(
        await run_in_threadpool(template_bytes, role, auth_method, department_id), "member-import-template"
    )


@router.get("")
async def history(organization_id: UUID, request: Request, session: Session, actor: Actor):
    await access_for(session, actor, organization_id, history=True)
    rows = (
        await session.scalars(
            select(MemberImport)
            .where(
                MemberImport.organization_id == organization_id,
                MemberImport.expires_at > now(),
            )
            .order_by(MemberImport.created_at.desc(), MemberImport.id.desc())
            .limit(100)
        )
    ).all()
    return {"items": [await view(session, row, request.app.state.settings, detail=False) for row in rows]}


@router.post("/validate", status_code=201)
async def validate(
    organization_id: UUID,
    role: Role,
    auth_method: AuthMethod,
    request: Request,
    session: Session,
    actor: Actor,
    department_id: UUID | None = None,
):
    await access_for(session, actor, organization_id)
    require(
        request.headers.get("content-type", "").split(";")[0] == MIME,
        "import_file_type",
        "Upload an .xlsx Excel workbook",
    )
    rows = await run_in_threadpool(parse_workbook, await request.body())
    supplied_passwords = {str(row["row_number"]): row.pop("password", "") for row in rows}
    await lock_administration(session)
    access = await access_for(session, actor, organization_id)
    await validate_department(session, organization_id, department_id)
    require(
        role != "org_admin" or department_id is None, "invalid_scope", "Administrators cover the whole tenant"
    )
    settings = request.app.state.settings
    require(
        auth_method != "local" or settings.local_auth_enabled,
        "local_auth_disabled",
        "Local account authentication is disabled",
        409,
    )
    await session.execute(delete(MemberImport).where(MemberImport.expires_at <= now()))
    number = await session.scalar(
        select(func.count())
        .select_from(MemberImport)
        .where(
            MemberImport.organization_id == organization_id,
        )
    )
    require(
        (number or 0) < 100,
        "import_history_limit",
        "This tenant has reached 100 retained imports. Try again after older results expire.",
        429,
    )
    capacity = (await subscription_view(session, access.organization))["remaining"]["users"]
    seen = set()
    for row in rows:
        if row["status"] != "ready":
            continue
        try:
            body = InvitationCreate(
                email=row["email"],
                local_display_name=row["full_name"],
                auth_method=auth_method,
                role=role,
                department_id=department_id,
            )
            require(bool(row["full_name"]), "invalid_name", "Enter a full name.")
            row["email"] = str(body.email).lower()
            password = supplied_passwords[str(row["row_number"])]
            require(
                not password or auth_method == "local",
                "password_auth_method",
                "Passwords are only available for local accounts.",
            )
            require(
                not password or 12 <= len(password) <= 1024,
                "invalid_import_password",
                "Use a password of 12-1024 characters.",
            )
            if password:
                existing_local = await session.scalar(
                    select(User.id).where(func.lower(User.email) == row["email"], User.auth_method == "local")
                )
                require(
                    existing_local is None,
                    "existing_account_password",
                    "This account already exists; leave Password blank to preserve its current password.",
                )
            require(
                row["email"] not in seen,
                "duplicate_email",
                "This email already appears earlier in the workbook.",
            )
            seen.add(row["email"])
            await create_invitation(session, settings, actor, organization_id, body, validate_only=True)
            require(
                capacity > 0,
                "subscription_user_limit",
                "No user seats remain. Increase capacity or free a seat before retrying.",
            )
            capacity -= 1
        except ValidationError:
            row.update(
                status="invalid",
                code="invalid_person",
                message="Enter a full name (1-256 characters) and a valid email address.",
            )
        except AppError as error:
            row.update(status="invalid", code=error.code, message=error.message)
        row["has_password"] = row["status"] == "ready" and bool(supplied_passwords[str(row["row_number"])])
    timestamp = now()
    batch = MemberImport(
        id=uuid4(),
        organization_id=organization_id,
        created_by=actor.id,
        role=role,
        auth_method=auth_method,
        department_id=department_id,
        rows=rows,
        created_at=timestamp,
        validated_until=timestamp + timedelta(hours=24),
        expires_at=timestamp + timedelta(days=30),
    )
    seal(
        batch,
        settings,
        {
            str(row["row_number"]): supplied_passwords[str(row["row_number"])]
            for row in rows
            if row["status"] == "ready" and supplied_passwords[str(row["row_number"])]
        },
    )
    session.add(batch)
    await audit(
        session,
        actor,
        "membership.import.validated",
        "member_import",
        batch.id,
        organization_id,
        details={"role": role, **counts(batch)},
    )
    await session.commit()
    return await view(session, batch, settings)


@router.get("/{import_id}")
async def detail(organization_id: UUID, import_id: UUID, request: Request, session: Session, actor: Actor):
    await access_for(session, actor, organization_id, history=True)
    batch = await get_import(session, organization_id, import_id)
    result = await view(session, batch, request.app.state.settings)
    if batch.status == "completed" and batch.passwords_encrypted is not None:
        await audit(
            session, actor, "membership.import.passwords_viewed", "member_import", batch.id, organization_id
        )
        await session.commit()
    return result


@router.post("/{import_id}/commit")
async def execute(organization_id: UUID, import_id: UUID, request: Request, session: Session, actor: Actor):
    await lock_administration(session)
    access = await access_for(session, actor, organization_id)
    batch = await get_import(session, organization_id, import_id)
    settings = request.app.state.settings
    if batch.status == "completed":
        result = await view(session, batch, settings)
        if batch.passwords_encrypted is not None:
            await audit(
                session,
                actor,
                "membership.import.passwords_viewed",
                "member_import",
                batch.id,
                organization_id,
            )
            await session.commit()
        return result
    require(
        batch.validated_until > now(),
        "import_expired",
        "Validation has expired. Upload and validate the workbook again.",
        409,
    )
    require(
        any(r["status"] == "ready" for r in batch.rows),
        "import_no_valid_rows",
        "Correct the errors and validate a new workbook first.",
        409,
    )
    require(
        batch.auth_method != "local" or settings.local_auth_enabled,
        "local_auth_disabled",
        "Local account authentication is disabled",
        409,
    )
    capacity = (await subscription_view(session, access.organization))["remaining"]["users"]
    supplied_passwords = open_passwords(batch, settings)
    completed_passwords: dict[str, str] = {}
    results = []
    for source in batch.rows:
        row = dict(source)
        if row["status"] == "ready":
            try:
                async with session.begin_nested():
                    require(
                        capacity > 0,
                        "subscription_user_limit",
                        "No user seats remain. Increase capacity or free a seat before retrying.",
                    )
                    body = InvitationCreate(
                        email=row["email"],
                        local_display_name=row["full_name"],
                        auth_method=batch.auth_method,
                        role=batch.role,
                        department_id=batch.department_id,
                    )
                    password = None
                    if batch.auth_method == "local":
                        existing_local = await session.scalar(
                            select(User.id).where(
                                func.lower(User.email) == row["email"], User.auth_method == "local"
                            )
                        )
                        if existing_local is None:
                            password = supplied_passwords.get(
                                str(row["row_number"])
                            ) or secrets.token_urlsafe(24)
                            user = User(
                                id=uuid4(),
                                auth_method="local",
                                identity_issuer=None,
                                identity_subject=None,
                                email=row["email"],
                                # The tenant administrator explicitly provisions this local identity.
                                # Invitation acceptance still requires the separate invitation token.
                                email_verified=True,
                                display_name=row["full_name"],
                                created_by=actor.id,
                            )
                            session.add(user)
                            await session.flush()
                            session.add(
                                LocalCredential(
                                    user_id=user.id,
                                    login_email=row["email"],
                                    password_hash=await hash_password(password),
                                    setup_completed_at=now(),
                                )
                            )
                            await session.flush()
                            await audit(
                                session,
                                actor,
                                "membership.local_user_created",
                                "user",
                                user.id,
                                organization_id,
                            )
                        else:
                            require(
                                str(row["row_number"]) not in supplied_passwords,
                                "existing_account_password",
                                "Existing account passwords are not replaced by an import.",
                            )
                    member, token, _ = await create_invitation(
                        session, settings, actor, organization_id, body
                    )
                    queue_invitation(session, settings, member, token)
                    await session.flush()
                    row.update(
                        status="succeeded",
                        membership_id=str(member.id),
                        code=None,
                        message="Invitation created. Access begins after acceptance.",
                    )
                capacity -= 1
                if password:
                    completed_passwords[str(row["row_number"])] = password
                row["has_password"] = bool(password)
            except AppError as error:
                row.update(status="failed", code=error.code, message=error.message)
            except IntegrityError as error:
                if getattr(error.orig, "sqlstate", None) not in {"23505", "23514", "23503"}:
                    raise
                row.update(
                    status="failed",
                    code="import_conflict",
                    message="The account, membership or available capacity changed. Review the member list and retry this row.",
                )
        results.append(row)
    batch.rows = results
    seal(batch, settings, completed_passwords)
    batch.status = "completed"
    batch.completed_at = now()
    await audit(
        session,
        actor,
        "membership.import.completed",
        "member_import",
        batch.id,
        organization_id,
        details={"role": batch.role, **counts(batch)},
    )
    await session.commit()
    return await view(session, batch, settings)


@router.get("/{import_id}/report")
async def report(
    organization_id: UUID,
    import_id: UUID,
    request: Request,
    session: Session,
    actor: Actor,
    errors_only: bool = True,
    passwords_only: bool = False,
):
    await access_for(session, actor, organization_id, history=True)
    batch = await get_import(session, organization_id, import_id)
    if passwords_only:
        require(batch.status == "completed", "import_not_completed", "Finish the import first", 409)
        passwords = open_passwords(batch, request.app.state.settings)
        await audit(
            session,
            actor,
            "membership.import.passwords_downloaded",
            "member_import",
            batch.id,
            organization_id,
        )
        await session.commit()
        return download(
            await run_in_threadpool(
                workbook_bytes,
                {
                    "Passwords": [("Full name", "Email", "Password")]
                    + [
                        (r["full_name"], r["email"], passwords[str(r["row_number"])])
                        for r in batch.rows
                        if r["status"] == "succeeded" and str(r["row_number"]) in passwords
                    ]
                },
            ),
            "member-import-passwords",
        )
    failed = [r for r in batch.rows if r["status"] in {"invalid", "failed"}]
    rows = failed if errors_only else batch.rows
    data = {
        "Members": [("Full name", "Email")] + [(r["full_name"], r["email"]) for r in failed],
        "Errors" if errors_only else "Results": [
            ("Original row", "Full name", "Email", "Status", "Code", "Message"),
            *[
                (r["row_number"], r["full_name"], r["email"], r["status"], r["code"], r["message"])
                for r in rows
            ],
        ],
    }
    return download(
        await run_in_threadpool(workbook_bytes, data),
        "member-import-errors" if errors_only else "member-import-results",
    )
