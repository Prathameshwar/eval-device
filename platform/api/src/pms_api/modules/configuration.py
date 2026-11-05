import copy
from typing import Any

from pms_api.core.common import AppError, digest, require, required
from pms_api.database.models import (
    Device,
    DeviceModelSelection,
    LLMConnection,
    Organization,
    PlatformSettings,
    ProfileRevision,
    ProviderConnection,
)
from pms_api.modules.common import public
from pms_api.modules.runtime_model_store import runtime_model
from pms_api.modules.schemas import (
    ProfileSettings,
)

REGISTRY: dict[str, dict[str, Any]] = {
    "training.interview": {"section": "audio_input", "engines": {"patient_interview_v1": None}},
    "audio.transcribe": {
        "section": "audio_input",
        "engines": {
            "aws_transcribe": "aws_processing",
            "azure_speech": "azure_speech",
            "azure_openai_whisper": "azure_openai_whisper",
            "local_whisper": None,
        },
    },
    "audio.activity": {"section": "audio_input", "engines": {"audio_activity": None}},
    "video.labels": {
        "section": "video",
        "engines": {"aws_rekognition": "aws_processing", "azure_video_indexer": "azure_video_indexer"},
    },
    "video.motion": {"section": "video", "engines": {"opencv_motion": None}},
    "audio.synthesize": {
        "section": "audio_output",
        "engines": {"aws_polly": "aws_processing", "azure_speech": "azure_speech", "espeak_ng": None},
    },
    "audio.playback": {"section": "audio_output", "engines": {"device_player": None}},
}
CONNECTION_FIELDS = {
    "azure_openai_whisper": {"endpoint", "deployment", "model", "api_version"},
    "aws_processing": {
        "region",
        "enabled_services",
        "staging_bucket",
        "staging_prefix",
        "role_arn",
        "external_id",
    },
    "azure_speech": {"region", "endpoint", "resource_id", "tenant_id", "client_id"},
    "azure_video_indexer": {
        "subscription_id",
        "resource_group",
        "account_name",
        "account_id",
        "location",
        "tenant_id",
        "client_id",
    },
}


def within(candidate: dict, limits: dict) -> bool:
    if not isinstance(candidate, dict) or not isinstance(limits, dict):
        return False
    return all(
        k in candidate
        and (
            within(candidate[k], v)
            if isinstance(v, dict)
            else isinstance(candidate[k], (int, float)) and 0 < candidate[k] <= v
        )
        for k, v in limits.items()
    )


def tighter(*policies: dict) -> dict:
    result = {}
    for key, value in policies[0].items():
        entries = [p[key] for p in policies if key in p]
        result[key] = tighter(*entries) if isinstance(value, dict) else min(entries)
    return result


def connection_view(row):
    value = public(row)
    value["has_credentials"] = row.encrypted_credentials is not None or row.secret_ref is not None
    return value


def validate_connection(provider, kind, auth, settings, credentials=None):
    import re

    require(
        isinstance(settings, dict), "invalid_connection_settings", "Connection settings must be an object"
    )
    require(
        set(settings) <= CONNECTION_FIELDS[kind],
        "unknown_connection_setting",
        "Unrecognized provider setting",
    )
    expected = "aws" if kind == "aws_processing" else "azure"
    require(provider == expected, "provider_mismatch", "Provider and connection type do not match")
    modes = {
        "azure_openai_whisper": {"api_key"},
        "aws_processing": {"workload_identity", "assume_role", "access_key"},
        "azure_speech": {"workload_identity", "api_key", "service_principal"},
        "azure_video_indexer": {"workload_identity", "service_principal"},
    }
    require(auth in modes[kind], "invalid_auth_mode", "Authentication mode is unsupported for this service")
    required = {
        "azure_openai_whisper": ["endpoint", "deployment"],
        "aws_processing": ["region"],
        "azure_speech": ["region"],
        "azure_video_indexer": [
            "subscription_id",
            "resource_group",
            "account_name",
            "account_id",
            "location",
        ],
    }[kind]
    if auth == "assume_role":
        required += ["role_arn", "external_id"]
    if auth == "service_principal":
        required += ["tenant_id", "client_id"]
    if kind == "azure_speech" and auth != "api_key":
        required += ["endpoint", "resource_id"]
    for key in required:
        require(
            isinstance(settings.get(key), str) and 0 < len(settings[key]) <= 512,
            "missing_connection_setting",
            f"Configure {key}",
        )
    for key in ("region", "location"):
        if key in settings:
            require(
                bool(re.fullmatch(r"[a-z0-9-]{2,40}", settings[key])),
                "invalid_region",
                "Invalid provider region",
            )
    if kind == "azure_openai_whisper":
        from pms_api.integrations.llm.policy import endpoint

        settings["endpoint"] = endpoint(
            settings["endpoint"], [], "azure_openai", [settings["endpoint"].rstrip("/")]
        )
        require(
            bool(re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", settings["deployment"])),
            "invalid_deployment",
            "Use a valid Azure Whisper deployment name",
        )
        if "api_version" in settings:
            require(
                isinstance(settings["api_version"], str)
                and bool(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:-preview)?", settings["api_version"])),
                "invalid_api_version",
                "Use an Azure API version such as 2024-06-01, or omit it for v1",
            )
        require(
            settings.get("model", "whisper") in ("whisper", "gpt-realtime-whisper"),
            "unsupported_model",
            "Select whisper or gpt-realtime-whisper",
        )
        require(
            settings.get("model") != "gpt-realtime-whisper" or "api_version" not in settings,
            "invalid_api_version",
            "Realtime transcription uses v1; omit api_version",
        )
    if kind == "azure_speech" and settings.get("endpoint"):
        # Resource endpoints must use the Azure resource domain; all API paths are fixed in code.
        from urllib.parse import urlparse

        try:
            url = urlparse(settings["endpoint"])
            port = url.port
        except (TypeError, ValueError):
            raise AppError(422, "invalid_endpoint", "Use an Azure Speech resource HTTPS endpoint") from None
        require(
            url.scheme == "https"
            and not url.username
            and not url.password
            and port in {None, 443}
            and not url.query
            and not url.fragment
            and bool(url.hostname)
            and url.hostname.endswith(".cognitiveservices.azure.com")
            and url.path in {"", "/"},
            "invalid_endpoint",
            "Use an Azure Speech resource HTTPS endpoint",
        )
    if credentials is not None:
        allowed = {
            "access_key": (
                {"access_key_id", "secret_access_key", "session_token"},
                {"access_key_id", "secret_access_key"},
            ),
            "api_key": ({"api_key"}, {"api_key"}),
            "service_principal": ({"client_secret"}, {"client_secret"}),
        }
        require(
            auth in allowed,
            "credentials_not_required",
            "This authentication mode does not accept stored credentials",
        )
        permitted, needed = allowed[auth]
        require(
            set(credentials) <= permitted and needed <= set(credentials),
            "invalid_credentials",
            "Credential fields do not match the authentication mode",
        )
        require(
            all(
                isinstance(v, str) and 0 < len(v) <= 8192 and all(33 <= ord(c) <= 126 for c in v)
                for v in credentials.values()
            ),
            "invalid_credentials",
            "Credential values must be bounded, nonempty printable non-space ASCII text",
        )


async def resolved_configuration(session, device: Device):
    platform = required(await session.get(PlatformSettings, 1))
    org = required(await session.get(Organization, device.organization_id))
    selection = await session.get(DeviceModelSelection, device.id)
    revision = await session.get(ProfileRevision, selection.execution_revision_id) if selection else None
    settings = (
        copy.deepcopy(revision.settings)
        if revision
        else ProfileSettings().model_dump(mode="json", exclude_none=True)
    )
    language = next(
        (
            item
            for item in platform.languages
            if item["code"] == (device.preferred_language or "en") and item["is_active"]
        ),
        None,
    )
    language = language or next(item for item in platform.languages if item["code"] == "en")
    for section in ("audio_input", "audio_output"):
        if not settings[section].get("language"):
            settings[section]["language"] = language["speech_locale"]
    policies = [platform.policy_limits, org.policy_settings]
    if settings.get("limits"):
        policies.append(settings["limits"])
    policy = tighter(*policies)
    capture_limits = policy["capture_limits"]
    # Section settings are capture limits too, including for server-side upload
    # inspection and quota reservation. Reapply current organization/platform caps.
    for section, fields in (
        ("audio_input", {"max_duration_seconds": "max_audio_seconds"}),
        (
            "video",
            {
                "clip_seconds": "max_video_seconds",
                "width": "max_width",
                "height": "max_height",
                "fps": "max_fps",
            },
        ),
    ):
        if settings[section].get("enabled"):
            for field, limit in fields.items():
                if settings[section].get(field) is not None:
                    capture_limits[limit] = min(capture_limits[limit], settings[section][field])
                    settings[section][field] = capture_limits[limit]
    value = {
        "device_id": str(device.id),
        "organization_id": str(org.id),
        "department_id": str(device.department_id) if device.department_id else None,
        "profile_revision_id": str(revision.id) if revision else None,
        "settings": settings,
        "policy": policy,
        "preferred_language": device.preferred_language,
        "effective_language": language["code"],
        "speech_locale": language["speech_locale"],
        "device_defaults": platform.device_defaults,
        "platform_configuration_version": platform.configuration_version,
        "enabled_providers": platform.enabled_providers,
        "is_active": device.is_active and org.is_active,
        "maintenance_mode": platform.maintenance_mode,
    }
    if device.department_id:
        from pms_api.database.models import Department

        dept = required(await session.get(Department, device.department_id))
        value["is_active"] = value["is_active"] and dept.is_active
    value["connections"] = {}
    if revision:
        for section in ("audio_input", "video", "audio_output"):
            connection_id = getattr(revision, section + "_connection_id")
            if connection_id:
                connection = await runtime_model(session, connection_id, ProviderConnection)
                value["connections"][section] = {
                    "id": str(connection_id),
                    "is_active": bool(connection and connection.is_active),
                    "configuration_version": connection.configuration_version if connection else None,
                }
    value["processing_allowed"] = bool(
        value["is_active"]
        and not platform.maintenance_mode
        and device.enrollment_state == "enrolled"
        and device.credential_hash
        and not device.credential_revoked_at
    )
    if revision and revision.llm_connection_id:
        llm = await runtime_model(session, revision.llm_connection_id, LLMConnection)
        value["connections"]["llm"] = {
            "id": str(revision.llm_connection_id),
            "is_active": bool(llm and llm.is_active),
            "revision": llm.revision if llm else None,
            "provider": llm.provider if llm else None,
            "model": llm.model if llm else None,
        }
    value["configuration_hash"] = digest(value)
    return value
