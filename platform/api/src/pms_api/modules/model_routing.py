"""Published speech/LLM routes shared by desktop and device configuration."""

from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select

from pms_api.core.common import canonical, digest, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    Department,
    Device,
    DeviceModelSelection,
    LLMConnection,
    Organization,
    PlatformSettings,
    ProfileRevision,
    ProviderConnection,
)
from pms_api.modules.configuration import tighter
from pms_api.modules.runtime_model_store import runtime_model
from pms_api.security.access import Actor, device_access, organization_access

router = APIRouter(tags=["Model configuration"])
BASE = "/organizations/{organization_id}"


async def access_for(session, actor, org):
    if actor.device:
        device = await device_access(session, actor)
        require(device.organization_id == org, "not_found", "Organization not found", 404)
        return await session.get(Organization, org, populate_existing=True)
    return (await organization_access(session, actor, org, "org.processing.execute")).organization


async def bound_device(session, actor, organization_id, device_id):
    """Resolve a human client's registered device without treating its ID as authentication."""
    access = await organization_access(session, actor, organization_id, "org.processing.execute")
    device = await session.scalar(
        select(Device).where(Device.id == device_id, Device.organization_id == organization_id)
    )
    require(
        device is not None and (access.department_id is None or device.department_id == access.department_id),
        "not_found",
        "Device not found",
        404,
    )
    assert device is not None
    department = await session.get(Department, device.department_id) if device.department_id else None
    require(
        device.enrollment_state == "enrolled"
        and device.credential_hash is not None
        and device.credential_revoked_at is None
        and device.is_active
        and (department is None or (department.is_active and department.archived_at is None)),
        "device_inactive",
        "Device is not active and enrolled",
        409,
    )
    return device


async def effective_route(session, actor, org, settings, profile_id=None, device_id=None):
    profile: Any
    organization = await access_for(session, actor, org)
    require(
        not actor.device or device_id is None or device_id == actor.device.id,
        "invalid_request",
        "Device identity is already bound",
        422,
    )
    selected_device = actor.device.id if actor.device else device_id
    if selected_device is None and profile_id:
        direct = await session.get(DeviceModelSelection, profile_id)
        if direct:
            selected_device = direct.device_id
    selection = await session.get(DeviceModelSelection, selected_device) if selected_device else None
    if selection:
        require(selection.organization_id == org, "not_found", "Device not found", 404)
        if not actor.device:
            await bound_device(session, actor, org, selected_device)
        require(
            profile_id is None or profile_id == selected_device,
            "not_found",
            "Models are not assigned to this device",
            404,
        )
        profile = SimpleNamespace(id=selected_device, name="Device models")
        revision = required(await session.get(ProfileRevision, selection.execution_revision_id))
    else:
        require(False, "device_models_required", "Ask Platform Admin to select models for this device", 409)
    conversation = revision.settings.get("conversation", {})
    audio = revision.settings.get("audio_input", {})
    require(
        conversation.get("enabled") and revision.llm_connection_id,
        "model_profile_incomplete",
        "No conversation model is assigned to this device",
        409,
    )
    require(
        selection is not None
        or (audio.get("enabled") and audio.get("engine") in {"local_whisper", "azure_openai_whisper"}),
        "model_profile_incomplete",
        "Select local Whisper or Azure OpenAI Whisper",
        409,
    )
    llm = required(
        await runtime_model(session, revision.llm_connection_id, LLMConnection, populate_existing=True)
    )
    require(
        llm.organization_id in {None, org} and llm.is_active,
        "llm_connection_inactive",
        "Selected LLM is inactive",
        409,
    )
    speech = None
    if audio.get("enabled") and audio.get("execution_mode") == "cloud":
        speech = required(
            await runtime_model(
                session, revision.audio_input_connection_id, ProviderConnection, populate_existing=True
            )
        )
        require(
            speech.organization_id in {None, org}
            and speech.is_active
            and (selection is not None or speech.connection_type == "azure_openai_whisper"),
            "speech_connection_inactive",
            "Selected speech connection is inactive",
            409,
        )
    platform = required(await session.get(PlatformSettings, 1, populate_existing=True))
    policies = [platform.policy_limits, organization.policy_settings]
    if revision.settings.get("limits"):
        policies.append(revision.settings["limits"])
    limits = tighter(*policies)
    audio_mode = audio.get("execution_mode") or "local"
    llm_mode = "local" if llm.provider == "local_llama_cpp" else "cloud"
    value = {
        "profile_id": str(profile.id),
        "profile_name": profile.name,
        "profile_revision_id": str(revision.id),
        "profile_version": revision.version,
        "mode": (selection.mode if selection.mode != "mixed" else "custom")
        if selection
        else (audio_mode if audio_mode == llm_mode else "custom"),
        "audio": {
            "mode": audio_mode,
            "provider": (
                "azure_openai" if speech.connection_type == "azure_openai_whisper" else speech.provider
            )
            if speech
            else {
                "azure_openai_whisper": "azure_openai",
                "azure_speech": "azure",
                "aws_transcribe": "aws",
            }.get(audio.get("engine"), "local_whisper"),
            "enabled": bool(audio.get("enabled")),
            "model": speech.settings.get("deployment", audio.get("model", speech.connection_type))
            if speech
            else audio.get("model", "large-v3"),
            "connection_id": str(speech.id) if speech else None,
            "connection_revision": speech.configuration_version if speech else None,
            "language": audio.get("language", "auto"),
            "max_seconds": min(
                settings.speech_max_seconds,
                audio.get("max_duration_seconds") or 30,
                limits["capture_limits"]["max_audio_seconds"],
            ),
        },
        "llm": {
            "mode": llm_mode,
            "provider": llm.provider,
            "model": llm.model,
            "connection_id": str(llm.id),
            "connection_revision": llm.revision,
            "model_options": llm.model_options,
            "requires_external": not llm.base_url.startswith("http://127.0.0.1:"),
            # A local model runs on the caller's own machine, so the caller executes the
            # turn and this service never dials it. Publish what that execution needs;
            # the credential stays in the vault and is never part of a route.
            "execution": "caller" if llm_mode == "local" else "platform",
            "max_tokens": llm.max_tokens,
            "instruction_role": llm.instruction_role,
            "system_prompt": llm.system_prompt,
            "local_port": urlsplit(llm.base_url).port if llm_mode == "local" else None,
            "local_context_tokens": settings.patient_local_context_tokens if llm_mode == "local" else None,
            # Budgets belong to the platform even when the caller runs the model, so a
            # laptop turn and a hosted turn stay one substitutable unit.
            "patient_policy": "patient-conversation-v1",
            "conversation_tokens": (
                settings.patient_conversation_tokens_local
                if llm_mode == "local"
                else settings.patient_conversation_tokens_remote
            ),
            "history_messages": (
                settings.patient_history_messages_local
                if llm_mode == "local"
                else settings.patient_history_messages_remote
            ),
        },
        "platform_media": {
            section: {
                "settings": revision.settings.get(section, {"enabled": False}),
                "connection_id": str(binding) if binding else None,
            }
            for section in ("video", "audio_output")
            for binding in (getattr(revision, section + "_connection_id"),)
        },
        "cloud_allowed": settings.external_calls_enabled,
        "speech_enabled": settings.speech_enabled,
        "llm_enabled": settings.llm_enabled,
        "maintenance_mode": platform.maintenance_mode,
        "azure_enabled": "azure" in platform.enabled_providers,
        "limits": limits,
    }
    value["configuration_hash"] = digest(canonical(value))
    return value


async def require_route(session, actor, org, revision_id, expected_hash, settings):
    revision = required(await session.get(ProfileRevision, revision_id))
    require(revision.organization_id == org, "not_found", "Profile not found", 404)
    value = await effective_route(session, actor, org, settings, revision.device_id or revision.profile_id)
    require(
        value["profile_revision_id"] == str(revision_id) and value["configuration_hash"] == expected_hash,
        "model_selection_changed",
        "Processing configuration changed; reload before asking another question",
        409,
    )
    require(not value["maintenance_mode"], "maintenance_mode", "New processing is paused", 503)
    return value


@router.get(BASE + "/model-config")
async def get_config(
    organization_id: UUID,
    request: Request,
    session: Session,
    actor: Actor,
    profile_id: UUID | None = None,
    device_id: UUID | None = None,
):
    return await effective_route(
        session, actor, organization_id, request.app.state.settings, profile_id, device_id
    )
