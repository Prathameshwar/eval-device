"""PostgreSQL queue with fenced leases, uncertain-submission recovery and cleanup."""

import asyncio
import copy
import hashlib
import logging
from contextlib import suppress
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.dialects.postgresql import array

from pms_api.core.common import AppError, canonical, now, require, required
from pms_api.database.models import (
    ActivityEvent,
    Department,
    Device,
    Organization,
    PlatformSettings,
    ProcessingRun,
    ProviderConnection,
    TelemetrySample,
)
from pms_api.integrations.contracts import validate_submission
from pms_api.integrations.providers import ProviderFactory
from pms_api.integrations.storage import storage_for
from pms_api.modules.runtime_model_store import runtime_model

TERMINAL = {"succeeded", "failed", "cancelled", "expired"}
log = logging.getLogger(__name__)


async def record_state(session, row):
    from pms_api.modules.common import audit

    await audit(
        session,
        None,
        "processing.state_changed",
        "processing_run",
        row.id,
        row.organization_id,
        {
            "status": row.status,
            "submission_status": row.provider_submission_status,
            "cleanup_status": row.cleanup_status,
            "playback_status": row.playback_status,
        },
        category="operational",
        device_id=row.device_id,
        department_id=row.department_id,
    )


class Worker:
    def __init__(self, settings, sessions, factory=None, storage=None):
        self.settings = settings
        self.sessions = sessions
        self.factory = factory or ProviderFactory(settings)
        self.storage = storage or storage_for(settings)

    async def expire(self):
        async with self.sessions() as session:
            query = (
                select(ProcessingRun)
                .join(Device, Device.id == ProcessingRun.device_id)
                .join(Organization, Organization.id == ProcessingRun.organization_id)
                .outerjoin(Department, Department.id == Device.department_id)
                .where(
                    ProcessingRun.status.not_in(TERMINAL),
                    or_(
                        ProcessingRun.deadline_at <= now(),
                        Device.is_active.is_(False),
                        Device.enrollment_state != "enrolled",
                        Device.credential_hash.is_(None),
                        Device.credential_revoked_at.is_not(None),
                        Organization.is_active.is_(False),
                        Department.is_active.is_(False),
                    ),
                )
                .limit(100)
                .with_for_update(skip_locked=True, of=ProcessingRun)
            )
            for row in (await session.scalars(query)).all():
                row.status = "expired" if row.deadline_at <= now() else "cancelled"
                row.completed_at = now()
                if row.playback_status in {"pending", "playing", "unknown"}:
                    row.playback_status = "cancelled"
                if row.media_manifest:
                    row.cleanup_status = "pending"
                    row.cleanup_next_attempt_at = now()
                await record_state(session, row)
            playback_query = (
                select(ProcessingRun)
                .where(
                    ProcessingRun.playback_status.in_(["pending", "playing", "unknown"]),
                    ProcessingRun.playback_expires_at <= now(),
                )
                .limit(100)
                .with_for_update(skip_locked=True)
            )
            for row in (await session.scalars(playback_query)).all():
                row.playback_status = "expired"
                row.playback_acknowledged_at = now()
                await record_state(session, row)
            await session.commit()

    async def claim(self):
        timestamp = now()
        async with self.sessions() as session:
            query = (
                select(ProcessingRun)
                .where(
                    or_(
                        ProcessingRun.lease_expires_at.is_(None), ProcessingRun.lease_expires_at <= timestamp
                    ),
                    or_(
                        and_(
                            ProcessingRun.execution_mode == "cloud",
                            ProcessingRun.status.in_(["queued", "running"]),
                            or_(
                                ProcessingRun.next_attempt_at.is_(None),
                                ProcessingRun.next_attempt_at <= timestamp,
                            ),
                        ),
                        and_(
                            ProcessingRun.provider_submission_status.in_(["submitting", "unknown"]),
                            or_(
                                ProcessingRun.next_attempt_at.is_(None),
                                ProcessingRun.next_attempt_at <= timestamp,
                            ),
                        ),
                        and_(
                            ProcessingRun.status.in_(TERMINAL),
                            ProcessingRun.cleanup_status.in_(["pending", "running", "failed"]),
                            ProcessingRun.cleanup_next_attempt_at <= timestamp,
                            ProcessingRun.provider_submission_status.not_in(["submitting", "unknown"]),
                        ),
                    ),
                )
                .order_by(ProcessingRun.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            row = await session.scalar(query)
            if row is None:
                return None
            row.lease_token = uuid4()
            row.lease_expires_at = timestamp + timedelta(seconds=self.settings.worker_lease_seconds)
            row.attempt_count += 1
            await session.commit()
            return row

    async def save(self, claimed, **values):
        async with self.sessions() as session:
            row = await session.scalar(
                select(ProcessingRun)
                .where(
                    ProcessingRun.id == claimed.id,
                    ProcessingRun.lease_token == claimed.lease_token,
                    ProcessingRun.lease_expires_at > now(),
                )
                .with_for_update()
            )
            if row is None:
                return False
            if row.status in TERMINAL and values.get("provider_submission_status") == "submitting":
                return False
            # A concurrent cancellation is authoritative. Never resurrect a closed run.
            if row.status in TERMINAL and values.get("status") not in {None, row.status}:
                for key in ("status", "result", "error", "completed_at", "started_at"):
                    values.pop(key, None)
            before = (row.status, row.provider_submission_status, row.cleanup_status)
            for key, value in values.items():
                setattr(row, key, value)
            after = (row.status, row.provider_submission_status, row.cleanup_status)
            if before != after:
                await record_state(session, row)
            await session.commit()
            for key in values:
                setattr(claimed, key, getattr(row, key))
            return True

    async def renew(self, row):
        while True:
            await asyncio.sleep(self.settings.worker_lease_seconds / 3)
            if not await self.save(
                row, lease_expires_at=now() + timedelta(seconds=self.settings.worker_lease_seconds)
            ):
                return

    async def adapter(self, row, dispatch=False):
        async with self.sessions() as session:
            connection = required(await runtime_model(session, row.connection_id, ProviderConnection))
            require(connection is not None, "connection_missing", "Processing connection is unavailable", 409)
            assert connection is not None
            snapshot = row.effective_settings["connection"]
            if dispatch:
                device = required(await session.get(Device, row.device_id))
                org = required(await session.get(Organization, row.organization_id))
                dept = await session.get(Department, device.department_id) if device.department_id else None
                platform = required(await session.get(PlatformSettings, 1))
                require(
                    device.is_active
                    and device.enrollment_state == "enrolled"
                    and device.credential_hash
                    and not device.credential_revoked_at
                    and org.is_active
                    and (dept is None or dept.is_active),
                    "device_inactive",
                    "Processing is suspended",
                    409,
                )
                require(not platform.maintenance_mode, "maintenance_mode", "Processing is paused", 503)
                require(
                    connection.is_active
                    and connection.provider in platform.enabled_providers
                    and connection.configuration_version == snapshot["configuration_version"],
                    "connection_changed",
                    "Connection changed before dispatch",
                    409,
                )
                validation = connection.validation_results.get(row.operation, {})
                require(
                    getattr(connection, "kind", "legacy_media") != "legacy_media"
                    or (
                        validation.get("status") == "valid"
                        and validation.get("configuration_version") == connection.configuration_version
                    ),
                    "connection_unvalidated",
                    "Connection is unvalidated",
                    409,
                )
            # Routing remains the accepted snapshot; credentials may rotate independently.
            value = SimpleNamespace(
                id=connection.id,
                credential_owner_id=getattr(connection, "credential_owner_id", None),
                credential_owner_org=getattr(connection, "credential_owner_org", None),
                organization_id=connection.organization_id,
                settings=copy.deepcopy(snapshot["settings"]),
                provider=connection.provider,
                connection_type=connection.connection_type,
                auth_mode=connection.auth_mode,
                encrypted_credentials=connection.encrypted_credentials,
                credential_key_id=connection.credential_key_id,
            )
            connection.last_used_at = now()
            await session.commit()
            return self.factory.for_connection(value)

    async def apply_result(self, row, outcome):
        if outcome.status == "unknown":
            await self.save(
                row,
                provider_submission_status="unknown",
                error={"code": "submission_unknown"},
                next_attempt_at=now() + timedelta(minutes=10),
            )
            return
        values = {
            "provider_submission_status": "submitted",
            "provider_job_id": outcome.job_id or row.provider_job_id,
            "next_attempt_at": now() + timedelta(seconds=10),
        }
        if outcome.status in {"succeeded", "failed"}:
            values["usage"] = {**row.usage, "provider_complete": True}
            if row.status not in TERMINAL:
                require(
                    len(canonical(outcome.result or {}).encode()) <= 1048576,
                    "provider_result_too_large",
                    "Provider result is too large",
                )
                if outcome.audio is not None:
                    require(
                        len(outcome.audio)
                        <= row.effective_settings["policy"]["capture_limits"]["max_upload_bytes"],
                        "media_too_large",
                        "Generated media exceeds policy",
                    )
                    media = next(m for m in row.media_manifest if m["role"] == "output")
                    await self.storage.write(media["key"], outcome.audio, "application/octet-stream")
                values.update(
                    status=outcome.status,
                    result=outcome.result,
                    error={"code": outcome.error} if outcome.error else None,
                    completed_at=now(),
                )
        elif row.status not in TERMINAL:
            values.update(status="running", started_at=row.started_at or now())
        await self.save(row, **values)

    async def process(self, row):
        if row.provider_submission_status in {"submitting", "unknown"}:
            if row.engine == "aws_rekognition" and row.created_at < now() - timedelta(days=6):
                await self.save(
                    row,
                    next_attempt_at=now() + timedelta(hours=12),
                    error={"code": "operator_reconciliation_required"},
                )
                return
            adapter = await self.adapter(row)
            await self.apply_result(
                row,
                await adapter.reconcile(
                    row.id, row.operation, row.effective_settings["section"], row.request
                ),
            )
            return
        if row.status in TERMINAL:
            if (
                row.cleanup_status in {"pending", "running", "failed"}
                and row.cleanup_next_attempt_at <= now()
            ):
                await self.cleanup(row)
            return
        if row.provider_submission_status == "submitted":
            adapter = await self.adapter(row)
            await self.apply_result(row, await adapter.poll(row.id, row.operation, row.provider_job_id))
            return
        validate_submission(row.engine, row.operation, row.effective_settings["section"], row.request)
        adapter = await self.adapter(row, dispatch=True)
        media = next((m for m in row.media_manifest if m["role"] == "input"), None)
        data = None
        if media:
            data = await self.storage.read(
                media["key"], row.effective_settings["policy"]["capture_limits"]["max_upload_bytes"]
            )
            require(
                media.get("verified") and hashlib.sha256(data).hexdigest() == media.get("sha256"),
                "media_changed",
                "Uploaded media changed after verification",
                409,
            )
            # Persist the provider cleanup intent BEFORE staging can create external objects.
            if not any(m["storage"] == "provider" for m in row.media_manifest):
                manifest = [
                    *row.media_manifest,
                    {
                        "role": "input",
                        "storage": "provider",
                        "cleanup_status": "pending",
                        "expires_at": row.media_expires_at.isoformat(),
                    },
                ]
                if not await self.save(row, media_manifest=manifest):
                    return
            await adapter.stage(row.id, data, row.request["format"])
        if not await self.save(
            row, provider_submission_status="submitting", status="running", started_at=row.started_at or now()
        ):
            return
        # The submission marker is durable before any billable external request.
        if row.effective_settings["connection"]["provider"] == "azure":
            outcome = await adapter.submit(
                row.id, row.operation, row.effective_settings["section"], row.request, data=data
            )
        else:
            outcome = await adapter.submit(
                row.id, row.operation, row.effective_settings["section"], row.request
            )
        await self.apply_result(row, outcome)

    async def cleanup(self, row):
        if row.provider_submission_status in {"submitting", "unknown"}:
            return
        adapter = (
            await self.adapter(row) if any(m["storage"] == "provider" for m in row.media_manifest) else None
        )
        if (
            adapter
            and row.provider_submission_status == "submitted"
            and not row.usage.get("provider_complete")
        ):
            outcome = await adapter.poll(row.id, row.operation, row.provider_job_id)
            await self.apply_result(row, outcome)
            if outcome.status not in {"succeeded", "failed"}:
                await self.save(row, cleanup_next_attempt_at=now() + timedelta(minutes=1))
                return
        if not await self.save(row, cleanup_status="running"):
            return
        for media in row.media_manifest:
            if media["storage"] == "platform" and not media.get("shared"):
                await self.storage.delete(media["key"])
        if adapter and (
            row.provider_submission_status != "not_submitted"
            or row.effective_settings["connection"]["provider"] == "aws"
        ):
            await adapter.cleanup(row.id, row.operation, row.request, row.provider_job_id)
        await self.save(
            row,
            media_manifest=[{**m, "cleanup_status": "succeeded"} for m in row.media_manifest],
            cleanup_status="succeeded",
            cleanup_next_attempt_at=None,
        )

    async def tick(self):
        await self.expire()
        row = await self.claim()
        if row is None:
            return False
        renewal = asyncio.create_task(self.renew(row))
        try:
            await self.process(row)
        except Exception as error:
            code = error.code if isinstance(error, AppError) else "provider_unavailable"
            log.warning("worker_operation_failed", extra={"run_id": str(row.id), "error_code": code})
            if row.provider_submission_status == "submitting":
                await self.save(
                    row,
                    provider_submission_status="unknown",
                    error={"code": "submission_unknown"},
                    next_attempt_at=now() + timedelta(minutes=10),
                )
            elif row.status in TERMINAL:
                await self.save(
                    row,
                    cleanup_status="failed" if row.media_manifest else "not_required",
                    cleanup_next_attempt_at=now() + timedelta(minutes=10) if row.media_manifest else None,
                    next_attempt_at=now() + timedelta(minutes=10),
                    error={"code": code},
                )
            elif (
                row.provider_submission_status == "not_submitted"
                and code not in {"maintenance_mode", "external_calls_disabled"}
                and (
                    row.attempt_count >= 5
                    or code
                    in {
                        "media_changed",
                        "connection_changed",
                        "device_inactive",
                        "unsupported_format",
                        "voice_required",
                        "text_too_long",
                        "text_required",
                        "invalid_language",
                    }
                )
            ):
                await self.save(row, status="failed", completed_at=now(), error={"code": code})
            else:
                await self.save(
                    row,
                    error={"code": code},
                    next_attempt_at=now() + timedelta(seconds=min(600, 2 ** min(row.attempt_count, 9))),
                )
        finally:
            renewal.cancel()
            with suppress(asyncio.CancelledError):
                await renewal
            await self.save(row, lease_token=None, lease_expires_at=None)
        return True


async def retain(sessions):
    """Restricted maintenance connection: bounded redaction and expired-only deletion."""
    from pms_api.database.models import (
        LLMRequest,
        LocalConversationTurn,
        LocalTurn,
        PatientConversation,
        TrainingSession,
    )

    retained_request_fields = ("fingerprint", "format", "duration_seconds", "playback")
    deletable = and_(
        ProcessingRun.status.in_(TERMINAL),
        ProcessingRun.cleanup_status.in_(["not_required", "succeeded"]),
        ProcessingRun.provider_submission_status.not_in(["submitting", "unknown"]),
        or_(ProcessingRun.lease_expires_at.is_(None), ProcessingRun.lease_expires_at <= now()),
        ProcessingRun.playback_status.not_in(["pending", "playing", "unknown"]),
    )
    needs_redaction = or_(
        ProcessingRun.result.is_not(None),
        ProcessingRun.error.is_not(None),
        ProcessingRun.request.op("-")(array(retained_request_fields)) != {},
    )
    async with sessions() as session:
        rows = (
            await session.execute(
                select(ProcessingRun, deletable.label("can_delete"))
                # Already-redacted records waiting for cleanup/reconciliation must not
                # consume every slot and indefinitely block later expired records.
                .where(ProcessingRun.expires_at <= now(), or_(deletable, needs_redaction))
                .order_by(ProcessingRun.expires_at, ProcessingRun.id)
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for row, can_delete in rows:
            row.result = None
            row.error = None
            row.request = {k: v for k, v in row.request.items() if k in retained_request_fields}
            # Keep uncertain/unclean runs for reconciliation; never pretend cleanup succeeded.
            if can_delete:
                await session.delete(row)
        expired_training = (
            select(TrainingSession.id).where(TrainingSession.results_expires_at <= now()).limit(100)
        )
        await session.execute(delete(TrainingSession).where(TrainingSession.id.in_(expired_training)))
        expired_llm = (
            select(LLMRequest.id)
            .where(LLMRequest.expires_at <= now(), LLMRequest.status != "running")
            .limit(100)
        )
        await session.execute(delete(LLMRequest).where(LLMRequest.id.in_(expired_llm)))
        expired_conversations = (
            select(PatientConversation.id)
            .where(
                PatientConversation.expires_at <= now(),
                ~select(LLMRequest.id).where(LLMRequest.conversation_id == PatientConversation.id).exists(),
            )
            .limit(100)
        )
        await session.execute(
            delete(PatientConversation).where(PatientConversation.id.in_(expired_conversations))
        )
        # Expired telemetry, metrics and paired history use bounded deletion.
        for model in (TelemetrySample, ActivityEvent, LocalTurn, LocalConversationTurn):
            ids = select(model.id).where(model.expires_at <= now()).limit(500)
            await session.execute(delete(model).where(model.id.in_(ids)))
        await session.commit()
