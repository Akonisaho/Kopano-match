"""Ten tables across three schemas: core, sensitive, audit.

JSONB only where the shape varies. Anything a filter or hard rule touches is a typed column.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

PK = dict(primary_key=True, server_default=text("gen_random_uuid()"))
NOW = dict(server_default=func.now())


def fk(target: str):
    # RESTRICT everywhere audit integrity depends on it
    return ForeignKey(target, ondelete="RESTRICT")


def score_check(col: str) -> CheckConstraint:
    return CheckConstraint(f"{col} BETWEEN 0 AND 100", name=f"ck_{col}_0_100")


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "core"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(20))  # sme, corporate, funder, admin
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(fk("core.organisations.id"))
    consent_version: Mapped[str | None] = mapped_column(String(40))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Organisation(Base):
    __tablename__ = "organisations"
    __table_args__ = {"schema": "core"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    name: Mapped[str] = mapped_column(String(200))
    org_type: Mapped[str] = mapped_column(String(20))  # sme, corporate, funder
    registration_number: Mapped[str | None] = mapped_column(String(40), unique=True)
    verification_status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class SmeProfile(Base):
    __tablename__ = "sme_profiles"
    __table_args__ = (
        Index("ix_sme_profiles_org", "organisation_id", unique=True),
        {"schema": "core"},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    organisation_id: Mapped[uuid.UUID] = mapped_column(fk("core.organisations.id"))
    sector: Mapped[str] = mapped_column(String(40))
    province: Mapped[str] = mapped_column(String(40))
    annual_turnover: Mapped[float] = mapped_column(Numeric(14, 2))
    years_trading: Mapped[int] = mapped_column(Integer)
    largest_past_contract: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    capability_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    ownership: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    visible_to_corporates: Mapped[bool] = mapped_column(Boolean, default=True)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_org_type", "organisation_id", "document_type"),
        Index("ix_documents_hash", "hash_value"),
        {"schema": "sensitive"},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    organisation_id: Mapped[uuid.UUID] = mapped_column(fk("core.organisations.id"))
    document_type: Mapped[str] = mapped_column(String(20))  # catalogue code, e.g. TCS
    issuer: Mapped[str | None] = mapped_column(String(120))
    file_url: Mapped[str] = mapped_column(String(500))  # path on disk, never the bytes
    mime_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    hash_value: Mapped[str] = mapped_column(String(64))  # SHA-256
    expiry_date: Mapped[date | None] = mapped_column(Date)
    retention_until: Mapped[date | None] = mapped_column(Date)
    review_status: Mapped[str | None] = mapped_column(String(20))  # approved, rejected
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class Verification(Base):
    __tablename__ = "verifications"
    __table_args__ = (
        Index("ix_verifications_subject", "subject_type", "subject_id"),
        {"schema": "sensitive"},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    subject_type: Mapped[str] = mapped_column(String(20))  # identity, document, organisation
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    provider: Mapped[str] = mapped_column(String(40))
    result: Mapped[str] = mapped_column(String(30))  # verified, not_found, non_compliant, ...
    confidence: Mapped[float] = mapped_column(Numeric(4, 3))
    source_label: Mapped[str] = mapped_column(String(80))  # e.g. "mock adapter (CIPC)"
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str | None] = mapped_column(String(20))  # approved, rejected
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(fk("core.users.id"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    retention_until: Mapped[date | None] = mapped_column(Date)


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = {"schema": "core"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    organisation_id: Mapped[uuid.UUID] = mapped_column(fk("core.organisations.id"))
    kind: Mapped[str] = mapped_column(String(20), default="procurement")
    title: Mapped[str] = mapped_column(String(200))
    sector: Mapped[str] = mapped_column(String(40))
    province: Mapped[str] = mapped_column(String(40))
    contract_value: Mapped[float] = mapped_column(Numeric(14, 2))
    duration_months: Mapped[int] = mapped_column(Integer)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    scope_items: Mapped[list] = mapped_column(JSONB, default=list)
    transformation_gap: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    description: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), **NOW, onupdate=func.now()
    )


class OpportunityRequirement(Base):
    __tablename__ = "opportunity_requirements"
    __table_args__ = (
        Index("ix_requirements_opportunity", "opportunity_id"),
        CheckConstraint("weight BETWEEN 0 AND 20", name="ck_weight_0_20"),
        {"schema": "core"},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(fk("core.opportunities.id"))
    requirement_type: Mapped[str] = mapped_column(String(20))  # RequirementType value
    requirement_value: Mapped[dict] = mapped_column(JSONB)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    weight: Mapped[int] = mapped_column(Integer, default=5)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("sme_id", "opportunity_id", "model_version", name="uq_match_pair"),
        Index("ix_matches_ranked", "opportunity_id", text("overall_score DESC")),
        score_check("fit_score"),
        score_check("readiness_score"),
        score_check("overall_score"),
        {"schema": "core"},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    sme_id: Mapped[uuid.UUID] = mapped_column(fk("core.organisations.id"))
    opportunity_id: Mapped[uuid.UUID] = mapped_column(fk("core.opportunities.id"))
    gate: Mapped[str] = mapped_column(String(12))
    quadrant: Mapped[str] = mapped_column(String(20))
    fit_score: Mapped[float] = mapped_column(Numeric(5, 1))
    readiness_score: Mapped[float] = mapped_column(Numeric(5, 1))
    overall_score: Mapped[float] = mapped_column(Numeric(5, 1))  # sorting only
    explanation: Mapped[dict] = mapped_column(JSONB)  # components, gaps, rationale
    risk_flags: Mapped[dict] = mapped_column(JSONB)
    model_version: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="matched")  # shortlisted, rejected
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("match_id", name="uq_application_match"), {"schema": "core"})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    match_id: Mapped[uuid.UUID] = mapped_column(fk("core.matches.id"))
    status: Mapped[str] = mapped_column(String(20), default="submitted")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id", text("timestamp DESC")),
        {"schema": "audit"},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    # No foreign key on purpose: the trail must outlive anything it describes.
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    old_value: Mapped[dict | None] = mapped_column(JSONB)
    new_value: Mapped[dict | None] = mapped_column(JSONB)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
