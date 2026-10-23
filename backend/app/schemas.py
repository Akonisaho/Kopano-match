"""Request bodies. Every route takes one of these, so nothing unvalidated reaches the database."""

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .engine.taxonomy import CAPABILITIES, COMPLIANCE_CATALOGUE, PROVINCES, SECTORS
from .engine.types import READINESS_TYPES, RequirementType


def _fits_bcrypt(value: str) -> str:
    """bcrypt reads at most 72 bytes. Refuse longer passwords with a clear message, not a crash."""
    if len(value.encode()) > 72:
        raise ValueError("Passwords can be at most 72 characters")
    return value


OWNERSHIP_FLAGS = ("youth", "black", "black_women")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RegisterIn(Strict):
    email: EmailStr
    password: str = Field(min_length=12, max_length=72)
    full_name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    role: Literal[
        "sme", "corporate", "funder", "support"
    ]  # admin is provisioned, never self-served
    organisation_name: str = Field(min_length=2, max_length=200)
    registration_number: str | None = Field(default=None, max_length=40)
    consent: bool

    _password_limit = field_validator("password")(_fits_bcrypt)

    @field_validator("consent")
    @classmethod
    def must_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent to the privacy notice is required to register")
        return v


class ProfileIn(Strict):
    sector: Literal[tuple(SECTORS)]  # type: ignore[valid-type]
    province: Literal[tuple(PROVINCES)]  # type: ignore[valid-type]
    annual_turnover: float = Field(gt=0, le=1e10)
    years_trading: int = Field(ge=0, le=100)
    largest_past_contract: float = Field(ge=0, le=1e10, default=0)
    capability_codes: list[str] = Field(max_length=15)
    ownership: list[str] = Field(default_factory=list, max_length=3)
    visible_to_corporates: bool = True

    @field_validator("capability_codes")
    @classmethod
    def known_codes(cls, v: list[str]) -> list[str]:
        bad = [c for c in v if c not in CAPABILITIES]
        if bad:
            raise ValueError(f"Unknown capability codes: {bad}")
        return sorted(set(v))

    @field_validator("ownership")
    @classmethod
    def known_flags(cls, v: list[str]) -> list[str]:
        if any(f not in OWNERSHIP_FLAGS for f in v):
            raise ValueError("Unknown ownership flag")
        return sorted(set(v))


class ScopeItemIn(Strict):
    code: str
    value: float = Field(gt=0, le=1e10)

    @field_validator("code")
    @classmethod
    def known(cls, v: str) -> str:
        if v not in CAPABILITIES:
            raise ValueError("Unknown capability code")
        return v


class RequirementIn(Strict):
    requirement_type: RequirementType
    requirement_value: dict
    mandatory: bool = True
    weight: int = Field(default=5, ge=0, le=20)

    @model_validator(mode="after")
    def value_shape(self):
        t, v = self.requirement_type, self.requirement_value
        checks = {
            RequirementType.SECTOR: ("sector", lambda x: x in SECTORS),
            RequirementType.PROVINCE: ("province", lambda x: x in PROVINCES),
            RequirementType.MIN_YEARS_TRADING: (
                "years",
                lambda x: isinstance(x, int) and 0 <= x <= 100,
            ),
            RequirementType.MIN_TURNOVER: (
                "amount",
                lambda x: isinstance(x, (int, float)) and 0 <= x <= 1e10,
            ),
            RequirementType.OWNERSHIP: ("flag", lambda x: x in OWNERSHIP_FLAGS),
            RequirementType.CAPABILITY: ("code", lambda x: x in CAPABILITIES),
            RequirementType.COMPLIANCE_DOC: ("doc", lambda x: x in COMPLIANCE_CATALOGUE),
            RequirementType.CERTIFICATION: ("doc", lambda x: x in COMPLIANCE_CATALOGUE),
        }
        key, ok = checks[t]
        if set(v) != {key} or not ok(v[key]):
            raise ValueError(f"{t.value} requires exactly {{'{key}': <valid value>}}")
        return self


class OpportunityIn(Strict):
    kind: Literal["procurement", "grant", "funding", "training", "support"] = "procurement"
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    deadline: date | None = None
    sector: Literal[tuple(SECTORS)]  # type: ignore[valid-type]
    province: Literal[tuple(PROVINCES)]  # type: ignore[valid-type]
    contract_value: float = Field(gt=0, le=1e10)
    duration_months: int = Field(ge=1, le=120)
    payment_terms_days: int = Field(default=30, ge=0, le=180)
    scope_items: list[ScopeItemIn] = Field(min_length=1, max_length=20)
    transformation_gap: list[str] = Field(default_factory=list, max_length=3)
    requirements: list[RequirementIn] = Field(max_length=30)

    @field_validator("transformation_gap")
    @classmethod
    def known_flags(cls, v: list[str]) -> list[str]:
        if any(f not in OWNERSHIP_FLAGS for f in v):
            raise ValueError("Unknown transformation flag")
        return v


class ReviewIn(Strict):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=500)


class SimulateIn(Strict):
    credentials: list[str] = Field(min_length=1, max_length=6)

    @field_validator("credentials")
    @classmethod
    def known(cls, v: list[str]) -> list[str]:
        bad = [c for c in v if c not in COMPLIANCE_CATALOGUE]
        if bad:
            raise ValueError(f"Unknown credentials: {bad}")
        return sorted(set(v))


class ExtractIn(Strict):
    text: str = Field(min_length=20, max_length=20000)


__all__ = ["READINESS_TYPES"]


class ForgotIn(Strict):
    email: EmailStr


class ResetIn(Strict):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=12, max_length=72)
    _password_limit = field_validator("new_password")(_fits_bcrypt)


class MfaCodeIn(Strict):
    code: str = Field(min_length=6, max_length=20)


class MfaVerifyIn(Strict):
    mfa_token: str = Field(min_length=20, max_length=1000)
    code: str = Field(min_length=6, max_length=20)


class AwardIn(Strict):
    value: float = Field(gt=0, le=1e10)


class RespondIn(Strict):
    accept: bool


_PERSONAL = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.]+|\b\d{13}\b|(?:\+?27|0)[\s-]?\d{2}[\s-]?\d{3}[\s-]?\d{4}"
)


def _no_personal_details(v: str | None) -> str | None:
    """Feedback is about the work. Keep emails, phone numbers and ID numbers out of it (POPIA)."""
    if v and _PERSONAL.search(v):
        raise ValueError("Leave out email addresses, phone numbers and ID numbers")
    return v


class FeedbackIn(Strict):
    ratings: dict[str, int]
    comment: str | None = Field(default=None, max_length=1000)

    _clean = field_validator("comment")(_no_personal_details)

    @field_validator("ratings")
    @classmethod
    def complete(cls, v: dict[str, int]) -> dict[str, int]:
        keys = {
            "quality",
            "delivery",
            "responsiveness",
            "compliance",
            "innovation",
            "value_for_money",
        }
        if set(v) != keys:
            raise ValueError("Rate all six criteria")
        if any(not 1 <= x <= 5 for x in v.values()):
            raise ValueError("Each rating is from 1 to 5")
        return v


class FeedbackResponseIn(Strict):
    text: str = Field(min_length=3, max_length=1000)
    _clean = field_validator("text")(_no_personal_details)


class FeedbackResolveIn(Strict):
    decision: Literal["uphold", "remove"]
    note: str = Field(min_length=3, max_length=500)


class SearchIn(Strict):
    query: str = Field(min_length=3, max_length=500)
