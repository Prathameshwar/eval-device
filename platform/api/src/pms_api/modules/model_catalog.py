import hashlib
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from sqlalchemy import or_, select

from pms_api.core.common import now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    LLMConnection,
    ModelDefinition,
    PlatformModelConnection,
)
from pms_api.modules.common import audit, commit, directory_page, public
from pms_api.modules.patching import changes, update_fields
from pms_api.modules.schemas import ModelDefinitionCreate, ModelDefinitionPatch, Restore
from pms_api.security.access import Actor, human, platform_access

router = APIRouter()
Limit = Annotated[int, Query(ge=1, le=100)]

PROVIDERS = {
    "openai": {"protocols": ["openai"], "operations": ["text.generate"], "adapter_available": True},
    "azure_openai": {
        "protocols": ["azure_openai"],
        "operations": ["text.generate"],
        "adapter_available": True,
    },
    "openai_compatible": {
        "protocols": ["openai"],
        "operations": ["text.generate"],
        "adapter_available": True,
    },
    "local_llama_cpp": {"protocols": ["openai"], "operations": ["text.generate"], "adapter_available": True},
    "local_whisper": {"protocols": ["local"], "operations": ["audio.transcribe"], "adapter_available": True},
    "azure": {
        "protocols": ["azure_speech", "azure_video_indexer"],
        "operations": ["audio.transcribe", "audio.synthesize", "video.labels"],
        "adapter_available": True,
    },
    "aws": {
        "protocols": ["aws_sdk"],
        "operations": ["audio.transcribe", "audio.synthesize", "video.labels"],
        "adapter_available": True,
    },
    "anthropic": {"protocols": ["native"], "operations": ["text.generate"], "adapter_available": True},
    "google": {
        "protocols": ["native"],
        "operations": ["text.generate", "vision.analyze"],
        "adapter_available": False,
    },
    "aws_bedrock": {"protocols": ["native"], "operations": ["text.generate"], "adapter_available": False},
}


def _binding(request: Request, name: str, values: list[object]) -> tuple[str, str]:
    raw = "|".join([name, *(str(value) for value in values)])
    return (
        hashlib.sha256(raw.encode()).hexdigest(),
        request.app.state.settings.local_token_signing_key.get_secret_value()
        or request.app.state.settings.token_pepper.get_secret_value(),
    )


@router.get("/providers", tags=["Models"])
async def providers(actor: Actor):
    human(actor)
    return {"items": [{"id": key, **value} for key, value in PROVIDERS.items()]}


@router.get("/providers/{provider}/capabilities", tags=["Models"])
async def provider_capabilities(provider: str, actor: Actor):
    human(actor)
    require(provider in PROVIDERS, "not_found", "Provider not found", 404)
    return {"id": provider, **PROVIDERS[provider]}


async def _models(
    request: Request,
    session: Session,
    *,
    limit: int,
    cursor: str | None,
    q: str | None,
    provider: str | None,
    category: str | None,
    operation: str | None,
    lifecycle: str | None,
    adapter_status: str | None,
    sort_by: str,
    sort_order: str,
    include_total: bool,
):
    expressions = {
        "display_name": ModelDefinition.display_name,
        "provider": ModelDefinition.provider,
        "created_at": ModelDefinition.created_at,
        "updated_at": ModelDefinition.updated_at,
    }
    require(sort_by in expressions, "invalid_sort", "Unsupported model sort field", 422)
    query = select(ModelDefinition)
    if q:
        term = q[:128]
        query = query.where(
            or_(
                ModelDefinition.display_name.icontains(term, autoescape=True),
                ModelDefinition.model_key.icontains(term, autoescape=True),
                ModelDefinition.description.icontains(term, autoescape=True),
            )
        )
    if provider:
        query = query.where(ModelDefinition.provider == provider)
    if category:
        query = query.where(ModelDefinition.categories.contains([category]))
    if operation:
        query = query.where(ModelDefinition.operations.contains([operation]))
    if lifecycle:
        query = query.where(ModelDefinition.lifecycle == lifecycle)
    if adapter_status:
        query = query.where(ModelDefinition.adapter_status == adapter_status)
    binding, secret = _binding(
        request, "models", [q, provider, category, operation, lifecycle, adapter_status, sort_by, sort_order]
    )
    rows, next_cursor, has_more, total = await directory_page(
        session,
        query,
        ModelDefinition,
        limit=limit,
        cursor=cursor,
        sort=sort_by,
        direction=sort_order,
        expression=expressions[sort_by],
        binding=binding,
        secret=secret,
        kind="datetime" if sort_by.endswith("_at") else "string",
        include_total=include_total,
    )
    return {
        "items": [public(row) for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        **({"total": total} if include_total else {}),
    }


@router.get("/models", tags=["Models"])
async def models(
    request: Request,
    session: Session,
    actor: Actor,
    limit: Limit = 50,
    cursor: str | None = None,
    q: Annotated[str | None, Query(max_length=128)] = None,
    provider: str | None = None,
    category: str | None = None,
    operation: str | None = None,
    lifecycle: Literal["active", "deprecated"] | None = "active",
    adapter_status: Literal["available", "unavailable"] | None = None,
    sort_by: str = "display_name",
    sort_order: Literal["asc", "desc"] = "asc",
    include_total: bool = False,
):
    human(actor)
    return await _models(
        request,
        session,
        limit=limit,
        cursor=cursor,
        q=q,
        provider=provider,
        category=category,
        operation=operation,
        lifecycle=lifecycle,
        adapter_status=adapter_status,
        sort_by=sort_by,
        sort_order=sort_order,
        include_total=include_total,
    )


@router.get("/models/{model_id}", tags=["Models"])
async def model_detail(model_id: UUID, session: Session, actor: Actor):
    human(actor)
    row = required(await session.get(ModelDefinition, model_id))
    require(row.lifecycle != "retired", "not_found", "Model not found", 404)
    return public(row)


@router.get("/platform/models", tags=["Platform", "Models"])
async def platform_models(
    request: Request,
    session: Session,
    actor: Actor,
    limit: Limit = 50,
    cursor: str | None = None,
    q: Annotated[str | None, Query(max_length=128)] = None,
    provider: str | None = None,
    category: str | None = None,
    operation: str | None = None,
    lifecycle: Literal["active", "deprecated", "retired"] | None = None,
    adapter_status: Literal["available", "unavailable"] | None = None,
    sort_by: str = "display_name",
    sort_order: Literal["asc", "desc"] = "asc",
    include_total: bool = False,
):
    platform_access(actor, "platform.settings.read")
    return await _models(
        request,
        session,
        limit=limit,
        cursor=cursor,
        q=q,
        provider=provider,
        category=category,
        operation=operation,
        lifecycle=lifecycle,
        adapter_status=adapter_status,
        sort_by=sort_by,
        sort_order=sort_order,
        include_total=include_total,
    )


@router.post("/platform/models", status_code=201, tags=["Platform", "Models"])
async def create_model(body: ModelDefinitionCreate, session: Session, actor: Actor):
    platform_access(actor, "platform.settings.manage")
    row = ModelDefinition(id=uuid4(), created_by=actor.id, updated_by=actor.id, **body.model_dump())
    session.add(row)
    await audit(session, actor, "platform.model.created", "model_definition", row.id)
    await commit(session, row)
    return public(row)


@router.get("/platform/models/{model_id}", tags=["Platform", "Models"])
async def platform_model_detail(model_id: UUID, session: Session, actor: Actor):
    platform_access(actor, "platform.settings.read")
    return public(required(await session.get(ModelDefinition, model_id)))


@router.patch("/platform/models/{model_id}", tags=["Platform", "Models"])
async def update_model(model_id: UUID, body: ModelDefinitionPatch, session: Session, actor: Actor):
    platform_access(actor, "platform.settings.manage")
    row = required(await session.get(ModelDefinition, model_id, with_for_update=True))
    require(
        row.version == body.expected_version,
        "version_conflict",
        "Model changed; refresh before retrying",
        409,
    )
    values = changes(body, {"expected_version"})
    if await session.get(PlatformModelConnection, model_id):
        require(
            not set(values).intersection(
                {"provider", "model_key", "operations", "adapter_status", "lifecycle"}
            ),
            "configured_model_locked",
            "Edit or test the cloud connection before changing its executable model settings",
            409,
        )
    update_fields(row, values)
    row.version += 1
    row.updated_by = actor.id
    row.updated_at = now()
    await audit(
        session,
        actor,
        "platform.model.updated",
        "model_definition",
        row.id,
        details={"fields": sorted(values)},
    )
    await commit(session, row)
    return public(row)


@router.delete("/platform/models/{model_id}", tags=["Platform", "Models"])
async def retire_model(model_id: UUID, session: Session, actor: Actor):
    platform_access(actor, "platform.settings.manage")
    row = required(await session.get(ModelDefinition, model_id, with_for_update=True))
    require(
        await session.get(PlatformModelConnection, model_id) is None,
        "dependency_conflict",
        "A cloud configuration uses this model",
        409,
    )
    dependency = await session.scalar(
        select(LLMConnection.id).where(
            LLMConnection.model_definition_id == row.id,
            LLMConnection.is_active.is_(True),
            LLMConnection.archived_at.is_(None),
        )
    )
    require(not dependency, "dependency_conflict", "Active configured models still use this definition", 409)
    if row.lifecycle != "retired":
        row.lifecycle = "retired"
        row.version += 1
        row.updated_by = actor.id
        row.updated_at = now()
        await audit(session, actor, "platform.model.retired", "model_definition", row.id)
    await commit(session, row)
    return public(row)


@router.post("/platform/models/{model_id}/restore", tags=["Platform", "Models"])
async def restore_model(model_id: UUID, body: Restore, session: Session, actor: Actor):
    platform_access(actor, "platform.settings.manage")
    row = required(await session.get(ModelDefinition, model_id, with_for_update=True))
    require(
        row.version == body.expected_version,
        "version_conflict",
        "Model changed; refresh before retrying",
        409,
    )
    require(row.lifecycle == "retired", "state_conflict", "Model is not retired", 409)
    row.lifecycle = "deprecated"
    row.version += 1
    row.updated_by = actor.id
    row.updated_at = now()
    await audit(session, actor, "platform.model.restored", "model_definition", row.id)
    await commit(session, row)
    return public(row)
