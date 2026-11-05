"""Authenticated reporting of models installed on a device."""

from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from pydantic import Field, SecretStr

from pms_api.core.common import now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import Device
from pms_api.integrations.llm.policy import endpoint
from pms_api.modules.common import audit, commit
from pms_api.modules.device_management import fleet_record
from pms_api.modules.schemas import Input
from pms_api.security.access import Actor, device_access

router = APIRouter(tags=["Device models"])
CLOUD = {"openai", "azure_openai", "openai_compatible", "anthropic"}
LOCAL_LLM = {"qwen3-4b-local", "qwen3-1.7b-local", "qwen3.5-4b-local", "qwenmedic-v1-local"}
LOCAL_SPEECH = {"tiny", "base", "small", "medium", "large-v3", "large-v3-turbo", "whisper-medical-v1"}


class LocalModelReport(Input):
    device_id: UUID
    llm: list[Annotated[str, Field(max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")]] = Field(max_length=8)
    speech: list[Annotated[str, Field(max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")]] = Field(max_length=16)


def reported_inventory(device):
    capabilities = device.capabilities if isinstance(device.capabilities, dict) else {}
    report = capabilities.get("local_models")
    received = capabilities.get("local_models_received_at")
    try:
        timestamp = datetime.fromisoformat(received) if isinstance(received, str) else None
        current = now()
        fresh = (
            capabilities.get("local_models_source") == "device_report_v1"
            and isinstance(report, dict)
            and timestamp is not None
            and current - timedelta(hours=24) <= timestamp <= current + timedelta(minutes=1)
        )
    except (TypeError, ValueError):
        fresh = False
    return report if fresh else {}, received, fresh


@router.post("/device/local-models")
async def report_local_models(body: LocalModelReport, session: Session, actor: Actor):
    """The enrolled device reports its runtime's installed aliases; no paths or credentials."""
    device = await device_access(session, actor)
    require(
        body.device_id == device.id,
        "device_mismatch",
        "The device token does not match the configured device ID",
        403,
    )
    require(
        set(body.llm) <= LOCAL_LLM
        and set(body.speech) <= LOCAL_SPEECH
        and len(body.llm) == len(set(body.llm))
        and len(body.speech) == len(set(body.speech)),
        "invalid_local_inventory",
        "Report only unique supported model names",
        422,
    )
    current = required(await session.get(Device, device.id, with_for_update=True))
    timestamp = now()
    current.capabilities = {
        **current.capabilities,
        "local_models": {"llm": sorted(body.llm), "speech": sorted(body.speech)},
        "local_models_received_at": timestamp.isoformat(),
        "local_models_source": "device_report_v1",
    }
    current.last_seen_at = timestamp
    await audit(
        session,
        None,
        "device.local_models.reported",
        "device",
        current.id,
        current.organization_id,
        {"llm_count": len(body.llm), "speech_count": len(body.speech)},
    )
    await commit(session, current)
    return {
        "device_id": current.id,
        "received_at": timestamp,
        "llm": sorted(body.llm),
        "speech": sorted(body.speech),
    }


def cloud_endpoint(provider, value, settings):
    require(provider in CLOUD, "invalid_provider", "Select a supported cloud provider")
    return endpoint(value, settings.llm_allowed_ports, provider, settings.llm_allowed_base_urls)


def key_value(key: SecretStr) -> str:
    value = key.get_secret_value()
    require(
        value.isascii() and all(33 <= ord(char) <= 126 for char in value),
        "invalid_api_key",
        "Use a printable API key without spaces",
    )
    return value


@router.get("/platform/devices/{device_id}/local-models")
async def local_models_for_device(device_id: UUID, session: Session, actor: Actor):
    device = await fleet_record(session, actor, device_id)
    report, received, fresh = reported_inventory(device)
    return {
        "device_id": device.id,
        "received_at": received,
        "fresh": fresh,
        "llm": report.get("llm", []),
        "speech": report.get("speech", []),
    }
