"""Deterministic seed: 40 SMEs, 6 opportunities, planted demo cases.

Pure dataclasses, shared by seed.py (database) and scripts/check_engine.py (terminal).
Planted SMEs are sme-001 .. sme-013; everything after is seeded-random filler.
"""

import random

from .engine.taxonomy import CAPABILITIES, PROVINCES
from .engine.types import (
    SME,
    DocStatus,
    Opportunity,
    Requirement,
    RequirementType as R,
    ScopeItem,
)

V, E, X = DocStatus.VALID, DocStatus.EXPIRED, DocStatus.MISSING

PLANTED = {
    "coachable": "sme-001",  # high fit, two missing compliance documents
    "expired_only": "sme-002",  # expired B-BBEE affidavit only
    "overtrading": "sme-003",  # high fit, turnover a third of the contract
    "ready": ["sme-004", "sme-005", "sme-006"],  # award-now
    "consortium": ["sme-007", "sme-008", "sme-009"],  # together cover the agri-hub
    "registry_not_found": "sme-010",
    "tax_non_compliant": "sme-011",
    "duplicate_hash": ["sme-012", "sme-013"],
}

M = 1_000_000


def _opportunities() -> list[Opportunity]:
    def comp(doc: str, mandatory: bool = True) -> Requirement:
        return Requirement(R.COMPLIANCE_DOC, {"doc": doc}, mandatory, 10)

    return [
        Opportunity(
            id="opp-1",
            title="Provincial roads rehabilitation",
            sector="construction",
            province="Gauteng",
            contract_value=4.2 * M,
            duration_months=12,
            payment_terms_days=30,
            scope_items=[
                ScopeItem("CON-ROADS", 2.5 * M),
                ScopeItem("CON-CIVIL", 1.2 * M),
                ScopeItem("CON-ELEC", 0.5 * M),
            ],
            requirements=[
                Requirement(R.CAPABILITY, {"code": "CON-ROADS"}, True, 10),
                Requirement(R.MIN_YEARS_TRADING, {"years": 3}, True, 5),
                Requirement(R.PROVINCE, {"province": "Gauteng"}, False, 5),
                comp("TCS"),
                comp("BBBEE"),
                comp("COID"),
                Requirement(R.CERTIFICATION, {"doc": "CIDB"}, True, 10),
            ],
            transformation_gap=["youth", "black_women"],
        ),
        Opportunity(
            id="opp-2",
            title="Municipal ICT support contract",
            sector="ict",
            province="Gauteng",
            contract_value=1.8 * M,
            duration_months=24,
            payment_terms_days=30,
            scope_items=[ScopeItem("ICT-SUP", 1.0 * M), ScopeItem("ICT-NET", 0.8 * M)],
            requirements=[comp("TCS"), comp("COID"), comp("CSD")],
            transformation_gap=["youth"],
        ),
        Opportunity(
            id="opp-3",
            title="School cleaning and security",
            sector="services",
            province="KwaZulu-Natal",
            contract_value=3.0 * M,
            duration_months=12,
            payment_terms_days=45,
            scope_items=[ScopeItem("SVC-CLEAN", 1.8 * M), ScopeItem("SVC-SEC", 1.2 * M)],
            requirements=[comp("TCS"), comp("BBBEE"), comp("COID")],
            transformation_gap=["black"],
        ),
        Opportunity(
            id="opp-4",
            title="Integrated agri-hub build",
            sector="agriculture",
            province="Limpopo",
            contract_value=6.5 * M,
            duration_months=18,
            payment_terms_days=30,
            scope_items=[
                ScopeItem("AGR-PROC", 2.0 * M),
                ScopeItem("AGR-LOG", 1.5 * M),
                ScopeItem("ICT-NET", 1.0 * M),
                ScopeItem("CON-BLDG", 2.0 * M),
            ],
            requirements=[comp("TCS"), comp("BBBEE")],
            transformation_gap=["black_women"],
        ),
        Opportunity(
            id="opp-5",
            title="Packaging supply framework",
            sector="manufacturing",
            province="Western Cape",
            contract_value=2.4 * M,
            duration_months=12,
            payment_terms_days=30,
            scope_items=[ScopeItem("MFG-PACK", 1.5 * M), ScopeItem("MFG-FAB", 0.9 * M)],
            requirements=[
                Requirement(R.MIN_YEARS_TRADING, {"years": 5}, False, 5),
                comp("TCS"),
                comp("CSD"),
                comp("BBBEE"),
            ],
            transformation_gap=["black_women", "youth"],
        ),
        Opportunity(
            id="opp-6",
            title="Cold-chain logistics pilot",
            sector="agriculture",
            province="Mpumalanga",
            contract_value=3.6 * M,
            duration_months=12,
            payment_terms_days=60,
            scope_items=[ScopeItem("AGR-LOG", 2.4 * M), ScopeItem("AGR-PROD", 1.2 * M)],
            requirements=[comp("TCS"), comp("CSD"), comp("COID")],
            transformation_gap=["youth"],
        ),
        Opportunity(
            id="opp-7",
            title="Youth enterprise growth grant",
            sector="services",
            province="Gauteng",
            contract_value=0.25 * M,
            duration_months=12,
            payment_terms_days=30,
            scope_items=[
                ScopeItem("ICT-DEV", 0.05 * M),
                ScopeItem("ICT-SUP", 0.05 * M),
                ScopeItem("SVC-CLEAN", 0.05 * M),
                ScopeItem("MFG-PACK", 0.05 * M),
                ScopeItem("AGR-PROC", 0.05 * M),
            ],
            requirements=[
                Requirement(R.OWNERSHIP, {"flag": "youth"}, True, 10),
                Requirement(R.MIN_YEARS_TRADING, {"years": 1}, True, 5),
                Requirement(R.COMPLIANCE_DOC, {"doc": "TCS"}, True, 10),
                Requirement(R.COMPLIANCE_DOC, {"doc": "CSD"}, True, 10),
            ],
            transformation_gap=["youth"],
        ),
        Opportunity(
            id="opp-8",
            title="Seed investment readiness cohort",
            sector="ict",
            province="Gauteng",
            contract_value=2.0 * M,
            duration_months=24,
            payment_terms_days=30,
            scope_items=[
                ScopeItem("ICT-DEV", 1.0 * M),
                ScopeItem("ICT-NET", 0.5 * M),
                ScopeItem("ICT-SUP", 0.5 * M),
            ],
            requirements=[
                Requirement(R.MIN_YEARS_TRADING, {"years": 2}, True, 5),
                Requirement(R.MIN_TURNOVER, {"amount": 1.0 * M}, True, 5),
                Requirement(R.COMPLIANCE_DOC, {"doc": "TCS"}, True, 10),
                Requirement(R.COMPLIANCE_DOC, {"doc": "BBBEE"}, False, 5),
            ],
            transformation_gap=["black_women"],
        ),
        Opportunity(
            id="opp-9",
            title="Supplier development accelerator",
            sector="services",
            province="Gauteng",
            contract_value=0.6 * M,
            duration_months=12,
            payment_terms_days=30,
            scope_items=[
                ScopeItem("SVC-CLEAN", 0.2 * M),
                ScopeItem("SVC-SEC", 0.2 * M),
                ScopeItem("SVC-CATER", 0.2 * M),
            ],
            requirements=[
                Requirement(R.MIN_YEARS_TRADING, {"years": 1}, True, 5),
                Requirement(R.COMPLIANCE_DOC, {"doc": "TCS"}, True, 10),
            ],
            transformation_gap=["black", "youth"],
        ),
    ]


# Who publishes each opportunity, what kind it is, and when it closes (days from today).
OPP_META = {
    "opp-1": (
        "corporate",
        "procurement",
        16,
        "Rehabilitation of 42 km of provincial road, including drainage and signage. "
        "Phased delivery with monthly payment certificates.",
    ),
    "opp-2": (
        "corporate",
        "procurement",
        9,
        "Two-year managed IT support and network maintenance for municipal offices.",
    ),
    "opp-3": (
        "corporate",
        "procurement",
        21,
        "Cleaning and security services for 12 schools, with local employment targets.",
    ),
    "opp-4": (
        "corporate",
        "procurement",
        30,
        "Design and build of an agro-processing hub, cold chain and connectivity. "
        "Too broad for one supplier: consortium bids are expected.",
    ),
    "opp-5": (
        "corporate",
        "procurement",
        13,
        "Framework agreement for packaging supply and light metal fabrication.",
    ),
    "opp-6": (
        "corporate",
        "procurement",
        25,
        "Pilot cold-chain logistics for fresh produce, with 60-day payment terms.",
    ),
    "opp-7": (
        "funder",
        "grant",
        18,
        "Grants of up to R250k for youth-owned businesses to fund working capital "
        "and equipment. Applicants must be tax compliant and registered on CSD.",
    ),
    "opp-8": (
        "support",
        "training",
        28,
        "A training cohort for technology SMEs preparing to scale: financial "
        "projections, tender writing and compliance workshops.",
    ),
    "opp-9": (
        "support",
        "support",
        12,
        "Twelve months of mentoring, market access and compliance coaching "
        "for operating service businesses.",
    ),
}


def _docs(tcs=V, bbbee=V, coid=V, csd=V, cidb=V) -> dict[str, DocStatus]:
    return {"TCS": tcs, "BBBEE": bbbee, "COID": coid, "CSD": csd, "CIDB": cidb}


def _planted() -> list[SME]:
    return [
        SME(
            "sme-001",
            "Thabo Civils",
            "construction",
            "Gauteng",
            6 * M,
            8,
            3 * M,
            ["CON-ROADS", "CON-CIVIL", "CON-ELEC"],
            ["black", "youth", "black_women"],
            _docs(coid=X, cidb=X),
        ),
        SME(
            "sme-002",
            "Nomsa Builders",
            "construction",
            "Gauteng",
            7 * M,
            9,
            3.5 * M,
            ["CON-ROADS", "CON-CIVIL"],
            ["black", "black_women"],
            _docs(bbbee=E),
        ),
        SME(
            "sme-003",
            "Sizwe Road Works",
            "construction",
            "Gauteng",
            1.4 * M,
            12,
            4.5 * M,
            ["CON-ROADS", "CON-CIVIL", "CON-ELEC"],
            ["black", "youth", "black_women"],
            _docs(coid=X, cidb=X),
        ),
        SME(
            "sme-004",
            "Masego Infrastructure",
            "construction",
            "Gauteng",
            12 * M,
            11,
            4 * M,
            ["CON-ROADS", "CON-CIVIL"],
            ["black", "black_women"],
            _docs(),
        ),
        SME(
            "sme-005",
            "Khaya Earthworks",
            "construction",
            "Gauteng",
            9 * M,
            10,
            3.8 * M,
            ["CON-ROADS", "CON-ELEC"],
            ["black", "youth"],
            _docs(),
        ),
        SME(
            "sme-006",
            "Lerato Civil & Electrical",
            "construction",
            "Mpumalanga",
            10 * M,
            9,
            4.2 * M,
            ["CON-ROADS", "CON-CIVIL", "CON-ELEC"],
            ["black", "black_women", "youth"],
            _docs(),
        ),
        SME(
            "sme-007",
            "AgriFresh Processors",
            "agriculture",
            "Limpopo",
            5 * M,
            7,
            2 * M,
            ["AGR-PROC", "AGR-LOG"],
            ["black", "black_women"],
            _docs(),
        ),
        SME(
            "sme-008",
            "LinkNet Solutions",
            "ict",
            "Gauteng",
            4 * M,
            6,
            1.5 * M,
            ["ICT-NET"],
            ["black", "youth"],
            _docs(coid=E),
        ),
        SME(
            "sme-009",
            "BuildRight Contractors",
            "construction",
            "Limpopo",
            6 * M,
            8,
            2.5 * M,
            ["CON-BLDG"],
            ["black"],
            _docs(),
        ),
        SME(
            "sme-010",
            "Vuyo Catering",
            "services",
            "Western Cape",
            2 * M,
            4,
            0.5 * M,
            ["SVC-CATER"],
            ["black", "youth"],
            _docs(),
        ),
        SME(
            "sme-011",
            "Palesa Cleaning",
            "services",
            "KwaZulu-Natal",
            2.5 * M,
            5,
            0.8 * M,
            ["SVC-CLEAN"],
            ["black_women"],
            _docs(tcs=E),
        ),
        SME(
            "sme-012",
            "Sipho Packaging",
            "manufacturing",
            "Western Cape",
            3 * M,
            6,
            1 * M,
            ["MFG-PACK"],
            ["black"],
            _docs(),
        ),
        SME(
            "sme-013",
            "Zanele Fabrication",
            "manufacturing",
            "Western Cape",
            3.2 * M,
            7,
            1.2 * M,
            ["MFG-FAB", "MFG-PACK"],
            ["black_women"],
            _docs(),
        ),
        # Low fit on opp-1 so the quadrant chart has dots below the fit line
        SME(
            "sme-014",
            "Tumelo Roadworks",
            "construction",
            "Western Cape",
            1.6 * M,
            3,
            0.2 * M,
            ["CON-ROADS"],
            [],
            _docs(),
        ),
        SME(
            "sme-015",
            "Emerging Surfacing",
            "construction",
            "Eastern Cape",
            1.0 * M,
            3,
            0.1 * M,
            ["CON-ROADS"],
            [],
            _docs(bbbee=X, coid=X, csd=X, cidb=X),
        ),
    ]


def _filler(count: int, start: int) -> list[SME]:
    rng = random.Random(42)
    sectors = sorted({s for s, _ in CAPABILITIES.values()})
    smes = []
    seen: set[str] = set()
    for i in range(start, start + count):
        sector = rng.choice(sectors)
        codes_in_sector = [c for c, (s, _) in CAPABILITIES.items() if s == sector]
        codes = rng.sample(codes_in_sector, k=min(len(codes_in_sector), rng.randint(1, 2)))
        turnover = round(10 ** rng.uniform(5.7, 7.3))
        status = lambda: rng.choices([V, E, X], weights=[60, 15, 25])[0]  # noqa: E731
        name = f"{rng.choice(NAMES_A)} {rng.choice(NAMES_B)}"
        if name in seen:
            name = f"{name} {i}"
        seen.add(name)
        smes.append(
            SME(
                f"sme-{i:03d}",
                name,
                sector,
                rng.choice(PROVINCES),
                turnover,
                rng.randint(1, 15),
                round(turnover * rng.uniform(0.2, 0.8)),
                codes,
                [f for f in ("black", "youth", "black_women") if rng.random() < 0.5],
                _docs(status(), status(), status(), status(), status()),
            )
        )
    return smes


NAMES_A = [
    "Ubuntu",
    "Karoo",
    "Highveld",
    "Lowveld",
    "Tshwane",
    "Madiba",
    "Baobab",
    "Protea",
    "Impala",
    "Kopano",
    "Siyakha",
    "Thuso",
    "Mosaic",
    "Ikhaya",
    "Dikgang",
]
NAMES_B = [
    "Projects",
    "Services",
    "Holdings",
    "Enterprises",
    "Trading",
    "Solutions",
    "Contractors",
    "Logistics",
    "Works",
    "Group",
]


def build_seed() -> tuple[list[SME], list[Opportunity], dict[str, dict]]:
    smes = _planted()
    smes += _filler(40 - len(smes), start=len(smes) + 1)
    meta: dict[str, dict] = {}
    for n, s in enumerate(smes, start=1):
        meta[s.id] = {
            "registration_number": f"2018/{100000 + n}/06",
            "tax_status": "compliant",
            "document_hash": f"hash-{s.id}",
        }
    # Planted verification cases. Mock registry: reg numbers ending in 7 are not found.
    meta[PLANTED["registry_not_found"]]["registration_number"] = "2018/100010/07"
    meta[PLANTED["tax_non_compliant"]]["tax_status"] = "non_compliant"
    a, b = PLANTED["duplicate_hash"]
    meta[b]["document_hash"] = meta[a]["document_hash"]
    return smes, _opportunities(), meta
