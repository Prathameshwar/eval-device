"""Plan catalog, platform-managed assignments and organization capacity summaries."""

from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select, text

from pms_api.core.common import now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import Organization, SubscriptionPlan
from pms_api.database.session import lock_administration
from pms_api.modules.common import audit, commit, public
from pms_api.modules.patching import changes, update_fields
from pms_api.modules.schemas import SubscriptionAssignment, SubscriptionPlanPatch
from pms_api.security.access import Actor, human, organization_access, platform_access

router = APIRouter()


def plan_view(row):
    result = public(row)
    # Prices use exact decimal strings, in the named currency's major units.
    result["price_amount"] = format(row.price_amount, ".2f")
    return result


async def active_plan(session, plan_id):
    row = await session.get(SubscriptionPlan, plan_id, populate_existing=True)
    require(
        row is not None and row.is_active,
        "subscription_plan_unavailable",
        "Select an active subscription plan",
        409,
    )
    return row


def subscription_state(organization, at=None):
    at = at or now()
    if organization.subscription_status != "active":
        return organization.subscription_status
    if organization.subscription_ends_at and organization.subscription_ends_at <= at:
        return "expired"
    if organization.subscription_starts_at and organization.subscription_starts_at > at:
        return "scheduled"
    return "active"


async def subscription_view(session, organization, platform=False, at=None):
    plan = required(await session.get(SubscriptionPlan, organization.subscription_plan_id))
    usage = (
        (
            await session.execute(
                text("SELECT * FROM device_platform.subscription_usage(:organization_id)"),
                {"organization_id": organization.id},
            )
        )
        .mappings()
        .one()
    )
    users = usage["active_users"] + usage["pending_invitations"]
    devices = usage["active_devices"]
    return {
        "organization_id": organization.id,
        "organization_name": organization.name,
        "organization_is_active": organization.is_active,
        "organization_archived": organization.archived_at is not None,
        "version": organization.subscription_version,
        "status": organization.subscription_status,
        "state": subscription_state(organization, at),
        "starts_at": organization.subscription_starts_at,
        "ends_at": organization.subscription_ends_at,
        "enforcement": "tracking_only",
        **(
            {"reference": organization.subscription_reference, "notes": organization.subscription_notes}
            if platform
            else {}
        ),
        "subscription_plan_id": plan.id,
        "assigned_at": organization.subscription_assigned_at,
        "plan": plan_view(plan),
        "usage": {
            "active_users": usage["active_users"],
            "pending_invitations": usage["pending_invitations"],
            "users": users,
            "devices": devices,
        },
        "remaining": {"users": max(0, plan.max_users - users), "devices": max(0, plan.max_devices - devices)},
        "over_limit": users > plan.max_users or devices > plan.max_devices,
    }


@router.get("/subscription-plans", tags=["Subscriptions"])
async def available_plans(session: Session, actor: Actor):
    human(actor)
    rows = (
        await session.scalars(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active.is_(True))
            .order_by(SubscriptionPlan.price_amount, SubscriptionPlan.code)
        )
    ).all()
    return {"items": [plan_view(row) for row in rows]}


@router.get("/platform/subscription-plans", tags=["Platform"])
async def platform_plans(session: Session, actor: Actor):
    platform_access(actor, "platform.settings.read")
    rows = (await session.scalars(select(SubscriptionPlan).order_by(SubscriptionPlan.code))).all()
    return {"items": [plan_view(row) for row in rows]}


@router.patch("/platform/subscription-plans/{plan_id}", tags=["Platform"])
async def update_plan(plan_id: UUID, body: SubscriptionPlanPatch, session: Session, actor: Actor):
    platform_access(actor, "platform.settings.manage")
    await lock_administration(session)
    row = await session.get(SubscriptionPlan, plan_id, with_for_update=True)
    require(row is not None, "not_found", "Subscription plan not found", 404)
    assert row is not None
    require(
        row.configuration_version == body.expected_version,
        "version_conflict",
        "Subscription plan changed; refresh before retrying",
        409,
    )
    values = changes(body, {"expected_version"})
    require(bool(values), "no_changes", "Supply at least one plan field")
    before = plan_view(row)
    update_fields(row, values)
    after = plan_view(row)
    await audit(
        session,
        actor,
        "subscription.plan.updated",
        "subscription_plan",
        row.id,
        details={
            "fields": sorted(values),
            "previous_version": body.expected_version,
            "changes": {key: {"before": before[key], "after": after[key]} for key in values},
        },
    )
    await commit(session, row)
    return plan_view(row)


@router.get("/organizations/{organization_id}/subscription", tags=["Subscriptions"])
async def organization_subscription(organization_id: UUID, session: Session, actor: Actor):
    access = await organization_access(
        session, actor, organization_id, "org.settings.read", allow_inactive=True
    )
    return await subscription_view(session, access.organization)


@router.get("/platform/organizations/{organization_id}/subscription", tags=["Platform"])
async def platform_subscription(organization_id: UUID, session: Session, actor: Actor):
    platform_access(actor, "platform.organizations.read")
    row = await session.get(Organization, organization_id)
    require(row is not None, "not_found", "Organization not found", 404)
    return await subscription_view(session, row, platform=True)


@router.put("/platform/organizations/{organization_id}/subscription", tags=["Platform"])
async def assign_subscription(
    organization_id: UUID, body: SubscriptionAssignment, session: Session, actor: Actor
):
    platform_access(actor, "platform.organizations.manage")
    await lock_administration(session)
    row = await session.get(Organization, organization_id, with_for_update=True)
    require(row is not None, "not_found", "Organization not found", 404)
    assert row is not None
    require(
        row.archived_at is None, "state_conflict", "Restore the organization before changing its plan", 409
    )
    require(
        body.expected_version is None or body.expected_version == row.management_version,
        "version_conflict",
        "Organization changed; refresh before retrying",
        409,
    )
    await active_plan(session, body.subscription_plan_id)
    previous = row.subscription_plan_id
    if previous != body.subscription_plan_id:
        row.subscription_plan_id = body.subscription_plan_id
        row.management_version += 1
        await audit(
            session,
            actor,
            "platform.organization.subscription_changed",
            "organization",
            row.id,
            row.id,
            {"previous_plan_id": str(previous), "subscription_plan_id": str(body.subscription_plan_id)},
        )
        await commit(session, row)
    return await subscription_view(session, row, platform=True)
