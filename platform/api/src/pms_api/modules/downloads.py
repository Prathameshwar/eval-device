"""Private, operator-published desktop releases. No tenant data or public file mounts."""

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from pms_api.core.common import AppError, require
from pms_api.core.dependencies import Session
from pms_api.database.models import Membership, Organization
from pms_api.security.access import Actor, human

router = APIRouter(tags=["downloads"])
PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


class Release(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Literal["desktop-cuda", "desktop-runtime", "desktop-cpu"]
    filename: str = Field(
        pattern=r"^Human-test-windows-x64-(cpu|cuda|runtime)-protected-[A-Za-z0-9-]+\.zip$", max_length=160
    )
    size_bytes: int = Field(gt=0, le=10_000_000_000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


async def admin_access(session: Session, actor: Actor) -> None:
    user = human(actor)
    if user.platform_role == "platform_admin":
        return
    membership = await session.scalar(
        select(Membership.id)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.user_id == user.id,
            Membership.role == "org_admin",
            Membership.department_id.is_(None),
            Membership.is_active.is_(True),
            Membership.invitation_status == "accepted",
            Membership.archived_at.is_(None),
            Organization.is_active.is_(True),
            Organization.archived_at.is_(None),
        )
        .limit(1)
    )
    require(membership is not None, "permission_denied", "Administrator access is required", 403)


def catalog(root: Path) -> list[Release]:
    """Bound metadata reads; never hash a multi-GB release during an HTTP request."""
    try:
        if root.is_symlink() or root.is_junction():
            raise ValueError("linked root")
        manifest = root / "catalog.json"
        if manifest.is_symlink() or manifest.is_junction():
            raise ValueError("linked manifest")
        if not manifest.exists():
            return []
        with manifest.open("rb") as stream:
            raw = stream.read(16_385)
        if len(raw) > 16_384:
            raise ValueError("catalog too large")
        entries = json.loads(raw)
        if not isinstance(entries, list) or len(entries) > 2:
            raise ValueError("invalid catalog")
        releases = [Release.model_validate(entry) for entry in entries]
        if len({release.id for release in releases}) != len(releases):
            raise ValueError("duplicate release")
        for release in releases:
            if f"-{release.id.removeprefix('desktop-')}-protected-" not in release.filename:
                raise ValueError("release edition mismatch")
            path = root / release.filename
            if path.is_symlink() or path.is_junction() or not path.is_file():
                raise ValueError("unavailable artifact")
            if path.stat().st_size != release.size_bytes:
                raise ValueError("artifact size mismatch")
        return releases
    except (OSError, ValueError, ValidationError) as exc:
        raise AppError(503, "downloads_unavailable", "Downloads are temporarily unavailable") from exc


@router.get("/downloads")
async def list_downloads(request: Request, session: Session, actor: Actor):
    await admin_access(session, actor)
    releases = await run_in_threadpool(catalog, request.app.state.settings.downloads_root)
    return {"items": [release.model_dump() for release in releases]}


@router.head("/downloads/{artifact_id}", include_in_schema=False)
@router.get("/downloads/{artifact_id}", response_class=FileResponse)
async def download(
    artifact_id: str,
    request: Request,
    session: Session,
    actor: Actor,
    sha256: str | None = Query(default=None, pattern=r"^[a-f0-9]{64}$"),
):
    await admin_access(session, actor)
    root = request.app.state.settings.downloads_root
    releases = await run_in_threadpool(catalog, root)
    release = next((item for item in releases if item.id == artifact_id), None)
    require(release is not None, "not_found", "Download not found", 404)
    assert release is not None
    require(
        sha256 is None or sha256 == release.sha256,
        "release_changed",
        "This release has changed. Refresh Downloads and start a new download",
        409,
    )
    # Release the authentication/read transaction before a potentially hours-long stream.
    # Browser authentication may update last-seen state, so commit rather than roll it back.
    await session.commit()
    return FileResponse(
        root / release.filename,
        filename={
            "desktop-cuda": "Desktop-App-GPU.zip",
            "desktop-runtime": "Desktop-App.zip",
            "desktop-cpu": "Desktop-App-CPU.zip",
        }[release.id],
        media_type="application/zip",
        headers={**PRIVATE_HEADERS, "ETag": f'"{release.sha256}"'},
    )
