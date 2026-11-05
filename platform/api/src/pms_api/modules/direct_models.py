"""Models own execution settings. Devices select models in one atomic operation."""

import asyncio
import copy
from types import SimpleNamespace
from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Query, Request
from pydantic import Field, SecretStr, ValidationError, field_validator
from sqlalchemy import func, or_, select

from pms_api.core.common import AppError, now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    Department,
    Device,
    DeviceModelSelection,
    PlatformSettings,
    ProfileRevision,
    RuntimeModel,
)
from pms_api.database.session import lock_administration
from pms_api.integrations.contracts import synthesis_parameters
from pms_api.integrations.llm.capabilities import ModelOptions
from pms_api.integrations.llm.policy import configured_endpoint
from pms_api.integrations.providers import ProviderFactory
from pms_api.integrations.vault import CredentialVault
from pms_api.modules.common import audit, commit
from pms_api.modules.configuration import REGISTRY, validate_connection
from pms_api.modules.device_management import available_tenant, fleet_record, fleet_response
from pms_api.modules.platform_models import CLOUD, LOCAL_LLM, LOCAL_SPEECH, cloud_endpoint
from pms_api.modules.schemas import Input, ProfileSettings
from pms_api.security.access import Actor, authentication, bearer, platform_access

router = APIRouter(tags=["Models"])
KINDS = ("llm", "asr", "tts", "video")
SECTIONS = {"asr": "audio_input", "tts": "audio_output", "video": "video"}
LOCAL = {"llm": "llm", "asr": "local_whisper", "tts": "espeak_ng", "video": "opencv_motion"}
OPERATIONS = {"asr": "audio.transcribe", "tts": "audio.synthesize", "video": "video.labels"}


class MediaDefaults(Input):
    language: str | None = Field(None, pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$", max_length=40)
    voice: str | None = Field(None, min_length=1, max_length=120)
    format: Literal["wav", "mp3", "ogg", "pcm"] | None = None


class ConversationSettings(Input):
    base_url: str = Field(max_length=512)
    max_tokens: int = Field(1024, ge=16, le=4096, strict=True)
    token_parameter: Literal["max_tokens", "max_completion_tokens"] | None = None
    stream_usage: bool | None = Field(None, strict=True)
    instruction_role: Literal["system", "developer"] | None = None
    model_options: ModelOptions | None = None


class ModelDraft(Input):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["llm", "asr", "tts", "video"]
    location: Literal["local", "cloud"]
    provider: str = Field(max_length=80)
    engine: str = Field(max_length=80)
    model_key: str = Field(pattern=r"^[A-Za-z0-9_.:/-]{1,100}$")
    settings: dict = Field(default_factory=dict)
    defaults: dict = Field(default_factory=dict)
    credentials: dict[str, SecretStr] | None = None
    expected_revision: int | None = Field(None, gt=0)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value or "\x00" in value:
            raise ValueError("Enter a model name")
        return value

    @field_validator("defaults")
    @classmethod
    def valid_defaults(cls, value):
        return MediaDefaults(**value).model_dump(exclude_none=True)


class DeviceSelection(Input):
    mode: Literal["local", "cloud"]
    expected_version: int = Field(ge=0)
    llm_model_id: UUID | None = None
    asr_model_id: UUID | None = None
    tts_model_id: UUID | None = None
    video_model_id: UUID | None = None
    model_revisions: dict[UUID, int] = Field(default_factory=dict, max_length=4)


class ModelTest(Input):
    expected_revision: int = Field(gt=0)


def model_view(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "organization_id",
            "name",
            "kind",
            "location",
            "provider",
            "engine",
            "model_key",
            "settings",
            "defaults",
            "revision",
            "is_active",
        )
    } | {"has_credentials": bool(row.encrypted_credentials)}


def validate_model(body, settings, existing=None):
    credentials = {k: v.get_secret_value() for k, v in body.credentials.items()} if body.credentials else None
    values = copy.deepcopy(body.settings)
    require(
        len(str(values)) <= 8192 and len(str(body.defaults)) <= 4096,
        "invalid_model_settings",
        "Model settings are too large",
        422,
    )
    permitted = (
        {"language", "voice", "format"}
        if body.kind == "tts"
        else {"language"}
        if body.kind == "asr"
        else set()
    )
    require(
        set(body.defaults) <= permitted,
        "irrelevant_field",
        "Remove settings unrelated to this model type",
        422,
    )
    defaults = MediaDefaults(**body.defaults).model_dump(exclude_none=True)
    if body.location == "local":
        require(
            not values and not credentials,
            "local_settings",
            "Local models need no endpoint or credentials",
            422,
        )
        require(body.engine == LOCAL[body.kind], "invalid_engine", "Choose a supported local model", 422)
        expected_provider = (
            "local_llama_cpp" if body.kind == "llm" else "local_whisper" if body.kind == "asr" else "local"
        )
        require(
            body.provider == expected_provider, "invalid_provider", "Choose a supported local provider", 422
        )
        allowed = (
            LOCAL_LLM if body.kind == "llm" else LOCAL_SPEECH if body.kind == "asr" else {LOCAL[body.kind]}
        )
        require(body.model_key in allowed, "unsupported_model", "Choose an available local model", 422)
    elif body.kind == "llm":
        require(
            body.provider in CLOUD and body.engine == "llm",
            "invalid_provider",
            "Choose a supported LLM provider",
            422,
        )
        try:
            values = ConversationSettings(**values).model_dump(exclude_none=True)
        except ValidationError:
            raise AppError(422, "invalid_model_settings", "Check the conversation settings") from None
        require(
            isinstance(values.get("base_url"), str),
            "invalid_endpoint",
            "Enter an API endpoint",
            422,
        )
        values["base_url"] = cloud_endpoint(body.provider, values.get("base_url", ""), settings)
        maximum = values.get("max_tokens", 1024)
        require(
            type(maximum) is int and 16 <= maximum <= 4096,
            "invalid_tokens",
            "Reply limit must be 16–4096",
            422,
        )
        values["max_tokens"] = maximum
        if credentials:
            require(
                set(credentials) == {"api_key"}
                and 0 < len(credentials["api_key"]) <= 4096
                and all(33 <= ord(c) <= 126 for c in credentials["api_key"]),
                "invalid_credentials",
                "Enter a valid API key",
                422,
            )
        require(
            credentials or (existing and existing.encrypted_credentials),
            "credentials_required",
            "Enter an API key",
            422,
        )
    else:
        require(
            all(isinstance(value, str) and 0 < len(value) <= 512 for value in values.values()),
            "invalid_model_settings",
            "Provider fields must be nonempty text",
            422,
        )
        kind = REGISTRY[OPERATIONS[body.kind]]["engines"].get(body.engine)
        require(kind, "invalid_engine", "Choose a supported cloud model", 422)
        auth = values.pop("auth_mode", "api_key")
        values.pop("connection_type", None)
        if body.engine == "azure_openai_whisper":
            values["deployment"] = body.model_key
        validate_connection(body.provider, kind, auth, values, credentials)
        if body.engine == "azure_openai_whisper":
            values["endpoint"] = cloud_endpoint("azure_openai", values["endpoint"], settings)
            require(
                defaults.get("language", "auto") in {"en", "hi", "auto"},
                "unsupported_language",
                "Whisper language must be en, hi or auto",
                422,
            )
        require(
            auth in {"workload_identity", "assume_role"}
            or not existing
            or auth == existing.auth_mode
            or credentials,
            "credentials_required",
            "Enter credentials for the new authentication method",
            422,
        )
        require(
            auth in {"workload_identity", "assume_role"}
            or credentials
            or (existing and existing.encrypted_credentials),
            "credentials_required",
            "Enter the provider credentials",
            422,
        )
        if body.engine in {"aws_transcribe", "aws_rekognition"}:
            require(values.get("staging_bucket"), "staging_required", "Enter a private staging bucket", 422)
        values |= {"auth_mode": auth, "connection_type": kind}
    if body.kind == "tts" and body.location == "cloud":
        synthesis_parameters(body.engine, defaults, {"text": "configuration validation"})
    return values, defaults, credentials


@router.get("/platform/runtime-models")
async def models(session: Session, actor: Actor):
    platform_access(actor, "platform.settings.manage")
    rows = (
        await session.scalars(
            select(RuntimeModel)
            .where(RuntimeModel.kind.in_(KINDS), RuntimeModel.archived_at.is_(None))
            .order_by(RuntimeModel.name, RuntimeModel.id)
        )
    ).all()
    return {"items": [model_view(row) for row in rows]}


async def write_model(body, request, session, actor, model_id=None):
    platform_access(actor, "platform.settings.manage")
    await lock_administration(session)
    row = required(await session.get(RuntimeModel, model_id, with_for_update=True)) if model_id else None
    if row:
        require(row.archived_at is None, "not_found", "Model not found", 404)
        require(
            row.revision == body.expected_revision,
            "version_conflict",
            "This model changed. Reload before saving",
            409,
        )
        require(
            (row.kind, row.location, row.provider, row.engine)
            == (body.kind, body.location, body.provider, body.engine),
            "model_type_changed",
            "Create a new model to change its type or provider",
            422,
        )
    values, defaults, credentials = validate_model(body, request.app.state.settings, row)
    if row:
        if row.organization_id:
            await available_tenant(session, row.organization_id)
        endpoint_key = "base_url" if row.kind == "llm" else "endpoint"
        require(
            not row.encrypted_credentials
            or values.get(endpoint_key) == row.settings.get(endpoint_key)
            or credentials
            or body.location == "local",
            "llm_fresh_key_required",
            "Enter fresh credentials when changing the endpoint",
            422,
        )
        if row.kind == "llm":
            values = {
                key: value
                for key, value in row.settings.items()
                if key
                in {
                    "system_prompt",
                    "model_options",
                    "token_parameter",
                    "stream_usage",
                    "instruction_role",
                }
            } | values
    if not row:
        count = await session.scalar(
            select(func.count())
            .select_from(RuntimeModel)
            .where(RuntimeModel.archived_at.is_(None), RuntimeModel.kind.in_(KINDS))
        )
        require(
            count < 100, "model_configuration_limit", "The platform supports up to 100 configured models", 409
        )
        row = RuntimeModel(
            id=uuid4(),
            kind=body.kind,
            location=body.location,
            provider=body.provider,
            engine=body.engine,
            revision=0,
            created_by=actor.id,
        )
        session.add(row)
    row.name, row.model_key, row.settings, row.defaults = body.name, body.model_key, values, defaults
    row.revision += 1
    row.is_active, row.updated_by, row.updated_at = body.is_active, actor.id, now()
    if credentials:
        row.credential_owner_id, row.credential_owner_org = row.id, row.organization_id or UUID(int=0)
        row.encrypted_credentials, row.credential_key_id = CredentialVault(
            request.app.state.settings
        ).encrypt(row.credential_owner_org, row.credential_owner_id, credentials)
    elif body.location == "local" or values.get("auth_mode") in {"workload_identity", "assume_role"}:
        row.encrypted_credentials, row.credential_key_id = None, None
        row.credential_owner_id, row.credential_owner_org = None, None
    await session.flush()
    assigned = (
        await session.scalars(
            select(DeviceModelSelection)
            .where(or_(*(getattr(DeviceModelSelection, k + "_model_id") == row.id for k in KINDS)))
            .order_by(DeviceModelSelection.device_id)
            .with_for_update()
        )
    ).all()
    for selection in assigned:
        await snapshot_selection(session, selection, actor.id)
    await audit(
        session,
        actor,
        "model.updated" if model_id else "model.created",
        "runtime_model",
        row.id,
        row.organization_id,
        {"kind": row.kind, "location": row.location, "revision": row.revision},
    )
    await commit(session, row)
    return model_view(row)


@router.post("/platform/runtime-models", status_code=201)
async def create_model(body: ModelDraft, request: Request, session: Session, actor: Actor):
    return await write_model(body, request, session, actor)


@router.put("/platform/runtime-models/{model_id}")
async def update_model(model_id: UUID, body: ModelDraft, request: Request, session: Session, actor: Actor):
    return await write_model(body, request, session, actor, model_id)


async def testable_model(session, actor, model_id, revision, settings, *, lock=False):
    platform_access(actor, "platform.settings.manage")
    row = required(await session.get(RuntimeModel, model_id, populate_existing=True, with_for_update=lock))
    require(row.archived_at is None, "not_found", "Model not found", 404)
    require(row.revision == revision, "version_conflict", "Reload this model before testing", 409)
    require(row.location == "cloud", "cloud_model_required", "Test local models on their device", 422)
    require(row.is_active, "llm_connection_inactive", "Enable this model before testing", 409)
    if row.organization_id:
        await available_tenant(session, row.organization_id)
    platform = required(await session.get(PlatformSettings, 1, populate_existing=True))
    require(not platform.maintenance_mode, "maintenance_mode", "Provider checks are paused", 503)
    require(settings.external_calls_enabled, "external_calls_disabled", "External calls are disabled", 503)
    provider = "azure" if row.provider == "azure_openai" else row.provider
    require(
        provider not in {"aws", "azure"} or provider in platform.enabled_providers,
        "provider_disabled",
        "Enable this provider in platform settings",
        503,
    )
    return row


@router.post("/platform/runtime-models/{model_id}/test")
async def test_model(model_id: UUID, body: ModelTest, request: Request, session: Session, actor: Actor):
    """Bounded access check; never claims that catalog access proves inference works."""
    settings = request.app.state.settings
    row = await testable_model(session, actor, model_id, body.expected_revision, settings)
    snapshot = SimpleNamespace(
        **{
            key: getattr(row, key)
            for key in (
                "id",
                "organization_id",
                "provider",
                "kind",
                "model",
                "base_url",
                "settings",
                "auth_mode",
                "connection_type",
                "encrypted_credentials",
                "credential_key_id",
                "credential_owner_id",
                "credential_owner_org",
            )
        }
    )
    # Release the transaction before provider I/O; reauthenticate and fence the revision afterwards.
    await session.rollback()
    error_code = None
    check = "service_access"
    try:
        async with asyncio.timeout(30):
            if snapshot.kind == "llm":
                url = configured_endpoint(snapshot, settings, dispatch=True)
                credentials = CredentialVault(settings).decrypt(snapshot)
                await request.app.state.llm.health(
                    url, snapshot.model, credentials["api_key"], provider=snapshot.provider
                )
                check = "authenticated_api_access" if snapshot.provider == "azure_openai" else "model_catalog"
            else:
                adapter = ProviderFactory(settings).for_connection(snapshot)
                require(
                    await adapter.validate(OPERATIONS[snapshot.kind], sample=False) is True,
                    "model_test_failed",
                    "Provider check did not succeed",
                    502,
                )
                if snapshot.connection_type == "azure_openai_whisper":
                    check = "authenticated_api_access"
    except AppError as error:
        error_code = (
            error.code
            if error.code
            in {
                "llm_endpoint_invalid",
                "llm_credentials_rejected",
                "llm_model_mismatch",
                "llm_deployment_not_found",
                "llm_busy",
                "llm_unavailable",
                "credential_key_unavailable",
                "credential_decryption_failed",
                "external_calls_disabled",
            }
            else "model_test_failed"
        )
    except httpx.HTTPStatusError as error:
        error_code = (
            "llm_credentials_rejected" if error.response.status_code in {401, 403} else "model_test_failed"
        )
    except TimeoutError:
        error_code = "model_test_timeout"
    except Exception:
        # SDK exceptions can include signed URLs and credential-bearing request details.
        error_code = "model_test_failed"
    current_actor = await authentication(request, session, await bearer(request))
    row = await testable_model(session, current_actor, model_id, body.expected_revision, settings, lock=True)
    result = {
        "status": "failed" if error_code else "passed",
        "revision": row.revision,
        "check": check,
        "inference_verified": False,
        "error_code": error_code,
        "checked_at": now(),
    }
    await audit(
        session,
        current_actor,
        "model.tested",
        "runtime_model",
        row.id,
        row.organization_id,
        {key: result[key] for key in ("status", "revision", "check", "error_code")},
    )
    await session.commit()
    return result


@router.delete("/platform/runtime-models/{model_id}")
async def delete_model(model_id: UUID, session: Session, actor: Actor, expected_revision: int = Query(gt=0)):
    platform_access(actor, "platform.settings.manage")
    await lock_administration(session)
    row = required(await session.get(RuntimeModel, model_id, with_for_update=True))
    require(row.revision == expected_revision, "version_conflict", "Reload this model before deleting", 409)
    assigned = await session.scalar(
        select(DeviceModelSelection.device_id)
        .join(Device, Device.id == DeviceModelSelection.device_id)
        .where(or_(*(getattr(DeviceModelSelection, k + "_model_id") == model_id for k in KINDS)))
        .where(Device.enrollment_state != "retired")
        .limit(1)
    )
    require(not assigned, "model_in_use", "Remove this model from its devices before deleting it", 409)
    row.archived_at, row.is_active, row.updated_at = now(), False, now()
    row.revision += 1
    await audit(session, actor, "model.deleted", "runtime_model", row.id, row.organization_id)
    await commit(session, row)
    return {"deleted": True}


async def snapshot_selection(session, selection, actor_id):
    values = ProfileSettings().model_dump(mode="json", exclude_none=True)
    if selection.execution_revision_id:
        previous = required(await session.get(ProfileRevision, selection.execution_revision_id))
        for key in ("capture", "limits"):
            if key in previous.settings:
                values[key] = copy.deepcopy(previous.settings[key])
    bindings = {}
    for kind in KINDS:
        model_id = getattr(selection, kind + "_model_id")
        model = await session.get(RuntimeModel, model_id) if model_id else None
        if kind == "llm":
            bindings["llm_connection_id"] = model_id if model and model.is_active else None
            values["conversation"] = {
                "enabled": bool(model and model.is_active),
                "execution_mode": model.location if model else None,
            }
        else:
            section = SECTIONS[kind]
            bindings[section + "_connection_id"] = (
                model_id if model and model.is_active and model.location == "cloud" else None
            )
            if model:
                values[section] = {
                    **{
                        key: value
                        for key, value in model.legacy.get("section", {}).items()
                        if key
                        not in (
                            {"language", "voice", "format", "model_configuration_id"}
                            if kind == "tts"
                            else {"language", "model_configuration_id"}
                            if kind == "asr"
                            else {"model_configuration_id"}
                        )
                    },
                    "enabled": model.is_active,
                    "engine": model.engine,
                    "operation": model.legacy.get("section", {}).get("operation")
                    or ("video.motion" if model.engine == "opencv_motion" else OPERATIONS[kind]),
                    "execution_mode": model.location,
                    "model": model.model_key,
                    **model.defaults,
                }
    selection.version += 1
    snapshot = ProfileRevision(
        id=uuid4(),
        organization_id=selection.organization_id,
        device_id=selection.device_id,
        profile_id=None,
        version=selection.version,
        settings=values,
        published_by=actor_id,
        **bindings,
    )
    session.add(snapshot)
    await session.flush()
    selection.execution_revision_id, selection.updated_by, selection.updated_at = snapshot.id, actor_id, now()


def selection_view(row):
    return (
        {key: getattr(row, key) for key in ("mode", "version", *(k + "_model_id" for k in KINDS))}
        if row
        else {"mode": "cloud", "version": 0, **{k + "_model_id": None for k in KINDS}}
    )


async def configuration_blocker(session, device):
    tenant = await available_tenant(session, device.organization_id, False)
    if not tenant.is_active:
        return "organization_inactive", "Activate this tenant before changing device models."
    if device.enrollment_state == "retired":
        return "device_inactive", "This registration is retired. Configure the current device registration."
    if not device.is_active:
        return "device_inactive", "Activate this device before changing its models."
    if device.department_id:
        department = required(await session.get(Department, device.department_id))
        if not department.is_active or department.archived_at is not None:
            return "department_inactive", "Activate the device's department before changing its models."
    return None


@router.get("/platform/devices/{device_id}/models")
async def device_choices(device_id: UUID, session: Session, actor: Actor):
    device = await fleet_record(session, actor, device_id)
    blocker = await configuration_blocker(session, device)
    selection = await session.get(DeviceModelSelection, device_id)
    rows = (
        await session.scalars(
            select(RuntimeModel)
            .where(
                RuntimeModel.kind.in_(KINDS),
                RuntimeModel.archived_at.is_(None),
                or_(
                    RuntimeModel.organization_id.is_(None),
                    RuntimeModel.organization_id == device.organization_id,
                ),
            )
            .order_by(RuntimeModel.name, RuntimeModel.id)
        )
    ).all()
    return {
        "device": await fleet_response(session, device),
        "configuration_allowed": blocker is None,
        "configuration_blocked_reason": blocker[1] if blocker else None,
        "selection": selection_view(selection),
        "models": [
            {
                "id": row.id,
                "name": row.name,
                "kind": row.kind,
                "location": row.location,
                "revision": row.revision,
                # Assignment can precede enrollment/runtime installation. Inventory
                # describes execution readiness, not permission to configure a model.
                "available": row.is_active,
            }
            for row in rows
        ],
    }


@router.put("/platform/devices/{device_id}/models")
async def save_device_models(device_id: UUID, body: DeviceSelection, session: Session, actor: Actor):
    await lock_administration(session)
    device = await fleet_record(session, actor, device_id)
    blocker = await configuration_blocker(session, device)
    if blocker:
        raise AppError(409, *blocker)
    selection = await session.get(DeviceModelSelection, device_id, with_for_update=True)
    require(
        (selection.version if selection else 0) == body.expected_version,
        "version_conflict",
        "This device's models changed. Reload before saving",
        409,
    )
    if not selection:
        selection = DeviceModelSelection(
            device_id=device_id, organization_id=device.organization_id, version=0
        )
        session.add(selection)
    for kind in KINDS:
        ident = getattr(body, kind + "_model_id")
        if ident:
            model = required(await session.get(RuntimeModel, ident, with_for_update=True))
            require(
                model.organization_id in {None, device.organization_id} and model.archived_at is None,
                "not_found",
                "Model not found",
                404,
            )
            require(
                model.kind == kind and model.location == body.mode and model.is_active,
                "invalid_model",
                "Choose an active model of the selected type and mode",
                422,
            )
            require(
                body.model_revisions.get(ident) == model.revision,
                "model_changed",
                "Model changed. Reload before saving",
                409,
            )
        setattr(selection, kind + "_model_id", ident)
    selection.mode = body.mode
    await snapshot_selection(session, selection, actor.id)
    await audit(
        session,
        actor,
        "device.models.updated",
        "device",
        device.id,
        device.organization_id,
        {"mode": body.mode, "version": selection.version},
    )
    await commit(session, selection)
    return selection_view(selection)
