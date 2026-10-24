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
    # Two-step sign-in. The secret is encrypted at rest; recovery codes are stored hashed.
    totp_secret_enc: Mapped[str | None] = mapped_column(String(400))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)
    recovery_hashes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'")
    )
    # A preference, never an input to a score
    language: Mapped[str] = mapped_column(String(5), default="en", server_default="en")
    # The support programme that helped this business sign up, if one did
    assisted_by: Mapped[uuid.UUID | None] = mapped_column(fk("core.organisations.id"))


class Organisation(Base):
    __tablename__ = "organisations"
    __table_args__ = {"schema": "core"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    name: Mapped[str] = mapped_column(String(200))
    org_type: Mapped[str] = mapped_column(String(20))  # sme, corporate, funder
    registration_number: Mapped[str | None] = mapped_column(String(40), unique=True)
    verification_status: Mapped[str] = mapped_column(String(20), default="pending")
    # clear, monitoring, flagged, under_review, restricted, suspended, blacklisted, reinstated.
    # Suspended and blacklisted are a hard gate: no matching, no applying, no posting.
    enforcement_status: Mapped[str] = mapped_column(
        String(14), default="clear", server_default="clear"
    )
    restrictions: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class EnforcementCase(Base):
    """An investigation into one organisation. Evidence and a human decision sit behind every step."""

    __tablename__ = "enforcement_cases"
    __table_args__ = (Index("ix_enforcement_org", "organisation_id"), {"schema": "core"})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    organisation_id: Mapped[uuid.UUID] = mapped_column(fk("core.organisations.id"))
    reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    severity: Mapped[str] = mapped_column(String(10), default="medium")  # low, medium, high, critical
    notes: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSONB, default=list)  # [{"kind", "note"}]
    status: Mapped[str] = mapped_column(String(14), default="open")  # open, recommended, closed, blacklisted
    emergency: Mapped[bool] = mapped_column(Boolean, default=False)
    emergency_reason: Mapped[str | None] = mapped_column(Text)
    emergency_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_by: Mapped[uuid.UUID] = mapped_column(fk("core.users.id"))
    recommended_by: Mapped[uuid.UUID | None] = mapped_column(fk("core.users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(fk("core.users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW, onupdate=func.now())


class EnforcementAction(Base):
    """Every step taken on a case, kept as history. Nothing here is edited or removed."""

    __tablename__ = "enforcement_actions"
    __table_args__ = (Index("ix_enforcement_action_case", "case_id"), {"schema": "core"})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    case_id: Mapped[uuid.UUID] = mapped_column(fk("core.enforcement_cases.id"))
    organisation_id: Mapped[uuid.UUID] = mapped_column(fk("core.organisations.id"))
    action: Mapped[str] = mapped_column(String(24))
    previous_status: Mapped[str] = mapped_column(String(14))
    new_status: Mapped[str] = mapped_column(String(14))
    note: Mapped[str | None] = mapped_column(Text)
    by_user: Mapped[uuid.UUID] = mapped_column(fk("core.users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class EnforcementAppeal(Base):
    __tablename__ = "enforcement_appeals"
    __table_args__ = (Index("ix_enforcement_appeal_org", "organisation_id"), {"schema": "core"})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    case_id: Mapped[uuid.UUID | None] = mapped_column(fk("core.enforcement_cases.id"))
    organisation_id: Mapped[uuid.UUID] = mapped_column(fk("core.organisations.id"))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="submitted")  # submitted, more_info, approved, rejected
    decided_by: Mapped[uuid.UUID | None] = mapped_column(fk("core.users.id"))
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    awarded_value: Mapped[float | None] = mapped_column(Numeric(14, 2))
    awarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # How ready the SME was at the moment of award. This is what lets us prove how much went to
    # businesses a strict 'must hold every document' filter would have rejected.
    gate_at_award: Mapped[str | None] = mapped_column(String(12))
    quadrant_at_award: Mapped[str | None] = mapped_column(String(20))


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


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user", "user_id", text("created_at DESC")),
        {"schema": "core"},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    user_id: Mapped[uuid.UUID] = mapped_column(fk("core.users.id"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PasswordReset(Base):
    """Single-use reset links. Only a hash of the token is stored."""

    __tablename__ = "password_resets"
    __table_args__ = {"schema": "sensitive"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    user_id: Mapped[uuid.UUID] = mapped_column(fk("core.users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class Consortium(Base):
    """A proposed group of SMEs for one opportunity, and whether they have all said yes."""

    __tablename__ = "consortia"
    __table_args__ = (Index("ix_consortia_opportunity", "opportunity_id"), {"schema": "core"})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(fk("core.opportunities.id"))
    proposed_by: Mapped[uuid.UUID] = mapped_column(fk("core.users.id"))
    lead_sme_id: Mapped[uuid.UUID] = mapped_column(fk("core.organisations.id"))
    status: Mapped[str] = mapped_column(
        String(12), default="proposed"
    )  # proposed, formed, declined
    coverage_pct: Mapped[float] = mapped_column(Numeric(5, 1))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConsortiumMember(Base):
    __tablename__ = "consortium_members"
    __table_args__ = (
        UniqueConstraint("consortium_id", "sme_id", name="uq_consortium_member"),
        {"schema": "core"},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    consortium_id: Mapped[uuid.UUID] = mapped_column(fk("core.consortia.id"))
    sme_id: Mapped[uuid.UUID] = mapped_column(fk("core.organisations.id"))
    role: Mapped[str] = mapped_column(String(10), default="member")  # lead, member
    scope_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    response: Mapped[str] = mapped_column(
        String(10), default="pending"
    )  # pending, accepted, declined
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Feedback(Base):
    """A buyer's structured rating of an SME after an award. The SME can respond or dispute."""

    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint("application_id", name="uq_feedback_application"),
        Index("ix_feedback_sme", "sme_id"),
        {"schema": "core"},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    # Set for a review of awarded work. A programme or engagement review has none; it is tied to a
    # confirmed relationship instead (see `basis`).
    application_id: Mapped[uuid.UUID | None] = mapped_column(fk("core.applications.id"))
    sme_id: Mapped[uuid.UUID] = mapped_column(fk("core.organisations.id"))
    provider_org_id: Mapped[uuid.UUID] = mapped_column(fk("core.organisations.id"))
    author_id: Mapped[uuid.UUID] = mapped_column(fk("core.users.id"))
    ratings: Mapped[dict] = mapped_column(JSONB)  # criterion -> 1..5, or {"overall": 1..5}
    # What the review is about, shown under the review: procurement, training, incubation, ...
    kind: Mapped[str] = mapped_column(String(24), default="procurement", server_default="procurement")
    programme: Mapped[str | None] = mapped_column(String(200))
    # Attendance, duration and completion for programmes. Never a certification claim.
    context: Mapped[dict | None] = mapped_column(JSONB)
    # Why the reviewer is allowed to review: award, application or assisted
    basis: Mapped[str] = mapped_column(String(12), default="award", server_default="award")
    comment: Mapped[str | None] = mapped_column(Text)
    # published, responded, disputed, upheld (dispute lost), removed (dispute won)
    status: Mapped[str] = mapped_column(String(12), default="published")
    sme_response: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispute_reason: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(fk("core.users.id"))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class AiInsight(Base):
    """A cached AI-written note (semantic relevance, feedback summary). Advisory only."""

    __tablename__ = "ai_insights"
    __table_args__ = (
        UniqueConstraint("kind", "subject_id", name="uq_insight_subject"),
        {"schema": "core"},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    kind: Mapped[str] = mapped_column(String(20))  # semantic, feedback_summary
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    input_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)


class ApiKey(Base):
    """A key a buyer's own system uses to post opportunities. Only a hash is stored."""

    __tablename__ = "api_keys"
    __table_args__ = {"schema": "core"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    organisation_id: Mapped[uuid.UUID] = mapped_column(fk("core.organisations.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(fk("core.users.id"))
    name: Mapped[str] = mapped_column(String(60))
    prefix: Mapped[str] = mapped_column(String(12))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Passport(Base):
    """A business's shareable Readiness Passport link. The business can rotate or switch it off."""

    __tablename__ = "passports"
    __table_args__ = (
        UniqueConstraint("organisation_id", name="uq_passport_org"),
        {"schema": "core"},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **PK)
    organisation_id: Mapped[uuid.UUID] = mapped_column(fk("core.organisations.id"))
    token: Mapped[str] = mapped_column(String(64), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), **NOW)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
