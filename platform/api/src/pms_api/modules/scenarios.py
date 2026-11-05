"""Tenant-private scenario library. Mutations serialize organization before draft."""

import base64
import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Response
from pydantic import ValidationError
from sqlalchemy import Text, cast, func, literal, select, tuple_, update
from sqlalchemy.dialects.postgresql import JSONB
from training_contracts import canonical, fingerprint
from training_contracts.clinical_cases import ClinicalRuntime
from training_contracts.localized_cases import (
    localization_ready,
    prevent_review_forgery,
    review_localization,
)
from training_contracts.scenarios import (
    Issue,
    normalize_draft,
    parse_draft,
    patient_preview,
    validate_publication,
)

from pms_api.core.common import AppError, now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    Membership,
    Organization,
    OrganizationCaseTemplate,
    OrganizationClinicalSpecialty,
    OrganizationPatientProfile,
    PlatformSettings,
    TrainingScenario,
    TrainingScenarioDraft,
)
from pms_api.modules.common import audit, commit
from pms_api.modules.scenario_schemas import (
    DraftCreate,
    DraftCreated,
    DraftPage,
    DraftPublish,
    DraftSave,
    DraftState,
    DraftSubmit,
    DraftSummary,
    DraftValidate,
    DraftView,
    LocalizationReview,
    SafeScenario,
    ScenarioPage,
    ScenarioPublished,
    ScenarioSummary,
    ScenarioView,
    ValidationView,
)
from pms_api.security.access import Actor, effective_permissions, organization_access, reload_actor

router = APIRouter(prefix="/organizations/{organization_id}/training", tags=["Scenario library"])
PageLimit = Annotated[int, Query(ge=1, le=100)]
Search = Annotated[str | None, Query(min_length=1, max_length=120)]
Cursor = Annotated[str | None, Query(max_length=1024)]


async def clinical_access(session, actor, organization_id, permission, *, lock=False):
    access = await organization_access(session, actor, organization_id, permission)
    require(access.department_id is None, "scope_unavailable", "Organization-wide access is required", 403)
    if lock:
        await session.get(Organization, organization_id, with_for_update=True, populate_existing=True)
        actor = await reload_actor(session, user_id=actor.id)
        access = await organization_access(session, actor, organization_id, permission)
        require(
            access.department_id is None, "scope_unavailable", "Organization-wide access is required", 403
        )
        settings = required(await session.get(PlatformSettings, 1, populate_existing=True))
        require(not settings.maintenance_mode, "maintenance_mode", "Scenario changes are paused", 503)
    return access


async def author_access(session, actor, organization_id, *, lock=False):
    return await clinical_access(session, actor, organization_id, "org.clinical.author", lock=lock)


async def reviewer_access(session, actor, organization_id, *, lock=False):
    return await clinical_access(session, actor, organization_id, "org.clinical.review", lock=lock)


async def reader_access(session, actor, organization_id):
    access = await organization_access(session, actor, organization_id, "org.status.read")
    member = required(await session.get(Membership, access.membership_id, populate_existing=True))
    permissions = await effective_permissions(session, member)
    require(
        bool(permissions & {"org.clinical.author", "org.clinical.review"}),
        "permission_denied",
        "Permission denied",
        403,
    )
    return access


async def active_source_case(session, organization_id, case_id):
    source = required(
        await session.scalar(
            select(OrganizationCaseTemplate).where(
                OrganizationCaseTemplate.organization_id == organization_id,
                OrganizationCaseTemplate.id == case_id,
            )
        )
    )
    specialty = required(
        await session.scalar(
            select(OrganizationClinicalSpecialty).where(
                OrganizationClinicalSpecialty.organization_id == organization_id,
                OrganizationClinicalSpecialty.id == source.specialty_id,
            )
        )
    )
    patient = required(
        await session.scalar(
            select(OrganizationPatientProfile).where(
                OrganizationPatientProfile.organization_id == organization_id,
                OrganizationPatientProfile.id == source.patient_profile_id,
            )
        )
    )
    require(
        all(row.is_active and row.archived_at is None for row in (source, specialty, patient)),
        "case_source_inactive",
        "Activate the source case and its parents",
        409,
    )
    return source


async def active_specialty(session, organization_id, specialty_id):
    row = required(
        await session.scalar(
            select(OrganizationClinicalSpecialty).where(
                OrganizationClinicalSpecialty.organization_id == organization_id,
                OrganizationClinicalSpecialty.id == specialty_id,
            )
        )
    )
    require(
        row.is_active and row.archived_at is None,
        "specialty_inactive",
        "Choose an active tenant clinical specialty",
        409,
    )
    return row


async def draft_row(session, organization_id, draft_id, *, lock=False):
    query = (
        select(TrainingScenarioDraft)
        .where(TrainingScenarioDraft.organization_id == organization_id, TrainingScenarioDraft.id == draft_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update()
    return required(await session.scalar(query))


async def locked_draft(session, actor, organization_id, draft_id):
    await author_access(session, actor, organization_id, lock=True)
    row = await draft_row(session, organization_id, draft_id, lock=True)
    # A separate draft locker may have delayed us after the organization check.
    await author_access(session, await reload_actor(session, user_id=actor.id), organization_id, lock=True)
    return row


def expected_revision(row, expected):
    require(row.revision == expected, "draft_revision_conflict", "Draft changed; reload before editing", 409)


def require_runtime(document):
    require(
        document.get("version") in (4, 5)
        and not validate_publication(document)
        and all(localization_ready(document, language) for language in ("en", "hi")),
        "scenario_runtime_unsupported",
        "Complete and review English and Hindi before assigning this scenario",
        409,
    )
    return ClinicalRuntime(case=parse_draft(document)).model_dump(mode="json")


def runtime_supported(document):
    try:
        require_runtime(document)
        return True
    except AppError:
        return False


def draft_summary(row):
    return DraftSummary(
        id=row.id,
        code=row.code,
        schema_version=row.schema_version,
        title=row.document.get("title"),
        specialty=row.document.get("specialty"),
        revision=row.revision,
        is_archived=row.is_archived,
        source_scenario_id=row.source_scenario_id,
        source_case_id=row.source_case_id,
        source_case_revision=row.source_case_revision,
        specialty_id=row.specialty_id,
        workflow_version=row.workflow_version,
        submitted_revision=row.submitted_revision,
        submitted_at=row.submitted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def draft_view(row):
    return DraftView(
        **draft_summary(row).model_dump(),
        document=row.document,
        created_by=row.created_by,
        updated_by=row.updated_by,
    )


def scenario_summary(row, private=False):
    version = row.document.get("version", 1)
    values = dict(
        id=row.id,
        title=row.document.get("learner_label") or "Patient interview",
        version=row.version,
        schema_version=version,
        languages=(
            [
                language
                for language in row.document.get("localizations", {})
                if localization_ready(row.document, language)
            ]
            if version in (4, 5)
            else ["en", "hi"]
        ),
        approved=row.approved_at is not None,
        is_active=row.is_active,
        execution_supported=runtime_supported(row.document),
        publication_source=row.publication_source,
    )
    if private:
        return ScenarioSummary(
            **{**values, "title": row.document.get("title") or "Untitled scenario"},
            code=row.code,
            specialty=row.document.get("specialty"),
            specialty_id=row.specialty_id,
        )
    return SafeScenario(**values)


def scenario_view(row):
    return ScenarioView(
        **scenario_summary(row, True).model_dump(),
        document=row.document,
        fingerprint=row.fingerprint,
        created_at=row.created_at,
        created_by=row.created_by,
        approved_at=row.approved_at,
        approved_by=row.approved_by,
        approval=row.approval,
        source_draft_id=row.source_draft_id,
        source_draft_revision=row.source_draft_revision,
        starter_case_id=row.starter_case_id,
    )


async def paged(session, query, model, limit, cursor, scope):
    binding = fingerprint(scope)
    if cursor:
        try:
            data = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
            if (
                not isinstance(data, dict)
                or set(data) != {"scope", "created_at", "id"}
                or any(not isinstance(value, str) for value in data.values())
                or data["scope"] != binding
            ):
                raise ValueError("invalid scope")
            timestamp = datetime.fromisoformat(data["created_at"])
            if timestamp.tzinfo is None:
                raise ValueError("timezone required")
            identifier = UUID(data["id"])
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise AppError(422, "invalid_cursor", "Cursor is invalid for this query") from None
        query = query.where(
            tuple_(model.created_at, model.id) < tuple_(literal(timestamp), literal(identifier))
        )
    rows = list(
        (
            await session.scalars(query.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1))
        ).all()
    )
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = base64.urlsafe_b64encode(
            canonical(
                {"scope": binding, "created_at": last.created_at.isoformat(), "id": str(last.id)}
            ).encode()
        ).decode()
    return rows[:limit], next_cursor


@router.get("/scenarios", response_model=ScenarioPage)
async def list_scenarios(
    organization_id: UUID,
    actor: Actor,
    session: Session,
    limit: PageLimit = 100,
    cursor: Cursor = None,
    q: Search = None,
    code: Search = None,
    specialty: Search = None,
    status: Literal["all", "approved", "unapproved", "retired"] | None = None,
    schema_version: Literal["4", "5", "current", "all"] = "current",
):
    access = await organization_access(session, actor, organization_id, "org.results.read")
    member = required(await session.get(Membership, access.membership_id, populate_existing=True))
    permissions = await effective_permissions(session, member)
    private = (
        bool(permissions & {"org.clinical.author", "org.clinical.review"}) and access.department_id is None
    )
    require(
        private or (code is None and specialty is None and status is None),
        "private_filter_denied",
        "This filter requires author access",
        403,
    )
    query = select(TrainingScenario).where(TrainingScenario.organization_id == organization_id)
    if schema_version == "current":
        query = query.where(TrainingScenario.document["version"].astext.in_(["4", "5"]))
    elif schema_version != "all":
        query = query.where(TrainingScenario.document["version"].astext == schema_version)
    if not private or status == "approved":
        query = query.where(TrainingScenario.approved_at.is_not(None), TrainingScenario.is_active.is_(True))
    elif status == "unapproved":
        query = query.where(TrainingScenario.approved_at.is_(None), TrainingScenario.is_active.is_(True))
    elif status == "retired":
        query = query.where(TrainingScenario.is_active.is_(False))
    label = (
        TrainingScenario.document["title"].astext
        if private
        else func.coalesce(TrainingScenario.document["learner_label"].astext, "Patient interview")
    )
    if q:
        query = query.where(func.lower(label).contains(q.lower(), autoescape=True))
    if code:
        query = query.where(TrainingScenario.code == code)
    if specialty:
        query = query.where(TrainingScenario.document["specialty"].astext == specialty)
    rows, next_cursor = await paged(
        session,
        query,
        TrainingScenario,
        limit,
        cursor,
        {
            "org": str(organization_id),
            "actor": str(actor.id),
            "private": private,
            "department": str(access.department_id),
            "kind": "scenarios",
            "q": q,
            "code": code,
            "specialty": specialty,
            "status": status,
            "schema_version": schema_version,
        },
    )
    return ScenarioPage(items=[scenario_summary(row, private) for row in rows], next_cursor=next_cursor)


@router.get("/scenarios/{scenario_id}", response_model=ScenarioView | SafeScenario)
async def get_scenario(organization_id: UUID, scenario_id: UUID, actor: Actor, session: Session):
    access = await organization_access(session, actor, organization_id, "org.results.read")
    row = required(
        await session.scalar(
            select(TrainingScenario).where(
                TrainingScenario.organization_id == organization_id, TrainingScenario.id == scenario_id
            )
        )
    )
    member = required(await session.get(Membership, access.membership_id, populate_existing=True))
    permissions = await effective_permissions(session, member)
    if permissions & {"org.clinical.author", "org.clinical.review"} and access.department_id is None:
        return scenario_view(row)
    require(row.approved_at and row.is_active, "not_found", "Scenario not found", 404)
    return scenario_summary(row)


async def normalized(session, document, previous=None):
    try:
        if document.get("version") in (4, 5):
            document = prevent_review_forgery(document, previous)
        value = normalize_draft(document)
    except (ValidationError, ValueError):
        raise AppError(422, "invalid_scenario", "Scenario content violates the authoring contract") from None
    # PostgreSQL's JSONB text representation has its own independent storage budget.
    size = await session.scalar(select(func.octet_length(cast(literal(value, type_=JSONB), Text))))
    require(
        size <= (524288 if value.get("version") in (4, 5) else 65536),
        "scenario_too_large",
        "Scenario exceeds the storage budget",
        422,
    )
    return value


@router.post("/scenario-drafts", status_code=201, response_model=DraftCreated)
async def create_draft(
    organization_id: UUID,
    body: DraftCreate,
    response: Response,
    actor: Actor,
    session: Session,
):
    await author_access(session, actor, organization_id, lock=True)
    semantics = body.model_dump(mode="json", exclude_none=True)
    selected_specialty = (
        await active_specialty(session, organization_id, body.specialty_id) if body.specialty_id else None
    )
    if body.source_scenario_id is None and body.source_case_id is None:
        version = body.document.version if body.document else (body.schema_version or 4)
        contents = (
            body.document.model_dump(mode="json", exclude_none=True)
            if body.document
            else {"version": version, "code": body.code}
        )
        if selected_specialty:
            contents["specialty"] = selected_specialty.name
        document = await normalized(
            session,
            contents,
        )
        semantics = {
            "code": body.code,
            "schema_version": version,
            "document": document,
            "specialty_id": str(body.specialty_id) if body.specialty_id else None,
        }
    request_fingerprint = fingerprint(
        {"request": semantics, "actor": str(actor.id), "org": str(organization_id)}
    )
    existing = await session.scalar(
        select(TrainingScenarioDraft).where(
            TrainingScenarioDraft.organization_id == organization_id,
            TrainingScenarioDraft.request_key == body.request_key,
        )
    )
    if existing:
        require(
            existing.request_fingerprint == request_fingerprint,
            "idempotency_conflict",
            "Request key already has different content or author",
            409,
        )
        response.status_code = 200
        return DraftCreated(draft=draft_view(existing), replayed=True)
    require(
        not await session.scalar(
            select(TrainingScenarioDraft.id).where(
                TrainingScenarioDraft.organization_id == organization_id,
                TrainingScenarioDraft.code == body.code,
            )
        ),
        "draft_code_conflict",
        "A draft already exists for this code",
        409,
    )
    count = await session.scalar(
        select(func.count())
        .select_from(TrainingScenarioDraft)
        .where(TrainingScenarioDraft.organization_id == organization_id)
    )
    require((count or 0) < 100, "draft_capacity", "Organization draft capacity reached", 429)
    source_case_revision = None
    if body.source_scenario_id is not None:
        source = required(
            await session.scalar(
                select(TrainingScenario).where(
                    TrainingScenario.organization_id == organization_id,
                    TrainingScenario.id == body.source_scenario_id,
                )
            )
        )
        document = await normalized(
            session,
            {
                **source.document,
                "code": body.code,
                **({"localizations": {}} if source.document.get("version") in (4, 5) else {}),
            },
        )
        require(
            body.specialty_id in (None, source.specialty_id),
            "specialty_mismatch",
            "Copied scenario has a different specialty",
            422,
        )
        selected_specialty = (
            await active_specialty(session, organization_id, source.specialty_id)
            if source.specialty_id
            else None
        )
    if body.source_case_id is not None:
        source_case = await active_source_case(session, organization_id, body.source_case_id)
        source_case_revision = source_case.revision
        document = await normalized(
            session,
            {
                **source_case.document,
                "code": body.code,
                **({"localizations": {}} if source_case.document.get("version") in (4, 5) else {}),
            },
        )
        require(
            body.specialty_id in (None, source_case.specialty_id),
            "specialty_mismatch",
            "Copied case has a different specialty",
            422,
        )
        selected_specialty = await active_specialty(session, organization_id, source_case.specialty_id)
    row = TrainingScenarioDraft(
        id=uuid4(),
        organization_id=organization_id,
        request_key=body.request_key,
        request_fingerprint=request_fingerprint,
        code=body.code,
        schema_version=document["version"],
        workflow_version=2 if document["version"] in (4, 5) else 1,
        document=document,
        source_scenario_id=body.source_scenario_id,
        source_case_id=body.source_case_id,
        source_case_revision=source_case_revision,
        specialty_id=selected_specialty.id if selected_specialty else None,
        content_updated_by=actor.id,
        created_by=actor.id,
        updated_by=actor.id,
    )
    session.add(row)
    await audit(session, actor, "training.draft.created", "training_scenario_draft", row.id, organization_id)
    await commit(session, row)
    return DraftCreated(draft=draft_view(row), replayed=False)


@router.get("/scenario-drafts", response_model=DraftPage)
async def list_drafts(
    organization_id: UUID,
    actor: Actor,
    session: Session,
    limit: PageLimit = 50,
    cursor: Cursor = None,
    q: Search = None,
    code: Search = None,
    specialty: Search = None,
    archived: bool = False,
):
    await reader_access(session, actor, organization_id)
    query = select(TrainingScenarioDraft).where(
        TrainingScenarioDraft.organization_id == organization_id,
        TrainingScenarioDraft.is_archived == archived,
    )
    if q:
        query = query.where(
            func.lower(TrainingScenarioDraft.document["title"].astext).contains(q.lower(), autoescape=True)
        )
    if code:
        query = query.where(TrainingScenarioDraft.code == code)
    if specialty:
        query = query.where(TrainingScenarioDraft.document["specialty"].astext == specialty)
    rows, next_cursor = await paged(
        session,
        query,
        TrainingScenarioDraft,
        limit,
        cursor,
        {
            "org": str(organization_id),
            "actor": str(actor.id),
            "kind": "drafts",
            "q": q,
            "code": code,
            "specialty": specialty,
            "archived": archived,
        },
    )
    return DraftPage(items=[draft_summary(row) for row in rows], next_cursor=next_cursor)


@router.get("/scenario-drafts/{draft_id}", response_model=DraftView)
async def get_draft(organization_id: UUID, draft_id: UUID, actor: Actor, session: Session):
    await reader_access(session, actor, organization_id)
    return draft_view(await draft_row(session, organization_id, draft_id))


async def save_change(session, actor, row, revision, values, action, details=None):
    expected_revision(row, revision)
    changed = await session.scalar(
        update(TrainingScenarioDraft)
        .where(
            TrainingScenarioDraft.organization_id == row.organization_id,
            TrainingScenarioDraft.id == row.id,
            TrainingScenarioDraft.revision == revision,
        )
        .values(**values, revision=revision, updated_by=actor.id)
        .returning(TrainingScenarioDraft.id)
        .execution_options(synchronize_session=False)
    )
    require(changed is not None, "draft_revision_conflict", "Draft changed; reload before editing", 409)
    await audit(
        session, actor, action, "training_scenario_draft", row.id, row.organization_id, details=details
    )
    await commit(session, row)
    return draft_view(row)


@router.put("/scenario-drafts/{draft_id}", response_model=DraftView)
async def save_draft(organization_id: UUID, draft_id: UUID, body: DraftSave, actor: Actor, session: Session):
    row = await locked_draft(session, actor, organization_id, draft_id)
    expected_revision(row, body.expected_revision)
    require(not row.is_archived, "draft_archived", "Restore the draft before editing", 409)
    require(
        body.document.code == row.code
        and (
            body.document.version == row.schema_version
            or (row.schema_version == 4 and body.document.version == 5)
        ),
        "draft_identity_conflict",
        "Draft code and schema version cannot change",
        409,
    )
    specialty_id = body.specialty_id or row.specialty_id
    if row.source_case_id is not None:
        source = await active_source_case(session, organization_id, row.source_case_id)
        require(
            specialty_id == source.specialty_id,
            "specialty_mismatch",
            "Copied case specialty cannot change",
            422,
        )
    if row.source_scenario_id is not None:
        source_scenario = required(
            await session.scalar(
                select(TrainingScenario).where(
                    TrainingScenario.organization_id == organization_id,
                    TrainingScenario.id == row.source_scenario_id,
                )
            )
        )
        require(
            specialty_id == source_scenario.specialty_id,
            "specialty_mismatch",
            "Copied scenario specialty cannot change",
            422,
        )
    selected_specialty = (
        await active_specialty(session, organization_id, specialty_id) if specialty_id else None
    )
    contents = body.document.model_dump(mode="json", exclude_none=True)
    if selected_specialty:
        contents["specialty"] = selected_specialty.name
    document = await normalized(session, contents, row.document)
    changed = document != row.document or specialty_id != row.specialty_id
    return await save_change(
        session,
        actor,
        row,
        body.expected_revision,
        {
            "document": document,
            "schema_version": document["version"],
            "specialty_id": specialty_id,
            "content_updated_by": actor.id if document != row.document else row.content_updated_by,
            "submitted_revision": (
                None
                if changed
                else row.revision + 1
                if row.submitted_revision == row.revision
                else row.submitted_revision
            ),
            "submitted_at": None if changed else row.submitted_at,
        },
        "training.draft.saved",
    )


@router.post("/scenario-drafts/{draft_id}/submit", response_model=DraftView)
async def submit_draft(
    organization_id: UUID, draft_id: UUID, body: DraftSubmit, actor: Actor, session: Session
):
    row = await locked_draft(session, actor, organization_id, draft_id)
    expected_revision(row, body.expected_revision)
    require(not row.is_archived, "draft_archived", "Restore the draft before submitting", 409)
    require(row.specialty_id is not None, "specialty_required", "Choose a tenant clinical specialty", 422)
    await active_specialty(session, organization_id, row.specialty_id)
    if row.source_case_id is not None:
        source = await active_source_case(session, organization_id, row.source_case_id)
        require(
            source.revision == row.source_case_revision,
            "case_source_stale",
            "Refresh the draft from the current tenant case",
            409,
        )
    issues = validate_publication(row.document)
    if issues:
        raise AppError(
            422,
            "scenario_incomplete",
            "Complete the draft before submitting",
            [issue.model_dump() for issue in issues],
        )
    return await save_change(
        session,
        actor,
        row,
        body.expected_revision,
        {"submitted_revision": row.revision + 1, "submitted_at": now()},
        "training.draft.submitted",
        {"revision": row.revision + 1},
    )


@router.post("/scenario-drafts/{draft_id}/refresh-case", response_model=DraftView)
async def refresh_case(
    organization_id: UUID, draft_id: UUID, body: DraftValidate, actor: Actor, session: Session
):
    row = await locked_draft(session, actor, organization_id, draft_id)
    expected_revision(row, body.expected_revision)
    require(
        not row.is_archived and row.source_case_id is not None,
        "case_refresh_unavailable",
        "This draft has no active source case",
        409,
    )
    source = await active_source_case(session, organization_id, row.source_case_id)
    require(
        source.revision != row.source_case_revision,
        "case_source_unchanged",
        "The source case has not changed",
        409,
    )
    refreshed = {**source.document, "code": row.code}
    if source.document.get("version") in (4, 5):
        refreshed["localizations"] = {}
    if row.schema_version == 5 and source.document.get("version") == 4:
        # A clinical-only source cannot replace background authored in this draft.
        refreshed.update(version=5, background=row.document.get("background", []))
    document = await normalized(session, refreshed, row.document)
    require(
        document["version"] == row.schema_version or (row.schema_version == 4 and document["version"] == 5),
        "case_schema_changed",
        "Create a new draft for a different case format",
        409,
    )
    return await save_change(
        session,
        actor,
        row,
        body.expected_revision,
        {
            "document": document,
            "schema_version": document["version"],
            "source_case_revision": source.revision,
            "content_updated_by": actor.id if document != row.document else row.content_updated_by,
            "submitted_revision": None,
            "submitted_at": None,
        },
        "training.draft.case_refreshed",
        {"source_case_id": str(source.id), "source_case_revision": source.revision},
    )


@router.patch("/scenario-drafts/{draft_id}", response_model=DraftView)
async def archive_draft(
    organization_id: UUID, draft_id: UUID, body: DraftState, actor: Actor, session: Session
):
    row = await locked_draft(session, actor, organization_id, draft_id)
    return await save_change(
        session,
        actor,
        row,
        body.expected_revision,
        {
            "is_archived": body.is_archived,
            "submitted_revision": None if body.is_archived else row.submitted_revision,
            "submitted_at": None if body.is_archived else row.submitted_at,
        },
        "training.draft.archived" if body.is_archived else "training.draft.restored",
    )


@router.post("/scenario-drafts/{draft_id}/validate", response_model=ValidationView)
async def validate_draft(
    organization_id: UUID, draft_id: UUID, body: DraftValidate, actor: Actor, session: Session
):
    await reader_access(session, actor, organization_id)
    row = await draft_row(session, organization_id, draft_id)
    expected_revision(row, body.expected_revision)
    errors = validate_publication(row.document)
    if row.is_archived:
        errors.append(
            Issue(path=["is_archived"], code="draft_archived", message="Restore the draft before publication")
        )
    if row.source_case_id is not None:
        source = await active_source_case(session, organization_id, row.source_case_id)
        if source.revision != row.source_case_revision:
            errors.append(
                Issue(
                    path=["source_case_id"],
                    code="case_source_stale",
                    message="Refresh the draft from the current tenant case",
                )
            )
    warnings = [
        Issue(
            path=[],
            code="educator_review_required",
            message="Technical validation does not establish clinical accuracy",
        )
    ]
    if row.schema_version in (4, 5) and not row.document.get("vitals"):
        warnings.append(
            Issue(
                path=["vitals"],
                code="vitals_not_configured",
                message="Initial vital signs are not configured",
            )
        )
    return ValidationView(
        draft_id=row.id,
        revision=row.revision,
        publishable=not errors,
        errors=errors,
        warnings=warnings,
        preview=patient_preview(row.document),
    )


@router.post("/scenario-drafts/{draft_id}/localizations/{language}/review", response_model=DraftView)
async def review_translation(
    organization_id: UUID,
    draft_id: UUID,
    language: str,
    body: LocalizationReview,
    actor: Actor,
    session: Session,
):
    await reviewer_access(session, actor, organization_id, lock=True)
    row = await draft_row(session, organization_id, draft_id, lock=True)
    await reviewer_access(session, actor, organization_id, lock=True)
    expected_revision(row, body.expected_revision)
    require(
        row.content_updated_by != actor.id,
        "reviewer_is_author",
        "A different reviewer must review this content",
        403,
    )
    require(
        not row.is_archived and row.schema_version in (4, 5),
        "localization_unavailable",
        "Review requires an active clinical draft",
        409,
    )
    if row.workflow_version == 2:
        require(
            row.submitted_revision == row.revision,
            "draft_not_submitted",
            "Submit this revision before review",
            409,
        )
    try:
        document = review_localization(row.document, language)
    except ValueError:
        raise AppError(422, "translation_incomplete", "Complete the case translation before review") from None
    return await save_change(
        session,
        actor,
        row,
        body.expected_revision,
        {
            "document": document,
            "submitted_revision": row.revision + 1 if row.workflow_version == 2 else None,
            "submitted_at": row.submitted_at,
        },
        "training.localization.reviewed",
        details={"language": language, "approval": body.approval.model_dump(mode="json")},
    )


@router.post("/scenario-drafts/{draft_id}/publish", status_code=201, response_model=ScenarioPublished)
async def publish_draft(
    organization_id: UUID,
    draft_id: UUID,
    body: DraftPublish,
    response: Response,
    actor: Actor,
    session: Session,
):
    await reviewer_access(session, actor, organization_id, lock=True)
    row = await draft_row(session, organization_id, draft_id, lock=True)
    await reviewer_access(session, actor, organization_id, lock=True)
    approval = body.approval.model_dump(mode="json")
    require(
        len(canonical(approval).encode()) <= 3800, "approval_too_large", "Approval exceeds the storage budget"
    )
    existing = await session.scalar(
        select(TrainingScenario).where(
            TrainingScenario.organization_id == organization_id,
            TrainingScenario.request_key == body.request_key,
        )
    )
    if existing:
        require(
            existing.source_draft_id == row.id
            and existing.source_draft_revision == body.expected_revision
            and existing.approved_by == actor.id
            and existing.approval == approval,
            "idempotency_conflict",
            "Request key already has different publication content or approver",
            409,
        )
        response.status_code = 200
        return ScenarioPublished(scenario=scenario_view(existing), replayed=True)
    expected_revision(row, body.expected_revision)
    require(
        row.content_updated_by != actor.id,
        "reviewer_is_author",
        "A different reviewer must publish this content",
        403,
    )
    require(not row.is_archived, "draft_archived", "Restore the draft before publication", 409)
    if row.source_case_id is not None:
        source = await active_source_case(session, organization_id, row.source_case_id)
        require(
            source.revision == row.source_case_revision,
            "case_source_stale",
            "Refresh the draft from the current tenant case",
            409,
        )
    issues = validate_publication(row.document)
    if issues:
        raise AppError(
            422,
            "scenario_incomplete",
            "Complete the draft before publication",
            [issue.model_dump() for issue in issues],
        )
    if row.workflow_version == 2:
        require(
            row.submitted_revision == row.revision,
            "draft_not_submitted",
            "Submit this revision before publication",
            409,
        )
        require(row.specialty_id is not None, "specialty_required", "Choose a tenant clinical specialty", 422)
        await active_specialty(session, organization_id, row.specialty_id)
    if row.schema_version in (4, 5):
        require(
            localization_ready(row.document, row.document["source_language"]),
            "translation_review_required",
            "Review the source-language content before publication",
            409,
        )
    duplicate = await session.scalar(
        select(TrainingScenario.id).where(
            TrainingScenario.organization_id == organization_id,
            TrainingScenario.source_draft_id == row.id,
            TrainingScenario.source_draft_revision == row.revision,
        )
    )
    if duplicate:
        raise AppError(
            409,
            "draft_revision_published",
            "This draft revision is already published",
            {"scenario_id": str(duplicate)},
        )
    count = await session.scalar(
        select(func.count())
        .select_from(TrainingScenario)
        .where(TrainingScenario.organization_id == organization_id)
    )
    require((count or 0) < 100, "scenario_capacity", "Organization scenario capacity reached", 429)
    version = (
        await session.scalar(
            select(func.max(TrainingScenario.version)).where(
                TrainingScenario.organization_id == organization_id, TrainingScenario.code == row.code
            )
        )
        or 0
    ) + 1
    case = TrainingScenario(
        id=uuid4(),
        organization_id=organization_id,
        request_key=body.request_key,
        code=row.code,
        version=version,
        document=row.document,
        fingerprint=fingerprint(row.document),
        created_by=row.content_updated_by,
        approved_at=now(),
        approved_by=actor.id,
        approval=approval,
        source_draft_id=row.id,
        source_draft_revision=row.revision,
        specialty_id=row.specialty_id,
    )
    session.add(case)
    await audit(
        session,
        actor,
        "training.scenario.published",
        "training_scenario",
        case.id,
        organization_id,
        details={"source_draft_id": str(row.id), "source_draft_revision": row.revision},
    )
    await commit(session, case)
    return ScenarioPublished(scenario=scenario_view(case), replayed=False)
