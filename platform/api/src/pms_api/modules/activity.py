"""Read-only retained audit/activity directories. Payloads are metadata, never media."""

import json
import re
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import String, cast, or_, select

from pms_api.core.common import now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import ActivityEvent
from pms_api.modules.common import directory_page, public
from pms_api.security.access import Actor, organization_access, platform_access, scoped_query

router = APIRouter()

# Audit producers emit structured state/code/metric fields. Unknown fields are
# intentionally omitted: adding a producer payload does not grant readers access
# to provider credentials, prompts, recordings or transcript content.
DETAIL_KEYS = frozenset(
    {
        "subscription_status",
        "subscription_starts_at",
        "subscription_ends_at",
        "target_organization_id",
        "replacement_device_id",
        "source_organization_id",
        "previous_device_id",
        "actor_role",
        "scope",
        "code",
        "historical",
        "status",
        "submission_status",
        "cleanup_status",
        "playback_status",
        "fields",
        "method",
        "source",
        "operation",
        "outcome",
        "reason",
        "valid",
        "revision",
        "version",
        "previous_version",
        "pack_version",
        "credentials_rotated",
        "duration_ms",
        "provider_calls",
        "answer_source",
        "language",
        "template_id",
        "template_revision",
        "source_draft_id",
        "source_draft_revision",
        "subscription_plan_id",
        "previous_plan_id",
        "changes",
        "before",
        "after",
        "default",
        "is_active",
        "role",
        "department_id",
        "max_users",
        "max_devices",
        "user_limit",
        "device_limit",
    }
)
UNSAFE_TEXT = re.compile(
    r"https?://|\bBearer\s|\b(?:web_|act_|inv_|sk-)[A-Za-z0-9_-]{12,}|\beyJ[A-Za-z0-9_-]+\.", re.I
)


def activity_view(row):
    redacted = False

    def clean(value, depth=0):
        nonlocal redacted
        if depth > 6:
            redacted = True
            return "[omitted]"
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key not in DETAIL_KEYS:
                    redacted = True
                    continue
                result[key] = clean(item, depth + 1)
            return result
        if isinstance(value, list):
            redacted |= len(value) > 100
            return [clean(item, depth + 1) for item in value[:100]]
        if isinstance(value, str) and (len(value) > 512 or UNSAFE_TEXT.search(value)):
            redacted = True
            return "[omitted]"
        return value

    result = public(row)
    result["details"] = clean(row.details)
    result["details_redacted"] = redacted
    return result


class ActivityFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["audit", "operational", "all"] | None = None
    q: str | None = Field(None, max_length=128)
    severity: Literal["info", "warning", "error"] | None = None
    actor_type: Literal["user", "device", "system"] | None = None
    organization_id: UUID | None = None
    department_id: UUID | None = None
    device_id: UUID | None = None
    actor_user_id: UUID | None = None
    entity_id: UUID | None = None
    run_id: UUID | None = None
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None
    sort_by: Literal["id", "occurred_at", "received_at", "event_type", "severity"] = "id"
    sort_order: Literal["asc", "desc"] = "asc"
    limit: int = Field(50, ge=1, le=100)
    cursor: str | None = Field(None, max_length=4096)
    include_total: bool = False

    @field_validator("q")
    @classmethod
    def search_text(cls, value):
        if value is not None and ("\x00" in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value)):
            raise ValueError("Use valid search text")
        return value.strip() if value else None


async def activity_page(request, session, query, filters, binding, category):
    require(
        not filters.since or not filters.until or filters.since < filters.until,
        "invalid_date_range",
        "The start must be before the end",
        422,
    )
    query = query.where(ActivityEvent.expires_at > now())
    if category != "all":
        query = query.where(ActivityEvent.category == category)
    for key in (
        "organization_id",
        "department_id",
        "device_id",
        "actor_user_id",
        "entity_id",
        "run_id",
        "severity",
        "actor_type",
    ):
        value = getattr(filters, key)
        if value is not None:
            query = query.where(getattr(ActivityEvent, key) == value)
    if filters.q:
        # Searching payload contents would reveal hidden data through result counts.
        query = query.where(
            or_(
                ActivityEvent.event_type.icontains(filters.q, autoescape=True),
                ActivityEvent.entity_type.icontains(filters.q, autoescape=True),
                cast(ActivityEvent.id, String).icontains(filters.q, autoescape=True),
            )
        )
    if filters.since:
        query = query.where(ActivityEvent.occurred_at >= filters.since)
    if filters.until:
        query = query.where(ActivityEvent.occurred_at < filters.until)
    binding += "|" + json.dumps(
        filters.model_dump(mode="json", exclude={"cursor", "limit", "include_total"}), sort_keys=True
    )
    rows, next_cursor, has_more, total = await directory_page(
        session,
        query,
        ActivityEvent,
        limit=filters.limit,
        cursor=filters.cursor,
        sort=filters.sort_by,
        direction=filters.sort_order,
        expression=getattr(ActivityEvent, filters.sort_by),
        binding=binding,
        secret=request.app.state.settings.token_pepper.get_secret_value(),
        kind="uuid"
        if filters.sort_by == "id"
        else "datetime"
        if filters.sort_by.endswith("_at")
        else "string",
        include_total=filters.include_total,
        legacy_id=True,
    )
    return {
        "items": [activity_view(row) for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        **({"total": total} if filters.include_total else {}),
    }


@router.get("/platform/audit", tags=["Platform"])
async def platform_audit(
    request: Request, session: Session, actor: Actor, filters: Annotated[ActivityFilters, Query()]
):
    platform_access(actor, "platform.audit.read")
    require(
        filters.category in {None, "audit"},
        "permission_denied",
        "Platform access covers audit events only",
        403,
    )
    return await activity_page(request, session, select(ActivityEvent), filters, "platform-audit", "audit")


@router.get("/platform/audit/{event_id}", tags=["Platform"])
async def platform_audit_detail(event_id: UUID, session: Session, actor: Actor):
    platform_access(actor, "platform.audit.read")
    row = required(
        await session.scalar(
            select(ActivityEvent).where(
                ActivityEvent.id == event_id,
                ActivityEvent.category == "audit",
                ActivityEvent.expires_at > now(),
            )
        )
    )
    return activity_view(row)


@router.get("/organizations/{organization_id}/activities", tags=["Activity"])
async def activities(
    organization_id: UUID,
    request: Request,
    session: Session,
    actor: Actor,
    filters: Annotated[ActivityFilters, Query()],
):
    category = filters.category or "operational"
    access = await organization_access(
        session, actor, organization_id, "org.audit.read" if category == "audit" else "org.activity.read"
    )
    if category == "all":
        await organization_access(session, actor, organization_id, "org.audit.read")
    return await activity_page(
        request,
        session,
        scoped_query(ActivityEvent, access),
        filters,
        f"activities|{organization_id}|{access.department_id}",
        category,
    )


@router.get("/organizations/{organization_id}/activities/{event_id}", tags=["Activity"])
async def activity_detail(organization_id: UUID, event_id: UUID, session: Session, actor: Actor):
    row = required(
        await session.scalar(
            select(ActivityEvent).where(
                ActivityEvent.id == event_id,
                ActivityEvent.organization_id == organization_id,
                ActivityEvent.expires_at > now(),
            )
        )
    )
    access = await organization_access(
        session, actor, organization_id, "org.audit.read" if row.category == "audit" else "org.activity.read"
    )
    require(
        access.department_id is None or row.department_id == access.department_id,
        "not_found",
        "Record not found",
        404,
    )
    return activity_view(row)
