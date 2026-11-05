"""Private staff rehearsal setup, separate from approved learner training sessions."""

from copy import deepcopy
from uuid import UUID, uuid4

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from training_contracts.languages import DEFAULT_REGISTRY, LanguageTag, get_pack
from training_contracts.localized_cases import (
    convert_v2,
    localization_ready,
    mark_practice_override,
    review_localization,
)
from training_contracts.scenarios import Vitals

from pms_api.core.common import AppError, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    Membership,
    Organization,
    OrganizationCaseTemplate,
    OrganizationClinicalSpecialty,
    OrganizationPatientProfile,
    PatientPracticeSelection,
    TenantPatientSetupDefault,
    TenantScenarioDefault,
    TrainingScenario,
)
from pms_api.modules.common import audit, commit, public
from pms_api.modules.scenarios import author_access
from pms_api.security.access import Actor, organization_access, reload_actor
from pms_api.security.practice_access import execution_access, owner_filter, owner_values

router = APIRouter(prefix="/organizations/{organization_id}/patient-practice", tags=["Patient practice"])


class SaveSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0, le=2147483645, strict=True)
    template_id: UUID
    template_revision: int = Field(ge=1, le=2147483646, strict=True)
    category_id: UUID
    patient_identity_id: UUID
    language: LanguageTag = "en"
    vitals: Vitals

    @field_validator("language")
    @classmethod
    def supported_language(cls, value):
        return get_pack(value).language

    @model_validator(mode="after")
    def blood_pressure(self):
        if any(v is None for v in self.vitals.model_dump().values()):
            raise ValueError("All initial vital signs are required")
        if self.vitals.systolic_mmhg is not None and self.vitals.diastolic_mmhg is not None:
            if self.vitals.systolic_mmhg < self.vitals.diastolic_mmhg:
                raise ValueError("Systolic pressure must not be lower than diastolic pressure")
        return self


class SaveTenantDefault(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1, le=2147483645, strict=True)
    template_id: UUID
    template_revision: int = Field(ge=1, le=2147483646, strict=True)
    language: LanguageTag = "en"

    @field_validator("language")
    @classmethod
    def supported_language(cls, value):
        return get_pack(value).language


class SaveScenarioSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0, le=2147483645, strict=True)
    scenario_id: UUID
    language: LanguageTag = "en"
    vitals: Vitals

    @model_validator(mode="after")
    def complete_vitals(self):
        if any(value is None for value in self.vitals.model_dump().values()):
            raise ValueError("All initial vital signs are required")
        if (
            self.vitals.systolic_mmhg is not None
            and self.vitals.diastolic_mmhg is not None
            and self.vitals.systolic_mmhg < self.vitals.diastolic_mmhg
        ):
            raise ValueError("Systolic pressure must not be lower than diastolic pressure")
        return self


class SaveScenarioDefault(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0, le=2147483645, strict=True)
    scenario_id: UUID
    language: LanguageTag = "en"


async def access(session, actor, org, *, lock=False):
    await author_access(session, actor, org, lock=lock)
    await organization_access(session, actor, org, "org.processing.execute")


async def scenario_practice_access(session, actor, org, *, lock=False):
    if actor.device:
        await execution_access(session, actor, org, "org.processing.execute", lock=lock)
        return
    scope = await organization_access(session, actor, org, "org.processing.execute")
    require(scope.department_id is None, "scope_unavailable", "Organization-wide access required", 403)
    await organization_access(session, actor, org, "org.results.read")
    if lock:
        await session.get(Organization, org, with_for_update=True, populate_existing=True)
        actor = await reload_actor(session, user_id=actor.id)
        scope = await organization_access(session, actor, org, "org.processing.execute")
        require(scope.department_id is None, "scope_unavailable", "Organization-wide access required", 403)
        await organization_access(session, actor, org, "org.results.read")


async def published_scenario(session, organization_id, scenario_id, language):
    row = required(
        await session.scalar(
            select(TrainingScenario).where(
                TrainingScenario.organization_id == organization_id,
                TrainingScenario.id == scenario_id,
            )
        )
    )
    require(
        row.is_active and row.approved_at is not None,
        "scenario_unavailable",
        "Choose an active published scenario",
        409,
    )
    require(
        row.document.get("version") in (4, 5) and localization_ready(row.document, language),
        "scenario_language_unavailable",
        "This scenario is not ready for practice in that language",
        409,
    )
    return row


async def active_template(session, organization_id, template_id):
    template = required(
        await session.scalar(
            select(OrganizationCaseTemplate).where(
                OrganizationCaseTemplate.organization_id == organization_id,
                OrganizationCaseTemplate.id == template_id,
            )
        )
    )
    identity = required(
        await session.scalar(
            select(OrganizationPatientProfile).where(
                OrganizationPatientProfile.organization_id == organization_id,
                OrganizationPatientProfile.id == template.patient_profile_id,
            )
        )
    )
    category = required(
        await session.scalar(
            select(OrganizationClinicalSpecialty).where(
                OrganizationClinicalSpecialty.organization_id == organization_id,
                OrganizationClinicalSpecialty.id == template.specialty_id,
            )
        )
    )
    require(
        template.is_active
        and identity.is_active
        and category.is_active
        and template.archived_at is None
        and identity.archived_at is None
        and category.archived_at is None,
        "patient_case_inactive",
        "The selected patient or case is unavailable",
        409,
    )
    return template, identity, category


async def own_selection(session, actor, org, *, lock=False):
    query = (
        select(PatientPracticeSelection)
        .where(PatientPracticeSelection.organization_id == org, owner_filter(PatientPracticeSelection, actor))
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update()
    return await session.scalar(query)


async def practice_for_request(session, actor, org, practice_id, revision):
    await scenario_practice_access(session, actor, org)
    row = required(await own_selection(session, actor, org))
    require(row.id == practice_id, "not_found", "Patient setup not found", 404)
    require(row.revision == revision, "patient_setup_changed", "Patient setup changed; reload it", 409)
    require(
        row.language in {pack.language for pack in DEFAULT_REGISTRY.all()},
        "patient_language_required",
        "Choose an available language in Patient setup and save before starting the interview",
        409,
    )
    if row.scenario_id is not None:
        await published_scenario(session, org, row.scenario_id, row.language)
    else:
        await access(session, actor, org)
        require(
            row.tenant_template_id is not None,
            "legacy_patient_setup",
            "Select a published scenario before starting",
            409,
        )
        await active_template(session, org, row.tenant_template_id)
    return row


def selection_view(row):
    value = public(row, exclude={"user_id", "organization_id"})
    value["template_id"] = row.tenant_template_id or row.template_id
    value["category_id"] = row.tenant_category_id or row.category_id
    value["patient_identity_id"] = row.tenant_patient_identity_id or row.patient_identity_id
    value["scenario_id"] = row.scenario_id
    value["legacy"] = row.scenario_id is None and row.tenant_template_id is None
    return value


def default_view(row):
    return {
        "template_id": row.case_id,
        "category_id": row.specialty_id,
        "patient_identity_id": row.patient_profile_id,
        "language": row.language,
        "revision": row.revision,
    }


@router.get("/catalog")
async def catalog(organization_id: UUID, actor: Actor, session: Session):
    await access(session, actor, organization_id)
    categories = (
        await session.scalars(
            select(OrganizationClinicalSpecialty)
            .where(
                OrganizationClinicalSpecialty.organization_id == organization_id,
                OrganizationClinicalSpecialty.is_active.is_(True),
                OrganizationClinicalSpecialty.archived_at.is_(None),
            )
            .order_by(OrganizationClinicalSpecialty.sort_order)
        )
    ).all()
    identities = (
        await session.scalars(
            select(OrganizationPatientProfile)
            .where(
                OrganizationPatientProfile.organization_id == organization_id,
                OrganizationPatientProfile.is_active.is_(True),
                OrganizationPatientProfile.archived_at.is_(None),
            )
            .order_by(OrganizationPatientProfile.name)
        )
    ).all()
    cases = (
        await session.scalars(
            select(OrganizationCaseTemplate)
            .where(
                OrganizationCaseTemplate.organization_id == organization_id,
                OrganizationCaseTemplate.is_active.is_(True),
                OrganizationCaseTemplate.archived_at.is_(None),
                OrganizationCaseTemplate.specialty_id.in_([c.id for c in categories]),
                OrganizationCaseTemplate.patient_profile_id.in_([p.id for p in identities]),
            )
            .order_by(OrganizationCaseTemplate.title)
        )
    ).all()
    return {
        "categories": [{**public(c), "version": c.revision} for c in categories],
        "patients": [{**public(p), "version": p.revision} for p in identities],
        "cases": [
            {
                **public(c, exclude={"document"}),
                "category_id": c.specialty_id,
                "patient_identity_id": c.patient_profile_id,
                "version": c.revision,
            }
            for c in cases
        ],
        "mode": "staff_rehearsal",
        "languages": [
            {"code": p.language, "name": p.name, "pack_version": p.version} for p in DEFAULT_REGISTRY.all()
        ],
    }


@router.get("/cases/{template_id}")
async def case(organization_id: UUID, template_id: UUID, actor: Actor, session: Session):
    await access(session, actor, organization_id)
    row, _, _ = await active_template(session, organization_id, template_id)
    return {
        **public(row),
        "category_id": row.specialty_id,
        "patient_identity_id": row.patient_profile_id,
        "version": row.revision,
    }


@router.get("/selection")
async def selection(organization_id: UUID, actor: Actor, session: Session):
    await access(session, actor, organization_id)
    row = await own_selection(session, actor, organization_id)
    default = await session.get(TenantPatientSetupDefault, organization_id)
    # Return even an inactive previous choice so the UI can explain and replace it.
    return {
        "selection": selection_view(row) if row else None,
        "default": default_view(default) if default else None,
    }


@router.get("/scenario-options")
async def scenario_options(organization_id: UUID, actor: Actor, session: Session, cursor: UUID | None = None):
    await scenario_practice_access(session, actor, organization_id)
    rows = (
        await session.scalars(
            select(TrainingScenario)
            .where(
                TrainingScenario.organization_id == organization_id,
                TrainingScenario.is_active.is_(True),
                TrainingScenario.approved_at.is_not(None),
            )
            .where(TrainingScenario.id > cursor if cursor else TrainingScenario.id.is_not(None))
            .order_by(TrainingScenario.id)
            .limit(101)
        )
    ).all()
    default = await session.get(TenantScenarioDefault, organization_id)
    selection = await own_selection(session, actor, organization_id)
    return {
        "next_cursor": str(rows[99].id) if len(rows) > 100 else None,
        "items": [
            {
                "id": row.id,
                "title": row.document.get("title") or "Patient interview",
                "specialty": row.document.get("specialty"),
                "version": row.version,
                "languages": [
                    language
                    for language in ("en", "hi")
                    if row.document.get("version") in (4, 5) and localization_ready(row.document, language)
                ],
                "vitals": row.document.get("vitals") or {},
                "publication_source": row.publication_source,
            }
            for row in rows[:100]
        ],
        "default": {
            "scenario_id": default.scenario_id,
            "language": default.language,
            "revision": default.revision,
        }
        if default
        else None,
        "selection": selection_view(selection) if selection else None,
    }


@router.get("/scenario-selection")
async def scenario_selection(organization_id: UUID, actor: Actor, session: Session):
    await scenario_practice_access(session, actor, organization_id)
    row = await own_selection(session, actor, organization_id)
    return {"selection": selection_view(row) if row and row.scenario_id is not None else None}


@router.put("/scenario-default")
async def save_scenario_default(
    organization_id: UUID, body: SaveScenarioDefault, actor: Actor, session: Session
):
    await author_access(session, actor, organization_id, lock=True)
    scope = await organization_access(
        session, actor, organization_id, "org.processing.execute", lock_membership=True
    )
    member = required(await session.get(Membership, scope.membership_id, populate_existing=True))
    require(member.role == "org_admin", "permission_denied", "Tenant administrator access required", 403)
    default = await session.get(TenantScenarioDefault, organization_id, with_for_update=True)
    require(
        (default.revision if default else 0) == body.expected_revision,
        "scenario_default_changed",
        "The default changed; reload before saving",
        409,
    )
    await published_scenario(session, organization_id, body.scenario_id, body.language)
    if default is None:
        default = TenantScenarioDefault(
            organization_id=organization_id,
            scenario_id=body.scenario_id,
            language=body.language,
            revision=1,
            updated_by=actor.id,
        )
        session.add(default)
    else:
        default.scenario_id = body.scenario_id
        default.language = body.language
        default.revision += 1
        default.updated_by = actor.id
    await audit(
        session,
        actor,
        "training.practice.default_updated",
        "tenant_scenario_default",
        organization_id,
        organization_id,
        {"scenario_id": str(body.scenario_id), "revision": default.revision},
    )
    await commit(session, default)
    return {
        "default": {
            "scenario_id": default.scenario_id,
            "language": default.language,
            "revision": default.revision,
        }
    }


@router.put("/scenario-selection")
async def save_scenario_selection(
    organization_id: UUID, body: SaveScenarioSelection, actor: Actor, session: Session
):
    await scenario_practice_access(session, actor, organization_id, lock=True)
    if actor.device:
        from pms_api.database.models import PatientConversation, PracticeSession

        active = await session.scalar(
            select(PracticeSession).where(
                PracticeSession.device_id == actor.id, PracticeSession.status.in_(("active", "stopping"))
            )
        )
        if active:
            conversation = await session.scalar(
                select(PatientConversation.id).where(PatientConversation.assigned_session_id == active.id)
            )
            require(
                conversation is None
                and active.status == "active"
                and active.scenario_id == body.scenario_id
                and active.language == body.language,
                "session_assignment_changed",
                "Finish the assigned session before changing setup",
                409,
            )
    row = await own_selection(session, actor, organization_id, lock=True)
    require(
        (row.revision if row else 0) == body.expected_revision,
        "patient_setup_changed",
        "Practice selection changed; reload before saving",
        409,
    )
    scenario = await published_scenario(session, organization_id, body.scenario_id, body.language)
    document = mark_practice_override(scenario.document, body.language, body.vitals.model_dump(mode="json"))
    if row is None:
        row = PatientPracticeSelection(
            id=uuid4(), organization_id=organization_id, **owner_values(actor), revision=1
        )
        session.add(row)
    else:
        row.revision += 1
    row.template_id = row.category_id = row.patient_identity_id = None
    row.tenant_template_id = row.tenant_category_id = row.tenant_patient_identity_id = None
    row.scenario_id = scenario.id
    row.template_revision = scenario.version
    row.document = document
    row.language = body.language
    await audit(
        session,
        actor,
        "training.practice.scenario_selected",
        "patient_practice",
        row.id,
        organization_id,
        {"scenario_id": str(scenario.id), "version": scenario.version, "revision": row.revision},
    )
    await commit(session, row)
    return {"selection": selection_view(row)}


@router.put("/default")
async def save_tenant_default(organization_id: UUID, body: SaveTenantDefault, actor: Actor, session: Session):
    await access(session, actor, organization_id, lock=True)
    scope = await organization_access(
        session, actor, organization_id, "org.clinical.author", lock_membership=True
    )
    member = required(await session.get(Membership, scope.membership_id, populate_existing=True))
    require(member.role == "org_admin", "permission_denied", "Tenant administrator access required", 403)
    default = required(await session.get(TenantPatientSetupDefault, organization_id, with_for_update=True))
    require(
        default.revision == body.expected_revision,
        "patient_default_changed",
        "The tenant default changed; reload before saving",
        409,
    )
    template, identity, category = await active_template(session, organization_id, body.template_id)
    require(
        template.revision == body.template_revision,
        "patient_case_changed",
        "The case changed; reload before choosing a tenant default",
        409,
    )
    require(
        body.language in identity.languages,
        "patient_language_unavailable",
        "Complete the case and patient profile in this language before choosing a tenant default",
        422,
    )
    default.case_id = template.id
    default.specialty_id = category.id
    default.patient_profile_id = identity.id
    default.language = body.language
    default.revision += 1
    default.updated_by = actor.id
    await audit(
        session,
        actor,
        "patient.practice.default_updated",
        "tenant_patient_setup_default",
        organization_id,
        organization_id,
        {"revision": default.revision, "case_id": str(default.case_id)},
    )
    await commit(session, default)
    return {"default": default_view(default)}


@router.put("/selection")
async def save(organization_id: UUID, body: SaveSelection, actor: Actor, session: Session):
    await access(session, actor, organization_id, lock=True)
    row = await own_selection(session, actor, organization_id, lock=True)
    require(
        (row.revision if row else 0) == body.expected_revision,
        "patient_setup_changed",
        "Patient setup changed; reload before saving",
        409,
    )
    template, identity, _ = await active_template(session, organization_id, body.template_id)
    require(
        template.revision == body.template_revision,
        "patient_case_changed",
        "The case changed; reload before saving",
        409,
    )
    require(
        template.specialty_id == body.category_id and identity.id == body.patient_identity_id,
        "patient_case_mismatch",
        "The case does not belong to the selected category and patient",
        422,
    )
    document = deepcopy(template.document)
    if document.get("version") == 2:
        document = convert_v2(document)
    document["patient"] = {
        "name": identity.name,
        "age_years": identity.age_years,
        "sex": identity.sex,
        "occupation": identity.occupations,
        "height_cm": float(identity.height_cm),
        "weight_kg": float(identity.weight_kg),
    }
    document["vitals"] = body.vitals.model_dump(mode="json")
    # Completeness/disclosure rules also run after edits; no arbitrary patient prompt is accepted.
    try:
        document = review_localization(document, body.language)
    except ValueError:
        raise AppError(
            422,
            "patient_language_unavailable",
            "Complete the case and patient profile in this language before saving patient setup",
        ) from None
    if row is None:
        row = PatientPracticeSelection(
            id=uuid4(), organization_id=organization_id, **owner_values(actor), revision=1
        )
        session.add(row)
    else:
        row.revision += 1
    row.template_id = row.category_id = row.patient_identity_id = None
    row.tenant_template_id = template.id
    row.scenario_id = None
    row.tenant_category_id = template.specialty_id
    row.tenant_patient_identity_id = identity.id
    row.template_revision, row.document, row.language = template.revision, document, body.language
    await audit(
        session,
        actor,
        "patient.practice.saved",
        "patient_practice",
        row.id,
        organization_id,
        {"revision": row.revision, "template_id": str(template.id), "template_revision": template.revision},
    )
    await commit(session, row)
    return {"selection": selection_view(row)}
