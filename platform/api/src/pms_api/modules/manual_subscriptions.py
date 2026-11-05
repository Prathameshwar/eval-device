"""Manual subscription management. Dates/status never authorize or block processing."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime, Field
from sqlalchemy import Text, case, or_, select

from pms_api.core.common import now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import ActivityEvent, Organization
from pms_api.database.session import lock_administration
from pms_api.modules.activity import activity_view
from pms_api.modules.common import audit, commit, directory_page
from pms_api.modules.patching import changes, update_fields
from pms_api.modules.schemas import PeopleInput
from pms_api.modules.subscriptions import active_plan, subscription_view
from pms_api.security.access import Actor, organization_access, platform_access

router = APIRouter()


class ManualSubscriptionPatch(PeopleInput):
    expected_version: int = Field(gt=0, strict=True)
    subscription_plan_id: UUID | None = None
    subscription_status: Literal["active", "suspended", "cancelled"] | None = None
    subscription_starts_at: AwareDatetime | None = None
    subscription_ends_at: AwareDatetime | None = None
    subscription_reference: str | None = Field(None, max_length=256)
    subscription_notes: str | None = Field(None, max_length=2000)


def state_expression(at):
    return case(
        (Organization.subscription_status != "active", Organization.subscription_status),
        (Organization.subscription_ends_at <= at, "expired"),
        (Organization.subscription_starts_at > at, "scheduled"),
        else_="active",
    )


@router.get("/platform/subscriptions", tags=["Subscriptions"])
async def subscription_directory(
    request: Request,
    session: Session,
    actor: Actor,
    q: Annotated[str | None, Query(max_length=128)] = None,
    state: Literal["all", "active", "scheduled", "expired", "suspended", "cancelled"] = "all",
    plan_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: str | None = None,
):
    platform_access(actor, "platform.organizations.read")
    query = select(Organization).where(Organization.archived_at.is_(None))
    if q:
        query = query.where(
            or_(
                Organization.name.icontains(q, autoescape=True),
                Organization.id.cast(Text).icontains(q, autoescape=True),
            )
        )
    at = now()
    if state != "all":
        query = query.where(state_expression(at) == state)
    if plan_id:
        query = query.where(Organization.subscription_plan_id == plan_id)
    rows, next_cursor, has_more, total = await directory_page(
        session,
        query,
        Organization,
        limit=limit,
        cursor=cursor,
        sort="name",
        direction="asc",
        expression=Organization.name,
        kind="string",
        binding=f"subscriptions|{q}|{state}|{plan_id}",
        secret=request.app.state.settings.token_pepper.get_secret_value(),
        include_total=True,
    )
    # Bounded page; plan objects are identity-map cached, usage is authoritative SQL.
    return {
        "items": [await subscription_view(session, row, platform=True, at=at) for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "total": total,
    }


@router.patch("/platform/organizations/{organization_id}/subscription", tags=["Subscriptions"])
async def edit_subscription(
    organization_id: UUID,
    body: ManualSubscriptionPatch,
    session: Session,
    actor: Actor,
):
    platform_access(actor, "platform.organizations.manage")
    await lock_administration(session)
    row = required(await session.get(Organization, organization_id, with_for_update=True))
    require(
        row.archived_at is None, "state_conflict", "Restore the tenant before editing its subscription", 409
    )
    require(
        body.expected_version == row.subscription_version,
        "version_conflict",
        "Subscription changed; refresh before retrying",
        409,
    )
    values = changes(body, {"expected_version"})
    require(bool(values), "no_changes", "Supply at least one subscription field")
    start = values.get("subscription_starts_at", row.subscription_starts_at)
    end = values.get("subscription_ends_at", row.subscription_ends_at)
    require(
        start is None or end is None or end > start,
        "subscription_dates_invalid",
        "The end must be after the start",
    )
    if "subscription_plan_id" in values:
        require(values["subscription_plan_id"] is not None, "null_not_allowed", "A plan is required")
        if values["subscription_plan_id"] != row.subscription_plan_id:
            await active_plan(session, values["subscription_plan_id"])
    values = {key: value for key, value in values.items() if value != getattr(row, key)}
    if values:
        # Notes/reference remain platform-private, including in retained audits.
        safe = {
            key: {"before": getattr(row, key), "after": value}
            for key, value in values.items()
            if key not in {"subscription_reference", "subscription_notes"}
        }
        update_fields(row, values)
        row.management_version += 1
        await audit(
            session,
            actor,
            "platform.organization.subscription_updated",
            "organization",
            row.id,
            row.id,
            {"fields": sorted(values), "previous_version": body.expected_version, "changes": safe},
        )
        await commit(session, row)
    return await subscription_view(session, row, platform=True)


async def history(session, request, organization_id, limit, cursor):
    query = select(ActivityEvent).where(
        ActivityEvent.organization_id == organization_id,
        ActivityEvent.category == "audit",
        ActivityEvent.event_type.in_(
            ("platform.organization.subscription_updated", "platform.organization.subscription_changed")
        ),
        ActivityEvent.expires_at > now(),
    )
    rows, next_cursor, has_more, total = await directory_page(
        session,
        query,
        ActivityEvent,
        limit=limit,
        cursor=cursor,
        sort="occurred_at",
        direction="desc",
        expression=ActivityEvent.occurred_at,
        kind="datetime",
        binding=f"subscription-history|{organization_id}",
        secret=request.app.state.settings.token_pepper.get_secret_value(),
        include_total=True,
    )
    return {
        "items": [activity_view(row) for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "total": total,
    }


@router.get("/platform/organizations/{organization_id}/subscription/history", tags=["Subscriptions"])
async def platform_history(
    organization_id: UUID,
    request: Request,
    session: Session,
    actor: Actor,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: str | None = None,
):
    platform_access(actor, "platform.organizations.read")
    required(await session.get(Organization, organization_id))
    return await history(session, request, organization_id, limit, cursor)


@router.get("/organizations/{organization_id}/subscription/history", tags=["Subscriptions"])
async def tenant_history(
    organization_id: UUID,
    request: Request,
    session: Session,
    actor: Actor,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: str | None = None,
):
    access = await organization_access(
        session, actor, organization_id, "org.settings.read", allow_inactive=True
    )
    require(access.department_id is None, "permission_denied", "Tenant-wide access is required", 403)
    return await history(session, request, organization_id, limit, cursor)
