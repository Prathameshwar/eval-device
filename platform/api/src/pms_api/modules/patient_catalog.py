"""Tenant-owned fictional clinical catalog; no platform-role content bypass."""

from typing import Annotated, Any, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from training_contracts import fingerprint
from training_contracts.clinical_cases import ClinicalRuntime
from training_contracts.languages import DEFAULT_REGISTRY
from training_contracts.localized_cases import (
    mark_system_starter_localization,
    prevent_review_forgery,
)
from training_contracts.scenarios import parse_draft, validate_publication

from pms_api.core.common import AppError, digest, now, require, required
from pms_api.core.dependencies import Session
from pms_api.core.starter_cases import corrected_starter
from pms_api.database.models import (
    Membership,
    Organization,
    OrganizationCaseTemplate,
    OrganizationClinicalSpecialty,
    OrganizationPatientProfile,
    PatientCaseTemplate,
    PatientIdentity,
    PlatformSettings,
    ScenarioCategory,
    TenantPatientSetupDefault,
    TenantScenarioDefault,
    TrainingScenario,
)
from pms_api.modules.common import audit, commit, directory_page, public
from pms_api.modules.patient_catalog_schemas import (
    CaseInput,
    CatalogBody,
    CatalogState,
    CatalogUpdate,
    CategoryInput,
    Code,
    Label,
    PatientInput,
)
from pms_api.modules.schemas import Input
from pms_api.security.access import Actor, effective_permissions, organization_access

router = APIRouter(prefix="/organizations/{organization_id}/clinical-catalog", tags=["Clinical catalog"])
Kind = Literal["specialties", "patients", "cases"]
MODELS: dict[str, Any] = {
    "specialties": OrganizationClinicalSpecialty,
    "patients": OrganizationPatientProfile,
    "cases": OrganizationCaseTemplate,
}
FORMS = {"specialties": CategoryInput, "patients": PatientInput, "cases": CaseInput}
CAPS = {"specialties": 200, "patients": 500, "cases": 1000}
GLOBAL_MODELS: dict[str, Any] = {
    "specialties": ScenarioCategory,
    "patients": PatientIdentity,
    "cases": PatientCaseTemplate,
}
SEED_IDS = {
    "specialties": frozenset(UUID(f"00000000-0000-4000-8000-{number:012d}") for number in (301, 302, 303)),
    "patients": frozenset({UUID("00000000-0000-4000-8000-000000000401")}),
    "cases": frozenset(UUID(f"00000000-0000-4000-8000-{number:012d}") for number in range(501, 510)),
}
SEED_REVISION = {"specialties": 1, "patients": 1, "cases": 4}
DEFAULT_PATIENT_ID = UUID("00000000-0000-4000-8000-000000000401")
DEFAULT_SPECIALTY_IDS = tuple(UUID(f"00000000-0000-4000-8000-{number:012d}") for number in (301, 302, 303))
DEFAULT_CASE_IDS = tuple(UUID(f"00000000-0000-4000-8000-{number:012d}") for number in (501, 507))


def seed_revision(kind: str, source_id: UUID) -> int:
    return 6 if kind == "cases" and source_id in DEFAULT_CASE_IDS else SEED_REVISION[kind]


def seed_current(kind, source):
    current = getattr(source, "revision" if kind == "cases" else "management_version")
    return current == seed_revision(kind, source.id) and (
        kind != "cases"
        or source.id not in DEFAULT_CASE_IDS
        or corrected_starter(source.id, current, source.document)
    )


def starter_runtime(document: dict) -> dict:
    """Validate the clinical starter without authored answers or scoring criteria."""
    require(
        not validate_publication(document), "case_starters_unavailable", "Case starters are incomplete", 503
    )
    return ClinicalRuntime(case=parse_draft(document)).model_dump(mode="json")


class CopyInput(Input):
    code: Code
    name: Label | None = None
    title: Label | None = None


def projection(row, *, detail: bool):
    result = public(row, exclude=set() if detail else {"document", "backgrounds", "occupations"})
    result["version"] = row.revision
    return result


async def access_for_read(session, actor, organization_id, *, lock=False):
    access = await organization_access(
        session, actor, organization_id, "org.status.read", lock_membership=lock
    )
    membership = required(await session.get(Membership, access.membership_id, populate_existing=True))
    permissions = await effective_permissions(session, membership)
    require(
        bool(permissions & {"org.clinical.author", "org.clinical.review", "org.clinical.read"}),
        "permission_denied",
        "Permission denied",
        403,
    )
    full = bool(permissions & {"org.clinical.author", "org.clinical.review"})
    return access, full


async def access_for_write(session, actor, organization_id):
    access = await organization_access(
        session, actor, organization_id, "org.clinical.author", lock_membership=True
    )
    organization = await session.scalar(
        select(Organization)
        .where(Organization.id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    require(
        organization is not None and organization.is_active and organization.archived_at is None,
        "organization_inactive",
        "Organization is inactive",
        409,
    )
    return access


async def record(session, model, organization_id, record_id, *, lock=False):
    query = select(model).where(model.organization_id == organization_id, model.id == record_id)
    if lock:
        query = query.with_for_update()
    return required(await session.scalar(query))


async def require_no_active_cases(session, organization_id, kind, record_id):
    relation = (
        OrganizationCaseTemplate.specialty_id
        if kind == "specialties"
        else OrganizationCaseTemplate.patient_profile_id
    )
    active_child = await session.scalar(
        select(OrganizationCaseTemplate.id)
        .where(
            OrganizationCaseTemplate.organization_id == organization_id,
            relation == record_id,
            OrganizationCaseTemplate.is_active.is_(True),
            OrganizationCaseTemplate.archived_at.is_(None),
        )
        .limit(1)
    )
    require(active_child is None, "catalog_in_use", "Deactivate active cases first", 409)


async def prepare(session, organization_id, kind, data, previous=None):
    require(isinstance(data, FORMS[kind]), "invalid_catalog_form", "Use the form for this catalog")
    values = data.model_dump(mode="json")
    if kind != "cases" and previous and previous.is_active and not data.is_active:
        await require_no_active_cases(session, organization_id, kind, previous.id)
    if kind == "cases":
        specialty = await record(session, OrganizationClinicalSpecialty, organization_id, data.specialty_id)
        patient = await record(session, OrganizationPatientProfile, organization_id, data.patient_profile_id)
        require(
            specialty.archived_at is None and patient.archived_at is None,
            "catalog_parent_archived",
            "Restore the specialty and patient profile first",
            409,
        )
        values["specialty_id"] = data.specialty_id
        values["patient_profile_id"] = data.patient_profile_id
        if previous:
            require(
                (previous.specialty_id, previous.patient_profile_id)
                == (data.specialty_id, data.patient_profile_id),
                "case_relationship_immutable",
                "Create a new case to change its parents",
                409,
            )
        document = values["document"]
        try:
            document = prevent_review_forgery(document, previous.document if previous else None)
            document["patient"] = {
                "name": patient.name,
                "age_years": patient.age_years,
                "sex": patient.sex,
                "occupation": patient.occupations,
                "height_cm": float(patient.height_cm),
                "weight_kg": float(patient.weight_kg),
            }
            document["specialty"] = specialty.name
            document = parse_draft(document).model_dump(mode="json", exclude_none=True)
        except ValueError:
            raise AppError(422, "invalid_case_document", "Correct the clinical case fields") from None
        if values["is_active"]:
            require(
                specialty.is_active and patient.is_active,
                "catalog_parent_inactive",
                "Activate the specialty and patient profile first",
                409,
            )
            issues = validate_publication(document)
            if issues:
                raise AppError(
                    422,
                    "case_incomplete",
                    "Complete the case before activating it",
                    [issue.model_dump() for issue in issues],
                )
        values["document"] = document
    return values


async def save(session, actor, organization_id, kind, row, action):
    try:
        await session.flush()
        await audit(
            session,
            actor,
            f"clinical_catalog.{action}",
            kind,
            row.id,
            organization_id,
            details={"revision": row.revision, "active": row.is_active},
        )
        await commit(session, row)
    except IntegrityError as error:
        await session.rollback()
        state = getattr(error.orig, "sqlstate", None)
        if state == "23505":
            raise AppError(409, "catalog_duplicate", "A record already uses this code or name") from None
        if state == "23514":
            raise AppError(
                409, "catalog_conflict", "The catalog limit or lifecycle rule was reached"
            ) from None
        raise
    return projection(row, detail=True)


@router.get("/options")
async def options(organization_id: UUID, session: Session, actor: Actor):
    _, full = await access_for_read(session, actor, organization_id)
    specialties = (
        await session.scalars(
            select(OrganizationClinicalSpecialty)
            .where(
                OrganizationClinicalSpecialty.organization_id == organization_id,
                OrganizationClinicalSpecialty.archived_at.is_(None),
            )
            .order_by(OrganizationClinicalSpecialty.sort_order, OrganizationClinicalSpecialty.name)
        )
    ).all()
    patients = (
        await session.scalars(
            select(OrganizationPatientProfile)
            .where(
                OrganizationPatientProfile.organization_id == organization_id,
                OrganizationPatientProfile.archived_at.is_(None),
            )
            .order_by(OrganizationPatientProfile.name)
        )
    ).all()
    settings = required(await session.get(PlatformSettings, 1))
    return {
        "specialties": [projection(row, detail=full) for row in specialties],
        "patients": [projection(row, detail=full) for row in patients],
        "languages": settings.languages,
        "conversation_languages": [{"code": p.language, "name": p.name} for p in DEFAULT_REGISTRY.all()],
    }


@router.get("/starters")
async def starters(organization_id: UUID, session: Session, actor: Actor):
    await organization_access(session, actor, organization_id, "org.clinical.author")
    items = []
    for kind in ("specialties", "patients", "cases"):
        sources = (
            await session.scalars(
                select(GLOBAL_MODELS[kind]).where(GLOBAL_MODELS[kind].id.in_(SEED_IDS[kind]))
            )
        ).all()
        imported = set(
            (
                await session.scalars(
                    select(MODELS[kind].source_global_id).where(
                        MODELS[kind].organization_id == organization_id,
                        MODELS[kind].source_global_id.in_(SEED_IDS[kind]),
                    )
                )
            ).all()
        )
        for source in sources:
            if not seed_current(kind, source):
                continue
            item = {
                "kind": kind,
                "id": source.id,
                "code": source.code,
                "name": source.title if kind == "cases" else source.name,
                "imported": source.id in imported,
            }
            if kind == "cases":
                case_source = cast(PatientCaseTemplate, source)
                item["specialty_id"] = case_source.category_id
                item["patient_profile_id"] = case_source.patient_identity_id
            items.append(item)
    return {"items": items}


@router.post("/cases/validate")
async def validate_case(organization_id: UUID, body: CaseInput, session: Session, actor: Actor):
    await access_for_write(session, actor, organization_id)
    prepared = await prepare(session, organization_id, "cases", body)
    return {"valid": True, "document": prepared["document"]}


def source_form(kind, source, *, code=None, name=None, title=None, specialty_id=None, patient_id=None):
    if kind == "specialties":
        label = name or source.name
        return CategoryInput(
            code=code or source.code,
            name=label,
            names={**source.names, "en": label},
            description=source.description,
            sort_order=source.sort_order,
            is_active=False,
        )
    if kind == "patients":
        label = name or source.name
        return PatientInput(
            code=code or source.code,
            name=label,
            names={**source.names, "en": label},
            age_years=source.age_years,
            sex=source.sex,
            occupations=source.occupations,
            height_cm=float(source.height_cm),
            weight_kg=float(source.weight_kg),
            preferred_language=source.preferred_language,
            languages=source.languages,
            backgrounds=source.backgrounds,
            is_active=False,
        )
    label = title or source.title
    document = {**source.document, "code": code or source.code, "title": label}
    return CaseInput(
        code=code or source.code,
        specialty_id=specialty_id or source.specialty_id,
        patient_profile_id=patient_id or source.patient_profile_id,
        title=label,
        titles={**source.titles, "en": label},
        document=document,
        is_active=False,
    )


async def seed_tenant_clinical_defaults(session, organization_id: UUID, actor: Actor) -> None:
    """Create independent reviewable clinical starters within the tenant creation transaction."""
    specialties = (
        await session.scalars(select(ScenarioCategory).where(ScenarioCategory.id.in_(DEFAULT_SPECIALTY_IDS)))
    ).all()
    require(
        len(specialties) == len(DEFAULT_SPECIALTY_IDS)
        and all(source.management_version == SEED_REVISION["specialties"] for source in specialties),
        "clinical_starters_unavailable",
        "Clinical specialty starters are missing or have changed; review the source catalog",
        503,
    )
    specialty_ids: dict[UUID, UUID] = {}
    for source in sorted(specialties, key=lambda item: (item.sort_order, item.code)):
        values = await prepare(session, organization_id, "specialties", source_form("specialties", source))
        values["is_active"] = True
        specialty = OrganizationClinicalSpecialty(
            id=uuid4(),
            organization_id=organization_id,
            revision=1,
            created_by=actor.id,
            updated_by=actor.id,
            source_global_id=source.id,
            source_global_revision=source.management_version,
            **values,
        )
        session.add(specialty)
        specialty_ids[source.id] = specialty.id
        await audit(
            session,
            actor,
            "platform.organization.clinical_specialty_seeded",
            "specialties",
            specialty.id,
            organization_id,
            details={"source_global_id": str(source.id), "revision": specialty.revision},
        )
    source = await session.get(PatientIdentity, DEFAULT_PATIENT_ID)
    require(
        source is not None and source.management_version == SEED_REVISION["patients"],
        "patient_starter_unavailable",
        "Patient starter is missing or has changed; review the source catalog",
        503,
    )
    assert source is not None
    values = await prepare(session, organization_id, "patients", source_form("patients", source))
    row = OrganizationPatientProfile(
        id=uuid4(),
        organization_id=organization_id,
        revision=1,
        created_by=actor.id,
        updated_by=actor.id,
        source_global_id=source.id,
        source_global_revision=source.management_version,
        **values,
    )
    session.add(row)
    await audit(
        session,
        actor,
        "platform.organization.patient_profile_seeded",
        "patients",
        row.id,
        organization_id,
        details={"source_global_id": str(source.id), "revision": row.revision},
    )
    await session.flush()
    case_sources = (
        await session.scalars(select(PatientCaseTemplate).where(PatientCaseTemplate.id.in_(DEFAULT_CASE_IDS)))
    ).all()
    require(
        len(case_sources) == len(DEFAULT_CASE_IDS)
        and all(seed_current("cases", source) for source in case_sources),
        "case_starters_unavailable",
        "Case starters are missing or have changed; review the source catalog",
        503,
    )
    default_case: OrganizationCaseTemplate | None = None
    default_scenario: TrainingScenario | None = None
    for case_source in sorted(case_sources, key=lambda item: item.code):
        require(
            case_source.category_id in specialty_ids
            and case_source.patient_identity_id == DEFAULT_PATIENT_ID,
            "case_starters_unavailable",
            "Case drafts are unavailable",
            503,
        )
        form = source_form(
            "cases",
            case_source,
            specialty_id=specialty_ids[case_source.category_id],
            patient_id=row.id,
        )
        document = form.document.model_dump(mode="json", exclude_none=True)
        form = CaseInput(**form.model_dump(mode="python", exclude={"document"}), document=document)
        case_values = await prepare(session, organization_id, "cases", form)
        case = OrganizationCaseTemplate(
            id=uuid4(),
            organization_id=organization_id,
            revision=1,
            created_by=actor.id,
            updated_by=actor.id,
            source_global_id=case_source.id,
            source_global_revision=case_source.revision,
            **case_values,
        )
        session.add(case)
        await session.flush()
        await audit(
            session,
            actor,
            "platform.organization.case_draft_seeded",
            "cases",
            case.id,
            organization_id,
            details={"source_global_id": str(case_source.id), "revision": case.revision},
        )
        # The bundled clinical example is technically complete, but is never
        # attributed to a tenant clinician. Its language stamps retain that origin.
        starter_runtime(case.document)
        scenario_document = case.document
        for language in ("en", "hi"):
            scenario_document = mark_system_starter_localization(scenario_document, language)
        scenario = TrainingScenario(
            id=uuid4(),
            organization_id=organization_id,
            request_key=uuid4(),
            code=case.code,
            version=1,
            document=scenario_document,
            fingerprint=fingerprint(scenario_document),
            created_by=actor.id,
            approved_at=now(),
            publication_source="system_starter",
            starter_case_id=case.id,
            specialty_id=case.specialty_id,
            is_active=True,
        )
        session.add(scenario)
        await audit(
            session,
            actor,
            "training.scenario.system_starter_published",
            "training_scenario",
            scenario.id,
            organization_id,
            details={"starter_case_id": str(case.id), "publication_source": "system_starter"},
        )
        if case_source.id == DEFAULT_CASE_IDS[0]:
            default_case = case
            default_scenario = scenario
    assert default_case is not None
    assert default_scenario is not None
    await session.flush()
    setup = TenantPatientSetupDefault(
        organization_id=organization_id,
        case_id=default_case.id,
        specialty_id=default_case.specialty_id,
        patient_profile_id=default_case.patient_profile_id,
        language="en",
        revision=1,
        created_by=actor.id,
        updated_by=actor.id,
    )
    session.add(setup)
    session.add(
        TenantScenarioDefault(
            organization_id=organization_id,
            scenario_id=default_scenario.id,
            language="en",
            revision=1,
            updated_by=actor.id,
        )
    )
    await audit(
        session,
        actor,
        "patient.practice.default_seeded",
        "tenant_patient_setup_default",
        organization_id,
        organization_id,
        details={"case_id": str(default_case.id), "revision": 1},
    )
    await audit(
        session,
        actor,
        "training.practice.default_seeded",
        "tenant_scenario_default",
        organization_id,
        organization_id,
        details={"scenario_id": str(default_scenario.id), "revision": 1},
    )


@router.post("/import/{kind}/{source_id}", status_code=201)
async def import_global(
    organization_id: UUID,
    kind: Kind,
    source_id: UUID,
    response: Response,
    session: Session,
    actor: Actor,
):
    await access_for_write(session, actor, organization_id)
    require(source_id in SEED_IDS[kind], "not_found", "Record not found", 404)
    existing = await session.scalar(
        select(MODELS[kind]).where(
            MODELS[kind].organization_id == organization_id,
            MODELS[kind].source_global_id == source_id,
        )
    )
    if existing is not None:
        response.status_code = 200
        return projection(existing, detail=True)
    source = required(await session.get(GLOBAL_MODELS[kind], source_id))
    require(
        seed_current(kind, source),
        "starter_modified",
        "This starter example needs review before import",
        409,
    )
    specialty_id = patient_id = None
    if kind == "cases":
        case_source = cast(PatientCaseTemplate, source)
        specialty_id = await session.scalar(
            select(OrganizationClinicalSpecialty.id).where(
                OrganizationClinicalSpecialty.organization_id == organization_id,
                OrganizationClinicalSpecialty.source_global_id == case_source.category_id,
                OrganizationClinicalSpecialty.archived_at.is_(None),
            )
        )
        patient_id = await session.scalar(
            select(OrganizationPatientProfile.id).where(
                OrganizationPatientProfile.organization_id == organization_id,
                OrganizationPatientProfile.source_global_id == case_source.patient_identity_id,
                OrganizationPatientProfile.archived_at.is_(None),
            )
        )
        require(
            specialty_id is not None and patient_id is not None,
            "import_parents_required",
            "Import the case specialty and patient profile first",
            409,
        )
    body = source_form(kind, source, specialty_id=specialty_id, patient_id=patient_id)
    values = await prepare(session, organization_id, kind, body)
    count = await session.scalar(
        select(func.count()).select_from(MODELS[kind]).where(MODELS[kind].organization_id == organization_id)
    )
    require((count or 0) < CAPS[kind], "catalog_limit", "This tenant catalog is full", 409)
    row = MODELS[kind](
        id=uuid4(),
        organization_id=organization_id,
        revision=1,
        created_by=actor.id,
        updated_by=actor.id,
        source_global_id=source_id,
        source_global_revision=getattr(source, "revision" if kind == "cases" else "management_version"),
        **values,
    )
    session.add(row)
    return await save(session, actor, organization_id, kind, row, "imported")


@router.post("/{kind}/{record_id}/copy", status_code=201)
async def copy_record(
    organization_id: UUID,
    kind: Kind,
    record_id: UUID,
    body: CopyInput,
    session: Session,
    actor: Actor,
):
    await access_for_write(session, actor, organization_id)
    source = await record(session, MODELS[kind], organization_id, record_id)
    require(source.archived_at is None, "catalog_archived", "Restore this record before copying", 409)
    require(
        body.name is not None if kind != "cases" else body.title is not None,
        "copy_label_required",
        "Provide a name or title for the copy",
        422,
    )
    form = source_form(kind, source, code=body.code, name=body.name, title=body.title)
    values = await prepare(session, organization_id, kind, form)
    count = await session.scalar(
        select(func.count()).select_from(MODELS[kind]).where(MODELS[kind].organization_id == organization_id)
    )
    require((count or 0) < CAPS[kind], "catalog_limit", "This tenant catalog is full", 409)
    row = MODELS[kind](
        id=uuid4(),
        organization_id=organization_id,
        revision=1,
        created_by=actor.id,
        updated_by=actor.id,
        **values,
    )
    session.add(row)
    return await save(session, actor, organization_id, kind, row, "copied")


@router.get("/{kind}")
async def directory(
    organization_id: UUID,
    kind: Kind,
    request: Request,
    session: Session,
    actor: Actor,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: str | None = None,
    q: Annotated[str, Query(max_length=128)] = "",
    state: Literal["active", "inactive", "all"] = "all",
    specialty_id: UUID | None = None,
    patient_profile_id: UUID | None = None,
):
    await access_for_read(session, actor, organization_id)
    model = MODELS[kind]
    title = model.title if kind == "cases" else model.name
    query = select(model).where(model.organization_id == organization_id)
    if q:
        query = query.where(
            or_(title.icontains(q, autoescape=True), model.code.icontains(q, autoescape=True))
        )
    if state != "all":
        query = query.where(model.is_active == (state == "active"))
    if kind == "cases":
        if specialty_id:
            query = query.where(OrganizationCaseTemplate.specialty_id == specialty_id)
        if patient_profile_id:
            query = query.where(OrganizationCaseTemplate.patient_profile_id == patient_profile_id)
    rows, next_cursor, has_more, total = await directory_page(
        session,
        query,
        model,
        limit=limit,
        cursor=cursor,
        sort="name",
        direction="asc",
        expression=title,
        binding=digest([str(organization_id), kind, q, state, str(specialty_id), str(patient_profile_id)]),
        secret=request.app.state.settings.token_pepper.get_secret_value(),
        include_total=True,
    )
    return {
        "items": [projection(row, detail=False) for row in rows],
        "total": total,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.post("/{kind}", status_code=201)
async def create(organization_id: UUID, kind: Kind, body: CatalogBody, session: Session, actor: Actor):
    await access_for_write(session, actor, organization_id)
    model = MODELS[kind]
    count = await session.scalar(
        select(func.count()).select_from(model).where(model.organization_id == organization_id)
    )
    require((count or 0) < CAPS[kind], "catalog_limit", "This tenant catalog is full", 409)
    values = await prepare(session, organization_id, kind, body)
    row = model(
        id=uuid4(),
        organization_id=organization_id,
        revision=1,
        created_by=actor.id,
        updated_by=actor.id,
        **values,
    )
    session.add(row)
    return await save(session, actor, organization_id, kind, row, "created")


@router.get("/{kind}/{record_id}")
async def detail(organization_id: UUID, kind: Kind, record_id: UUID, session: Session, actor: Actor):
    _, full = await access_for_read(session, actor, organization_id)
    return projection(await record(session, MODELS[kind], organization_id, record_id), detail=full)


@router.patch("/{kind}/{record_id}")
async def update(
    organization_id: UUID,
    kind: Kind,
    record_id: UUID,
    body: CatalogUpdate,
    session: Session,
    actor: Actor,
):
    await access_for_write(session, actor, organization_id)
    row = await record(session, MODELS[kind], organization_id, record_id, lock=True)
    require(row.revision == body.expected_version, "version_conflict", "Reload before saving", 409)
    require(row.archived_at is None, "catalog_archived", "Restore this record before editing", 409)
    require(row.code == body.data.code, "catalog_code_immutable", "The code cannot change", 409)
    values = await prepare(session, organization_id, kind, body.data, row)
    for key, value in values.items():
        setattr(row, key, value)
    row.revision += 1
    row.updated_by = actor.id
    return await save(session, actor, organization_id, kind, row, "updated")


async def change_state(session, actor, organization_id, kind, record_id, expected_version, active):
    await access_for_write(session, actor, organization_id)
    row = await record(session, MODELS[kind], organization_id, record_id, lock=True)
    require(row.revision == expected_version, "version_conflict", "Reload before continuing", 409)
    if active:
        if kind == "cases":
            values = {key: getattr(row, key) for key in CaseInput.model_fields}
            values["is_active"] = True
            prepared = await prepare(session, organization_id, kind, CaseInput(**values), row)
            row.document = prepared["document"]
        row.archived_at = None
        row.is_active = True
    else:
        if kind != "cases":
            await require_no_active_cases(session, organization_id, kind, record_id)
        row.is_active = False
        row.archived_at = now()
    row.revision += 1
    row.updated_by = actor.id
    return await save(session, actor, organization_id, kind, row, "restored" if active else "archived")


@router.delete("/{kind}/{record_id}")
async def archive(
    organization_id: UUID,
    kind: Kind,
    record_id: UUID,
    session: Session,
    actor: Actor,
    expected_version: Annotated[int, Query(gt=0)],
):
    return await change_state(session, actor, organization_id, kind, record_id, expected_version, False)


@router.post("/{kind}/{record_id}/restore")
async def restore(
    organization_id: UUID,
    kind: Kind,
    record_id: UUID,
    body: CatalogState,
    session: Session,
    actor: Actor,
):
    return await change_state(session, actor, organization_id, kind, record_id, body.expected_version, True)
