"""Shared admission counts; callers hold the organization row lock."""

from sqlalchemy import func, select

from pms_api.core.common import now
from pms_api.database.models import ActivityEvent, ProcessingRun, TrainingSession
from pms_api.database.speech import SpeechRequest


async def speech_usage(session, org):
    count = await session.scalar(
        select(func.count())
        .select_from(SpeechRequest)
        .where(SpeechRequest.organization_id == org, SpeechRequest.status == "running")
    )
    return count, (await daily_speech_millis(session, org)) / 1000


async def daily_speech_millis(session, org):
    # Audit metadata survives short media retention, so deletion cannot reset quota.
    # Audit retention has a server-enforced minimum of one full day.
    return await session.scalar(
        select(func.coalesce(func.sum(ActivityEvent.details["duration_ms"].as_integer()), 0)).where(
            ActivityEvent.organization_id == org,
            ActivityEvent.category == "audit",
            ActivityEvent.event_type == "speech.accepted",
            ActivityEvent.received_at >= now().replace(hour=0, minute=0, second=0, microsecond=0),
        )
    )


async def other_audio_usage(session, org):
    day = now().replace(hour=0, minute=0, second=0, microsecond=0)
    runs = (
        await session.scalars(
            select(ProcessingRun).where(
                ProcessingRun.organization_id == org,
                (ProcessingRun.created_at >= day)
                | ProcessingRun.status.not_in(("succeeded", "failed", "cancelled", "expired")),
            )
        )
    ).all()
    sessions = (
        await session.scalars(
            select(TrainingSession).where(
                TrainingSession.organization_id == org,
                (TrainingSession.created_at >= day) | TrainingSession.status.in_(("authorized", "active")),
            )
        )
    ).all()
    concurrent = sum(r.status not in {"succeeded", "failed", "cancelled", "expired"} for r in runs)
    concurrent += sum(s.status in {"authorized", "active"} and s.expires_at > now() for s in sessions)
    used = sum(
        r.usage.get("reserved", 0)
        for r in runs
        if r.created_at >= day and r.usage.get("unit") == "audio_seconds"
    )
    used += sum(s.duration_seconds for s in sessions if s.created_at >= day)
    return concurrent, used
