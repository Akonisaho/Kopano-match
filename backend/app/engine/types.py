"""Plain dataclasses for the engine. No database, no framework imports."""

from dataclasses import dataclass, field
from enum import Enum

MODEL_VERSION = "v1"


class RequirementType(str, Enum):
    SECTOR = "sector"  # fit axis
    PROVINCE = "province"  # fit axis, can be a hard gate
    MIN_YEARS_TRADING = "min_years"  # fit axis
    MIN_TURNOVER = "min_turnover"  # fit axis
    OWNERSHIP = "ownership"  # fit axis, usually a hard gate
    CAPABILITY = "capability"  # fit axis, taxonomy code
    COMPLIANCE_DOC = "compliance_doc"  # readiness axis
    CERTIFICATION = "certification"  # readiness axis


READINESS_TYPES = {RequirementType.COMPLIANCE_DOC, RequirementType.CERTIFICATION}


class Gate(str, Enum):
    PASS = "pass"
    REMEDIABLE = "remediable"
    FAIL = "fail"


class DocStatus(str, Enum):
    VALID = "valid"
    EXPIRED = "expired"
    MISSING = "missing"


@dataclass(frozen=True)
class Requirement:
    type: RequirementType
    value: dict
    mandatory: bool = True
    weight: int = 5


@dataclass(frozen=True)
class ScopeItem:
    code: str
    value: float  # rand value of this line item


@dataclass
class Opportunity:
    id: str
    title: str
    sector: str
    province: str
    contract_value: float
    duration_months: int
    payment_terms_days: int
    scope_items: list[ScopeItem]
    requirements: list[Requirement]
    transformation_gap: list[str] = field(default_factory=list)  # youth, black, black_women
    status: str = "open"


@dataclass
class SME:
    id: str
    name: str
    sector: str
    province: str
    turnover: float
    years_trading: int
    largest_past_contract: float
    capability_codes: list[str]
    ownership: list[str] = field(default_factory=list)  # youth, black, black_women
    documents: dict[str, DocStatus] = field(default_factory=dict)  # credential code -> status


@dataclass
class Gap:
    credential: str
    label: str
    status: DocStatus
    mandatory: bool
    issuer: str
    days: int
    cost_zar: int
    also_unlocks: int = 0


@dataclass
class RiskFlags:
    overtrading: bool
    overtrading_pct: float
    working_capital_zar: float
    concentration: bool
    concentration_pct: float


@dataclass
class MatchResult:
    sme_id: str
    opportunity_id: str
    gate: Gate
    fit: float
    readiness: float
    overall: float
    quadrant: str
    components: dict[str, float]
    gaps: list[Gap]
    risk: RiskFlags
    fail_reasons: list[str] = field(default_factory=list)
    model_version: str = MODEL_VERSION


@dataclass
class Consortium:
    opportunity_id: str
    lead_sme_id: str
    member_sme_ids: list[str]
    coverage_pct: float
    uncovered_codes: list[str]
