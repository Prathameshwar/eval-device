"""Platform administration of tenant memberships, without tenant content access."""

from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from pydantic import Field
from sqlalchemy import and_, func, or_, select

from pms_api.core.common import now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import LocalCredential, Membership, Organization, User
from pms_api.database.session import lock_administration
from pms_api.modules.common import audit, commit, directory_page
from pms_api.modules.management import (
    archive_membership_record,
    check_version,
    member_view,
    restore_membership_record,
    update_membership_record,
)
from pms_api.modules.schemas import HumanRole, MembershipPatch, PeopleInput, Restore
from pms_api.security.access import Actor, platform_access

router = APIRouter(prefix="/platform/organizations/{organization_id}", tags=["Platform"])


class MemberAssignment(PeopleInput):
    user_id: UUID
    role: HumanRole


class MemberUpdate(MembershipPatch):
    expected_version: int = Field(gt=0)


async def tenant_access(session, actor, organization_id, write=False):
    platform_access(actor, "platform.organizations.manage" if write else "platform.organizations.read")
    platform_access(actor, "platform.users.manage" if write else "platform.users.read")
    if write:
        await lock_administration(session)
    org = required(await session.get(Organization, organization_id))
    if write:
        require(org.archived_at is None, "organization_archived", "Restore this tenant first", 409)
    return org


def administrator_access(actor, *roles):
    if "org_admin" in roles:
        platform_access(actor, "platform.organization_admins.manage")


async def tenant_member(session, organization_id, membership_id):
    return required(
        await session.scalar(
            select(Membership)
            .where(
                Membership.id == membership_id,
                Membership.organization_id == organization_id,
            )
            .with_for_update()
        )
    )


@router.get("/members")
async def members(
    organization_id: UUID,
    request: Request,
    session: Session,
    actor: Actor,
    q: Annotated[str, Query(max_length=128)] = "",
    state: Literal["current", "all", "archived", "enabled", "disabled", "pending"] = "current",
    role: HumanRole | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    cursor: str | None = None,
):
    await tenant_access(session, actor, organization_id)
    query = (
        select(Membership)
        .outerjoin(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id == organization_id,
        )
    )
    if state != "all":
        query = query.where(
            Membership.archived_at.is_not(None) if state == "archived" else Membership.archived_at.is_(None)
        )
    if state in {"enabled", "disabled"}:
        query = query.where(
            Membership.invitation_status == "accepted", Membership.is_active == (state == "enabled")
        )
    if state == "pending":
        query = query.where(
            Membership.invitation_status == "pending", Membership.invitation_expires_at > now()
        )
    if role:
        query = query.where(Membership.role == role)
    if q:
        query = query.where(
            or_(
                User.display_name.icontains(q, autoescape=True),
                User.email.icontains(q, autoescape=True),
                Membership.invited_email.icontains(q, autoescape=True),
            )
        )
    rows, next_cursor, has_more, total = await directory_page(
        session,
        query,
        Membership,
        limit=limit,
        cursor=cursor,
        sort="name",
        direction="asc",
        expression=func.coalesce(User.display_name, Membership.invited_email, ""),
        binding=f"platform-members|{organization_id}|{q}|{role}|{state}",
        secret=request.app.state.settings.token_pepper.get_secret_value(),
        kind="string",
        include_total=True,
    )
    return {
        "items": [await member_view(session, row) for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "total": total,
    }


@router.get("/member-candidates")
async def candidates(
    organization_id: UUID,
    session: Session,
    actor: Actor,
    q: Annotated[str, Query(min_length=1, max_length=128)],
):
    await tenant_access(session, actor, organization_id)
    linked = (
        select(Membership.id)
        .where(
            Membership.organization_id == organization_id,
            or_(
                Membership.user_id == User.id,
                and_(
                    func.lower(Membership.invited_email) == func.lower(User.email),
                    Membership.invitation_status == "pending",
                    or_(
                        Membership.invitation_auth_method.is_(None),
                        Membership.invitation_auth_method == User.auth_method,
                    ),
                ),
            ),
        )
        .exists()
    )
    query = (
        select(User)
        .outerjoin(LocalCredential, LocalCredential.user_id == User.id)
        .where(
            User.is_active.is_(True),
            User.archived_at.is_(None),
            or_(User.auth_method != "local", LocalCredential.setup_completed_at.is_not(None)),
            or_(User.display_name.icontains(q, autoescape=True), User.email.icontains(q, autoescape=True)),
            ~linked,
        )
        .order_by(User.display_name, User.id)
        .limit(26)
    )
    rows = (await session.scalars(query)).all()
    return {
        "items": [{"id": row.id, "display_name": row.display_name, "email": row.email} for row in rows[:25]],
        "has_more": len(rows) > 25,
    }


@router.post("/members", status_code=201)
async def assign(organization_id: UUID, body: MemberAssignment, session: Session, actor: Actor):
    await tenant_access(session, actor, organization_id, True)
    administrator_access(actor, body.role)
    user = required(await session.get(User, body.user_id))
    require(
        user.is_active and user.archived_at is None,
        "membership_account_inactive",
        "Enable the account first",
        409,
    )
    if user.auth_method == "local":
        credential = await session.get(LocalCredential, user.id)
        require(
            credential and credential.setup_completed_at is not None,
            "account_setup_required",
            "Complete account setup first",
            409,
        )
    existing = await session.scalar(
        select(Membership.id).where(
            Membership.organization_id == organization_id,
            or_(
                Membership.user_id == user.id,
                and_(
                    func.lower(Membership.invited_email) == user.email.lower(),
                    Membership.invitation_status == "pending",
                    or_(
                        Membership.invitation_auth_method.is_(None),
                        Membership.invitation_auth_method == user.auth_method,
                    ),
                ),
            ),
        )
    )
    require(
        existing is None,
        "membership_exists",
        "This account is already associated; manage its membership instead",
        409,
    )
    row = Membership(
        id=uuid4(),
        organization_id=organization_id,
        user_id=user.id,
        role=body.role,
        department_id=None,
        is_active=True,
        invitation_status="accepted",
        joined_at=now(),
        created_by=actor.id,
    )
    session.add(row)
    await audit(
        session,
        actor,
        "platform.membership.assigned",
        "membership",
        row.id,
        organization_id,
        {"role": body.role},
    )
    await commit(session, row)
    return await member_view(session, row)


@router.patch("/members/{membership_id}")
async def update(
    organization_id: UUID, membership_id: UUID, body: MemberUpdate, session: Session, actor: Actor
):
    await tenant_access(session, actor, organization_id, True)
    row = await tenant_member(session, organization_id, membership_id)
    administrator_access(actor, row.role, body.role)
    return await update_membership_record(organization_id, row, body, session, actor)


@router.delete("/members/{membership_id}")
async def remove(
    organization_id: UUID,
    membership_id: UUID,
    session: Session,
    actor: Actor,
    expected_version: Annotated[int, Query(gt=0)],
):
    await tenant_access(session, actor, organization_id, True)
    row = await tenant_member(session, organization_id, membership_id)
    administrator_access(actor, row.role)
    return await archive_membership_record(organization_id, row, session, actor, expected_version)


@router.post("/members/{membership_id}/restore")
async def restore(organization_id: UUID, membership_id: UUID, body: Restore, session: Session, actor: Actor):
    await tenant_access(session, actor, organization_id, True)
    row = await tenant_member(session, organization_id, membership_id)
    administrator_access(actor, row.role)
    check_version(row, body.expected_version)
    if row.invitation_status != "accepted":
        require(
            row.archived_at is not None and row.user_id is not None,
            "state_conflict",
            "Select an archived account membership",
            409,
        )
        user = required(await session.get(User, row.user_id))
        require(
            user.is_active and user.archived_at is None,
            "membership_account_inactive",
            "Enable the account first",
            409,
        )
        if user.auth_method == "local":
            credential = await session.get(LocalCredential, user.id)
            require(
                credential and credential.setup_completed_at is not None,
                "account_setup_required",
                "Complete account setup first",
                409,
            )
        # Platform restoration explicitly re-associates an existing identity. The
        # membership still remains disabled until separately enabled.
        row.invitation_status = "accepted"
        row.invitation_token_hash = None
        row.joined_at = row.joined_at or now()
    return await restore_membership_record(organization_id, row, body, session, actor)
