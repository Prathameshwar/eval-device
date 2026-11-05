"""Explicit ORM mappings for the versioned PostgreSQL contract.

DDL constraints/functions/indexes are owned by the versioned Alembic migrations.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    FetchedValue,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "device_platform"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


class ScenarioCategory(Base):
    """Shared reference data; it contains no tenant patient content."""

    management_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), server_onupdate=FetchedValue()
    )
    __tablename__ = "scenario_categories"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    names: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )


class PatientIdentity(Base):
    """Deployment-managed fictional templates; scenarios retain their own snapshots."""

    management_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), server_onupdate=FetchedValue()
    )
    __tablename__ = "patient_identities"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    names: Mapped[dict] = mapped_column(JSONB, nullable=False)
    age_years: Mapped[int] = mapped_column(Integer, nullable=False)
    sex: Mapped[str] = mapped_column(Text, nullable=False)
    occupations: Mapped[dict] = mapped_column(JSONB, nullable=False)
    height_cm: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    preferred_language: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'en'"))
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("ARRAY['en','hi']")
    )
    backgrounds: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_fictional: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )


class PatientCaseTemplate(Base):
    __tablename__ = "patient_case_templates"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(Text)
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    patient_identity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(Text)
    titles: Mapped[dict] = mapped_column(JSONB, nullable=False)
    document: Mapped[dict] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class OrganizationClinicalSpecialty(Base):
    __tablename__ = "organization_clinical_specialties"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    names: Mapped[dict] = mapped_column(JSONB)
    description: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_global_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_global_revision: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class OrganizationPatientProfile(Base):
    __tablename__ = "organization_patient_profiles"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    names: Mapped[dict] = mapped_column(JSONB)
    age_years: Mapped[int] = mapped_column(Integer)
    sex: Mapped[str] = mapped_column(Text)
    occupations: Mapped[dict] = mapped_column(JSONB)
    height_cm: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    preferred_language: Mapped[str] = mapped_column(Text)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text))
    backgrounds: Mapped[dict] = mapped_column(JSONB)
    is_fictional: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_global_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_global_revision: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class OrganizationCaseTemplate(Base):
    __tablename__ = "organization_case_templates"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    code: Mapped[str] = mapped_column(Text)
    specialty_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    patient_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(Text)
    titles: Mapped[dict] = mapped_column(JSONB)
    document: Mapped[dict] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_global_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_global_revision: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class PatientPracticeSelection(Base):
    __tablename__ = "patient_practice_selections"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    patient_identity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tenant_template_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tenant_category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tenant_patient_identity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    template_revision: Mapped[int] = mapped_column(Integer)
    document: Mapped[dict] = mapped_column(JSONB)
    language: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class TenantPatientSetupDefault(Base):
    __tablename__ = "tenant_patient_setup_defaults"
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    specialty_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    patient_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    language: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class PatientConversation(Base):
    """Fixed tenant/owner context with bounded, server-owned cloud runtime state."""

    __tablename__ = "patient_conversations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    assigned_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fingerprint: Mapped[str] = mapped_column(Text)
    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    scenario_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    context: Mapped[dict] = mapped_column(JSONB)
    snapshot: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer)
    history: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeviceSessionQueue(Base):
    __tablename__ = "device_session_queues"
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    runtime_state: Mapped[str] = mapped_column(Text, default="offline")


class PracticeSession(Base):
    __tablename__ = "practice_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    learner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    instructor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    scenario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    batch_index: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(Text)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    credential_version: Mapped[int | None] = mapped_column(Integer)
    runtime_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    price_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    billing_period: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unspecified'"))
    max_users: Mapped[int] = mapped_column(Integer, nullable=False)
    max_devices: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    configuration_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), server_onupdate=FetchedValue()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )


class Organization(Base):
    __tablename__ = "organizations"
    subscription_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    subscription_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    subscription_reference: Mapped[str | None] = mapped_column(Text)
    subscription_notes: Mapped[str | None] = mapped_column(Text)
    subscription_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), server_onupdate=FetchedValue()
    )
    subscription_plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    subscription_assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    status_changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    management_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_settings: Mapped[dict] = mapped_column(JSONB(none_as_null=True), nullable=False)
    suspension_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Department(Base):
    __tablename__ = "departments"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    status_changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    management_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class User(Base):
    __tablename__ = "users"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    status_changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    management_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    auth_method: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'oidc'"))
    identity_issuer: Mapped[str | None] = mapped_column(Text, nullable=True)
    identity_subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LocalCredential(Base):
    __tablename__ = "local_credentials"
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    login_email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    setup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class LocalSession(Base):
    __tablename__ = "local_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    browser_token_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class AccountActionToken(Base):
    __tablename__ = "account_action_tokens"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False)
    target_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    key_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    category: Mapped[str] = mapped_column(Text, primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountEmailOutbox(Base):
    __tablename__ = "account_email_outbox"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    recipient: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Membership(Base):
    __tablename__ = "organization_memberships"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    status_changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    management_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    invitation_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    invitation_auth_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    invited_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    invitation_token_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    invitation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemberCapability(Base):
    __tablename__ = "organization_member_capabilities"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    membership_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    capability: Mapped[str] = mapped_column(Text, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    granted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class DeviceIdentity(Base):
    """One permanent physical identity; tenant registrations retain their own UUIDs."""

    __tablename__ = "device_identities"
    device_unique_id: Mapped[str] = mapped_column(Text, primary_key=True)


class Device(Base):
    preferred_language: Mapped[str | None] = mapped_column(Text, nullable=True)
    __tablename__ = "devices"
    __mapper_args__ = {"eager_defaults": True}
    device_unique_id: Mapped[str] = mapped_column(Text, nullable=False)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    status_changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    device_type: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'org_device'"))
    details: Mapped[dict] = mapped_column(
        JSONB(none_as_null=True), nullable=False, server_default=text("'{}'::jsonb")
    )
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_profile_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    applied_configuration_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_error: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    capabilities: Mapped[dict] = mapped_column(
        JSONB(none_as_null=True), nullable=False, server_default=text("'{}'::jsonb")
    )
    enrollment_state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    enrollment_token_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    enrollment_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enrollment_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    credential_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), server_onupdate=FetchedValue()
    )
    credential_issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_onupdate=FetchedValue()
    )
    credential_revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_onupdate=FetchedValue()
    )
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    offline_authorized_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_telemetry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_health: Mapped[dict] = mapped_column(
        JSONB(none_as_null=True), nullable=False, server_default=text("'{}'::jsonb")
    )


class ProviderConnection(Base):
    encrypted_credentials: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    credential_key_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    __tablename__ = "provider_connections"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    status_changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    connection_type: Mapped[str] = mapped_column(Text, nullable=False)
    auth_mode: Mapped[str] = mapped_column(Text, nullable=False)
    settings: Mapped[dict] = mapped_column(
        JSONB(none_as_null=True), nullable=False, server_default=text("'{}'::jsonb")
    )
    secret_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    configuration_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), server_onupdate=FetchedValue()
    )
    validation_results: Mapped[dict] = mapped_column(
        JSONB(none_as_null=True),
        nullable=False,
        server_default=text("'{}'::jsonb"),
        server_onupdate=FetchedValue(),
    )
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_onupdate=FetchedValue()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProcessingProfile(Base):
    retired_assignments: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    draft_llm_connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    __tablename__ = "processing_profiles"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    status_changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    management_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_settings: Mapped[dict] = mapped_column(
        JSONB(none_as_null=True),
        nullable=False,
        server_default=text(
            '\'{"schema_version":1,"audio_input":{"enabled":false},"video":{"enabled":false},"audio_output":{"enabled":false}}\'::jsonb'
        ),
    )
    draft_audio_input_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    draft_video_connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    draft_audio_output_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    published_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class ProfileRevision(Base):
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    llm_connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    __tablename__ = "processing_profile_revisions"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB(none_as_null=True), nullable=False)
    audio_input_connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    video_connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    audio_output_connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    published_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProcessingRun(Base):
    __tablename__ = "processing_runs"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    profile_revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    capture_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    execution_mode: Mapped[str] = mapped_column(Text, nullable=False)
    engine: Mapped[str] = mapped_column(Text, nullable=False)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    effective_settings: Mapped[dict] = mapped_column(JSONB(none_as_null=True), nullable=False)
    request: Mapped[dict] = mapped_column(
        JSONB(none_as_null=True), nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_submission_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'not_submitted'")
    )
    provider_job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    error: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    usage: Mapped[dict] = mapped_column(
        JSONB(none_as_null=True), nullable=False, server_default=text("'{}'::jsonb")
    )
    media_manifest: Mapped[list[dict]] = mapped_column(
        JSONB(none_as_null=True), nullable=False, server_default=text("'[]'::jsonb")
    )
    media_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleanup_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'not_required'"))
    cleanup_next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    playback_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'not_requested'"))
    playback_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    playback_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TelemetrySample(Base):
    __tablename__ = "device_telemetry_samples"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    boot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    metrics: Mapped[dict] = mapped_column(JSONB(none_as_null=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'info'"))
    entity_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    details: Mapped[dict] = mapped_column(
        JSONB(none_as_null=True), nullable=False, server_default=text("'{}'::jsonb")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlatformSettings(Base):
    languages: Mapped[list[dict]] = mapped_column(
        JSONB(none_as_null=True),
        nullable=False,
        server_default=text(
            """'[ {"code":"en","name":"English","speech_locale":"en-IN","is_active":true}, {"code":"hi","name":"Hindi","speech_locale":"hi-IN","is_active":true} ]'::jsonb"""
        ),
    )
    __tablename__ = "platform_settings"
    __mapper_args__ = {"eager_defaults": True}
    id: Mapped[int] = mapped_column(SmallInteger, nullable=False, primary_key=True, server_default=text("1"))
    display_name: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'Device Platform'"))
    registration_mode: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'self_service'")
    )
    enabled_providers: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    default_organization_policy: Mapped[dict] = mapped_column(JSONB(none_as_null=True), nullable=False)
    policy_limits: Mapped[dict] = mapped_column(JSONB(none_as_null=True), nullable=False)
    device_defaults: Mapped[dict] = mapped_column(JSONB(none_as_null=True), nullable=False)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    configuration_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), server_onupdate=FetchedValue()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), server_onupdate=FetchedValue()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


TABLE_MODELS = {
    "organizations": Organization,
    "departments": Department,
    "users": User,
    "organization_memberships": Membership,
    "devices": Device,
    "provider_connections": ProviderConnection,
    "processing_profiles": ProcessingProfile,
    "processing_profile_revisions": ProfileRevision,
    "processing_runs": ProcessingRun,
    "device_telemetry_samples": TelemetrySample,
    "activity_events": ActivityEvent,
    "platform_settings": PlatformSettings,
}


class TrainingScenario(Base):
    __tablename__ = "training_scenarios"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    code: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    document: Mapped[dict] = mapped_column(JSONB)
    fingerprint: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    source_draft_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_draft_revision: Mapped[int | None] = mapped_column(Integer)
    publication_source: Mapped[str] = mapped_column(Text, server_default=text("'tenant_review'"))
    starter_case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    specialty_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class TrainingScenarioDraft(Base):
    __tablename__ = "training_scenario_drafts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    request_fingerprint: Mapped[str] = mapped_column(Text)
    code: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[int] = mapped_column(SmallInteger)
    document: Mapped[dict] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"), server_onupdate=FetchedValue())
    source_scenario_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_case_revision: Mapped[int | None] = mapped_column(Integer)
    specialty_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    workflow_version: Mapped[int] = mapped_column(SmallInteger, server_default=text("2"))
    submitted_revision: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue(), server_onupdate=FetchedValue()
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class TenantScenarioDefault(Base):
    __tablename__ = "tenant_scenario_defaults"
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    scenario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    language: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class TrainingSession(Base):
    __tablename__ = "training_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    learner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    instructor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    scenario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fingerprint: Mapped[str] = mapped_column(Text)
    device_credential_version: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'authorized'"))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    tts_budget: Mapped[int] = mapped_column(Integer, server_default=text("3000"))
    limits: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    results_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    feedback: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    feedback_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class LLMConnection(Base):
    model_options: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    managed_by_platform: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __tablename__ = "llm_connections"
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'local_llama_cpp'"))
    token_parameter: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'max_tokens'"))
    stream_usage: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    instruction_role: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'system'"))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    encrypted_credentials: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    credential_key_id: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    model_definition_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class ModelDefinition(Base):
    __tablename__ = "model_definitions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_key: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    publisher: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_family: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    categories: Mapped[list] = mapped_column(JSONB, nullable=False)
    operations: Mapped[list] = mapped_column(JSONB, nullable=False)
    capabilities: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    adapter_status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'unavailable'"))
    lifecycle: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class RuntimeModel(Base):
    """Executable model: provider configuration and credentials belong to this record."""

    __tablename__ = "runtime_models"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)
    engine: Mapped[str] = mapped_column(Text)
    model_key: Mapped[str] = mapped_column(Text)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    defaults: Mapped[dict] = mapped_column(JSONB, default=dict)
    legacy: Mapped[dict] = mapped_column(JSONB, default=dict)
    encrypted_credentials: Mapped[bytes | None] = mapped_column(LargeBinary)
    credential_key_id: Mapped[str | None] = mapped_column(Text)
    credential_owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    credential_owner_org: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def model(self):
        return self.model_key

    @property
    def base_url(self):
        return self.settings.get("base_url", "http://127.0.0.1:8787")

    @property
    def max_tokens(self):
        return self.settings.get("max_tokens", 256 if self.location == "local" else 1024)

    @property
    def system_prompt(self):
        return self.settings.get(
            "system_prompt",
            "You are a concise, helpful assistant. Reply in the user's language. If unsure, say so.",
        )

    @property
    def model_options(self):
        return self.settings.get("model_options", {"model_family": "generic", "context_tokens": 8192})

    @property
    def token_parameter(self):
        return self.settings.get(
            "token_parameter",
            "max_completion_tokens" if self.provider in {"openai", "azure_openai"} else "max_tokens",
        )

    @property
    def stream_usage(self):
        return self.settings.get("stream_usage", self.provider != "anthropic")

    @property
    def instruction_role(self):
        return self.settings.get("instruction_role", "system")

    @property
    def configuration_version(self):
        return self.revision

    @property
    def connection_type(self):
        return self.settings.get("connection_type")

    @property
    def auth_mode(self):
        return self.settings.get("auth_mode", "api_key")

    @property
    def validation_results(self):
        return self.legacy.get("validation_results", {})


class DeviceModelSelection(Base):
    __tablename__ = "device_model_selections"
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    mode: Mapped[str] = mapped_column(Text)
    llm_model_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    asr_model_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tts_model_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    video_model_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    execution_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class MediaModelConfig(Base):
    """Read-only compatibility view over canonical runtime models."""

    __tablename__ = "media_model_configs"
    __table_args__ = {"info": {"compatibility_view": True}}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    engine: Mapped[str] = mapped_column(Text)
    operation: Mapped[str] = mapped_column(Text)
    defaults: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class PlatformModelConnection(Base):
    """Read-only compatibility view for historical catalog metadata readers."""

    __tablename__ = "platform_model_connections"
    __table_args__ = {"info": {"compatibility_view": True}}
    model_definition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_credentials: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    credential_key_id: Mapped[str] = mapped_column(Text, nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=1024)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tested_revision: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    @property
    def id(self) -> uuid.UUID:
        """Use the catalog ID as this configuration's vault identity."""
        return self.model_definition_id

    @property
    def organization_id(self) -> uuid.UUID:
        """Vault AAD isolates the platform catalog from every tenant namespace."""
        return uuid.UUID(int=0)


class LocalConversationTurn(Base):
    """Optional client-reported text archive; never an inference request."""

    __tablename__ = "local_conversation_turns"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    turn_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    sequence: Mapped[int] = mapped_column(Integer)
    profile_revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    fingerprint: Mapped[str] = mapped_column(Text)
    input_text: Mapped[str] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text)
    document: Mapped[dict] = mapped_column(JSONB)
    byte_size: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LocalTurn(Base):
    """One turn a laptop executed on its own model: counts and routing outcome, never text."""

    __tablename__ = "local_turns"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    turn_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    profile_revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(Text, nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    connection_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    practice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    practice_revision: Mapped[int | None] = mapped_column(Integer)
    practice_snapshot_hash: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    answer_source: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str | None] = mapped_column(Text)
    context_ref: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    request_fingerprint: Mapped[str | None] = mapped_column(Text)
    routing_status: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str | None] = mapped_column(Text)
    topics: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    provider_calls: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    finish_reason: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    first_token_ms: Mapped[int | None] = mapped_column(Integer)
    total_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LLMRequest(Base):
    profile_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    configuration_hash: Mapped[str | None] = mapped_column(Text)
    __tablename__ = "llm_requests"
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    conversation_sequence: Mapped[int | None] = mapped_column(Integer)
    conversation_input: Mapped[str | None] = mapped_column(Text)
    practice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    practice_revision: Mapped[int | None] = mapped_column(Integer)
    practice_snapshot_hash: Mapped[str | None] = mapped_column(Text)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    device_credential_version: Mapped[int | None] = mapped_column(Integer)
    connection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    connection_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    target_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reserved_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    charged_total_tokens: Mapped[int | None] = mapped_column(Integer)
    lease_token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    error_code: Mapped[str | None] = mapped_column(Text)


class MemberImport(Base):
    __tablename__ = "member_imports"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    auth_method: Mapped[str] = mapped_column(Text, nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="validated")
    rows: Mapped[list] = mapped_column(JSONB, nullable=False)
    passwords_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    passwords_key_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    validated_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InvitationEmailOutbox(Base):
    __tablename__ = "invitation_email_outbox"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    membership_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_id: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SessionArchive(Base):
    __tablename__ = "session_archives"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    learner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    assigned_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    scenario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    scenario_title: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text)
    execution: Mapped[str] = mapped_column(Text)
    practice_snapshot: Mapped[dict] = mapped_column(JSONB)
    context: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    media_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    upload_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    manifest: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionArchiveItem(Base):
    __tablename__ = "session_archive_items"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(BigInteger)
    document: Mapped[dict] = mapped_column("metadata", JSONB)
    received: Mapped[list] = mapped_column(JSONB)
    purged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
