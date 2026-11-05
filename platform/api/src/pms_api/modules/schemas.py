from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

Name = Annotated[str, Field(min_length=1, max_length=256)]
DeviceUniqueId = Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[^\x00-\x1f\x7f]+$")]
HumanRole = Literal["org_admin", "org_user", "org_read_only", "org_trainee"]
Provider = Literal["aws", "azure"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class CaptureLimits(Input):
    max_audio_seconds: int = Field(60, gt=0, le=3600)
    max_video_seconds: int = Field(15, gt=0, le=600)
    max_width: int = Field(1280, gt=0, le=7680)
    max_height: int = Field(720, gt=0, le=4320)
    max_fps: int = Field(15, gt=0, le=120)
    max_upload_bytes: int = Field(26214400, gt=0, le=1073741824)


class UsageLimits(Input):
    max_concurrent_jobs: int = Field(2, gt=0, le=1000)
    daily_audio_seconds: int = Field(1800, gt=0, le=86400000)
    daily_video_seconds: int = Field(600, gt=0, le=86400000)
    daily_tts_characters: int = Field(10000, gt=0, le=100000000)


class Policy(Input):
    offline_authorization_hours: int = Field(24, gt=0, le=168)
    media_retention_hours: int = Field(24, gt=0, le=720)
    result_retention_days: int = Field(30, gt=0, le=3650)
    telemetry_retention_days: int = Field(7, gt=0, le=365)
    operational_retention_days: int = Field(30, gt=0, le=3650)
    audit_retention_days: int = Field(90, gt=0, le=3650)
    capture_limits: CaptureLimits = Field(default_factory=CaptureLimits)
    usage_limits: UsageLimits = Field(default_factory=UsageLimits)


class DeviceDefaults(Input):
    heartbeat_seconds: int = Field(60, gt=0, le=3600)
    offline_after_seconds: int = Field(180, gt=0, le=86400)
    active_poll_seconds: int = Field(5, gt=0, le=300)
    telemetry_sample_seconds: int = Field(300, gt=0, le=3600)

    @model_validator(mode="after")
    def timing(self):
        if self.offline_after_seconds <= self.heartbeat_seconds:
            raise ValueError("offline_after_seconds must exceed heartbeat_seconds")
        return self


class Contact(Input):
    name: Name
    description: str | None = Field(None, max_length=4000)
    contact_name: str | None = Field(None, max_length=256)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(None, max_length=80)


class OrganizationCreate(Contact):
    subscription_plan_id: UUID
    policy_settings: Policy | None = None


class SubscriptionPlanPatch(Input):
    expected_version: int = Field(gt=0)
    name: Name | None = None
    price_amount: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=2)
    currency: Literal["INR", "USD"] | None = None
    billing_period: Literal["unspecified", "monthly", "annual", "one_time"] | None = None
    max_users: int | None = Field(None, ge=1, le=1000000, strict=True)
    max_devices: int | None = Field(None, ge=1, le=1000000, strict=True)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def valid_plan_name(cls, value):
        if value is not None and ("\x00" in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value)):
            raise ValueError("Plan name contains unsupported characters")
        return value


class SubscriptionAssignment(Input):
    subscription_plan_id: UUID
    expected_version: int | None = Field(None, gt=0)


class OrganizationPatch(Input):
    expected_version: int | None = Field(None, gt=0)
    name: Name | None = None
    description: str | None = Field(None, max_length=4000)
    contact_name: str | None = Field(None, max_length=256)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(None, max_length=80)
    is_active: bool | None = None
    status_reason: str | None = Field(None, max_length=4000)
    policy_settings: Policy | None = None


LanguageCode = Annotated[str, Field(pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")]


class Language(Input):
    code: LanguageCode
    name: str = Field(min_length=1, max_length=80)
    speech_locale: str = Field(pattern=r"^[a-z]{2,3}-[A-Z]{2}$")
    is_active: bool = True


class PlatformPatch(Input):
    languages: list[Language] | None = Field(None, min_length=1, max_length=100)
    expected_version: int = Field(gt=0)
    display_name: Name | None = None
    registration_mode: Literal["self_service", "invite_only"] | None = None
    enabled_providers: list[Provider] | None = None
    default_organization_policy: Policy | None = None
    policy_limits: Policy | None = None
    device_defaults: DeviceDefaults | None = None
    maintenance_mode: bool | None = None


class UserPatch(Input):
    display_name: Name | None = None
    phone: str | None = Field(None, max_length=80)


class PeopleInput(Input):
    @field_validator("*")
    @classmethod
    def valid_text(cls, value):
        if isinstance(value, str) and ("\x00" in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value)):
            raise ValueError("Use valid Unicode text without null characters")
        return value


class UserAdminPatch(PeopleInput):
    expected_version: int | None = Field(None, gt=0)
    display_name: Name | None = None
    phone: str | None = Field(None, max_length=80)
    is_active: bool | None = None
    platform_role: Literal["platform_admin"] | None = None
    status_reason: str | None = Field(None, max_length=4000)


class LocalUserCreate(PeopleInput):
    email: EmailStr
    display_name: Name
    phone: str | None = Field(None, max_length=80)
    platform_role: Literal["platform_admin"] | None = None
    organization_id: UUID | None = None

    @model_validator(mode="after")
    def administrator_scope(self):
        if self.platform_role and self.organization_id:
            raise ValueError("Choose platform administrator or tenant administrator, not both")
        return self


class Restore(Input):
    expected_version: int = Field(gt=0)


ModelCategory = Literal[
    "text",
    "conversation",
    "asr",
    "tts",
    "vision",
    "video",
    "ocr",
    "embedding",
    "reranking",
    "image_generation",
    "video_generation",
]


def validate_capability_metadata(value: dict) -> dict:
    import json

    forbidden = {
        "headers",
        "authorization",
        "credentials",
        "endpoint",
        "base_url",
        "url",
        "validator",
        "code",
    }

    def inspect(item):
        if isinstance(item, dict):
            if any(str(key).casefold() in forbidden for key in item):
                raise ValueError("Capability metadata cannot define credentials, destinations, or code")
            for nested in item.values():
                inspect(nested)
        elif isinstance(item, list):
            for nested in item:
                inspect(nested)

    inspect(value)
    if len(json.dumps(value, separators=(",", ":")).encode()) > 32768:
        raise ValueError("Capability metadata is too large")
    return value


class ModelDefinitionCreate(Input):
    provider: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    model_key: str = Field(pattern=r"^[A-Za-z0-9_.:/-]{1,160}$")
    display_name: Name
    description: str | None = Field(None, max_length=4000)
    publisher: str | None = Field(None, max_length=160)
    model_family: str | None = Field(None, max_length=160)
    model_version: str | None = Field(None, max_length=160)
    categories: list[ModelCategory] = Field(min_length=1, max_length=16)
    operations: list[str] = Field(min_length=1, max_length=32)
    capabilities: dict = Field(default_factory=dict)
    adapter_status: Literal["available", "unavailable"] = "unavailable"

    @model_validator(mode="after")
    def unique_catalog_values(self):
        if len(set(self.categories)) != len(self.categories) or len(set(self.operations)) != len(
            self.operations
        ):
            raise ValueError("Categories and operations must be unique")
        if any(not value or len(value) > 80 for value in self.operations):
            raise ValueError("Operations must contain 1 to 80 characters")
        validate_capability_metadata(self.capabilities)
        return self


class ModelDefinitionPatch(Input):
    expected_version: int = Field(gt=0)
    display_name: Name | None = None
    description: str | None = Field(None, max_length=4000)
    publisher: str | None = Field(None, max_length=160)
    model_family: str | None = Field(None, max_length=160)
    model_version: str | None = Field(None, max_length=160)
    categories: list[ModelCategory] | None = Field(None, min_length=1, max_length=16)
    operations: list[str] | None = Field(None, min_length=1, max_length=32)
    capabilities: dict | None = None
    adapter_status: Literal["available", "unavailable"] | None = None
    lifecycle: Literal["active", "deprecated"] | None = None

    @model_validator(mode="after")
    def validate_metadata(self):
        if self.categories is not None and len(set(self.categories)) != len(self.categories):
            raise ValueError("Categories must be unique")
        if self.operations is not None:
            if len(set(self.operations)) != len(self.operations) or any(
                not value or len(value) > 80 for value in self.operations
            ):
                raise ValueError("Operations must be unique and contain 1 to 80 characters")
        if self.capabilities is not None:
            validate_capability_metadata(self.capabilities)
        return self


class DepartmentCreate(Input):
    name: Name
    description: str | None = Field(None, max_length=4000)


class DepartmentPatch(Input):
    expected_version: int | None = Field(None, gt=0)
    name: Name | None = None
    description: str | None = Field(None, max_length=4000)
    is_active: bool | None = None
    status_reason: str | None = Field(None, max_length=4000)


class InvitationCreate(PeopleInput):
    email: EmailStr
    auth_method: Literal["local", "oidc"] | None = None
    local_display_name: Name | None = None
    role: HumanRole
    department_id: UUID | None = None


class MembershipPatch(PeopleInput):
    expected_version: int | None = Field(None, gt=0)
    role: HumanRole | None = None
    department_id: UUID | None = None
    is_active: bool | None = None
    status_reason: str | None = Field(None, max_length=4000)


class TokenInput(Input):
    token: SecretStr = Field(min_length=20, max_length=256)


class AdminAssignment(Input):
    user_id: UUID


class DeviceCreate(PeopleInput):
    device_unique_id: DeviceUniqueId
    is_active: bool = True
    preferred_language: LanguageCode | None = None
    name: Name
    device_type: Literal["manikin", "laptop"]
    department_id: UUID | None = None
    location: str | None = Field(None, max_length=512)
    contact_name: str | None = Field(None, max_length=256)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(None, max_length=80)
    details: dict = Field(default_factory=dict)


class DevicePatch(PeopleInput):
    expected_etag: str | None = Field(None, pattern=r"^[0-9a-f]{64}$")
    details: dict | None = None
    preferred_language: LanguageCode | None = None
    name: Name | None = None
    department_id: UUID | None = None
    location: str | None = Field(None, max_length=512)
    contact_name: str | None = Field(None, max_length=256)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(None, max_length=80)
    is_active: bool | None = None
    status_reason: str | None = Field(None, max_length=4000)


class Enrollment(Input):
    token: SecretStr = Field(min_length=20, max_length=256)
    device_identifier: DeviceUniqueId | None = None
    capabilities: dict = Field(default_factory=dict)


class Health(Input):
    cpu_percent: float | None = Field(None, ge=0, le=100)
    memory_percent: float | None = Field(None, ge=0, le=100)
    disk_free_bytes: int | None = Field(None, ge=0)
    temperature_c: float | None = None
    uptime_seconds: float | None = Field(None, ge=0)
    capture_fps: float | None = Field(None, ge=0)
    dropped_video_frames: int | None = Field(None, ge=0)
    audio_overflows: int | None = Field(None, ge=0)
    audio_underflows: int | None = Field(None, ge=0)
    processing_latency_ms: float | None = Field(None, ge=0)
    upload_failures: int | None = Field(None, ge=0)
    pending_runs: int | None = Field(None, ge=0)
    camera_status: Literal["ready", "busy", "absent", "error", "unknown"] | None = None
    microphone_status: Literal["ready", "busy", "absent", "error", "unknown"] | None = None
    speaker_status: Literal["ready", "busy", "absent", "error", "unknown"] | None = None


class Heartbeat(Input):
    boot_id: UUID
    sequence_number: int = Field(ge=0)
    observed_at: AwareDatetime | None = None
    metrics: Health = Field(default_factory=Health)
    capabilities: dict | None = None
    applied_profile_revision_id: UUID | None = None
    applied_configuration_hash: str | None = Field(None, pattern=r"^[0-9a-f]{64}$")
    config_error: dict | None = None


class DeviceEvent(Input):
    source_event_id: UUID
    event_type: Literal[
        "device.status",
        "device.error",
        "capture.started",
        "capture.stopped",
        "processing.error",
        "playback.status",
    ]
    occurred_at: AwareDatetime
    historical: bool = False
    severity: Literal["info", "warning", "error"] = "info"
    code: str | None = Field(None, max_length=80)


class EventBatch(Input):
    events: list[DeviceEvent] = Field(min_length=1, max_length=100)


class ProcessingSection(Input):
    model_configuration_id: UUID | None = None
    enabled: bool = False
    operation: str | None = Field(None, max_length=80)
    execution_mode: Literal["local", "cloud"] | None = None
    engine: str | None = Field(None, max_length=80)
    model: str | None = Field(None, pattern=r"^[a-zA-Z0-9_.:/-]{1,100}$")
    language: str | None = Field(None, max_length=40)
    voice: str | None = Field(None, max_length=120)
    format: Literal["wav", "mp3", "mp4", "flac", "ogg", "pcm"] | None = None
    sample_rate: int | None = Field(None, ge=8000, le=48000)
    channels: int | None = Field(None, ge=1, le=2)
    max_duration_seconds: int | None = Field(None, gt=0, le=3600)
    width: int | None = Field(None, gt=0, le=7680)
    height: int | None = Field(None, gt=0, le=4320)
    fps: int | None = Field(None, gt=0, le=120)
    clip_seconds: int | None = Field(None, gt=0, le=600)
    event_cooldown_seconds: int | None = Field(None, ge=1, le=86400)
    volume_limit: float | None = Field(None, ge=0, le=1)
    pause_input_during_playback: bool = True


class CaptureSettings(Input):
    activation: Literal["manual", "event"] = "manual"
    max_session_seconds: int = Field(60, gt=0, le=3600)


class ConversationSettings(Input):
    enabled: bool = False
    execution_mode: Literal["local", "cloud"] | None = None


class ProfileSettings(Input):
    schema_version: Literal[1] = 1
    audio_input: ProcessingSection = Field(default_factory=ProcessingSection)
    video: ProcessingSection = Field(default_factory=ProcessingSection)
    audio_output: ProcessingSection = Field(default_factory=ProcessingSection)
    capture: CaptureSettings = Field(default_factory=CaptureSettings)
    conversation: ConversationSettings = Field(default_factory=ConversationSettings)
    limits: Policy | None = None


class RunCreate(Input):
    source_run_id: UUID | None = None
    device_id: UUID | None = None
    request_key: UUID
    capture_id: UUID | None = None
    operation: Literal[
        "audio.transcribe",
        "audio.activity",
        "video.labels",
        "video.motion",
        "audio.synthesize",
        "audio.playback",
    ]
    profile_revision_id: UUID
    text: str | None = Field(None, min_length=1, max_length=10000)
    media_format: Literal["wav", "mp3", "mp4", "flac", "ogg"] | None = None
    duration_seconds: float | None = Field(None, gt=0, le=3600)
    captured_at: AwareDatetime | None = None
    playback: bool = False


class RunResult(Input):
    status: Literal["succeeded", "failed"]
    result: dict | None = None
    error_code: str | None = Field(None, max_length=80)


class PlaybackAck(Input):
    status: Literal["playing", "succeeded", "failed", "unknown"]


class ValidationRequest(Input):
    operation: Literal["audio.transcribe", "audio.synthesize", "video.labels"]
    sample: bool = False


class SubmissionResolution(Input):
    outcome: Literal["not_created", "job_found", "completed_without_result"]
    provider_job_id: str | None = Field(None, min_length=1, max_length=256)
    reason: str = Field(min_length=10, max_length=1000)
    verified_with_provider: Literal[True]
