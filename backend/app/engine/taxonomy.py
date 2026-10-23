"""Capability codes and the compliance catalogue.

Catalogue turnarounds and costs are INDICATIVE. Verify each against the issuer, and the
current B-BBEE EME/QSE turnover thresholds, before presenting.
"""

from dataclasses import dataclass

# code -> (sector, label)
CAPABILITIES: dict[str, tuple[str, str]] = {
    "CON-ROADS": ("construction", "Road construction"),
    "CON-BLDG": ("construction", "Building works"),
    "CON-CIVIL": ("construction", "Civil engineering"),
    "CON-ELEC": ("construction", "Electrical installation"),
    "ICT-DEV": ("ict", "Software development"),
    "ICT-NET": ("ict", "Networking and infrastructure"),
    "ICT-SUP": ("ict", "IT support services"),
    "AGR-PROD": ("agriculture", "Primary production"),
    "AGR-PROC": ("agriculture", "Agro-processing"),
    "AGR-LOG": ("agriculture", "Cold chain and logistics"),
    "SVC-CLEAN": ("services", "Cleaning and facilities"),
    "SVC-SEC": ("services", "Security services"),
    "SVC-CATER": ("services", "Catering"),
    "MFG-PACK": ("manufacturing", "Packaging"),
    "MFG-FAB": ("manufacturing", "Metal fabrication"),
}

SECTORS = sorted({s for s, _ in CAPABILITIES.values()})


def sector_of(code: str) -> str | None:
    entry = CAPABILITIES.get(code)
    return entry[0] if entry else None


ADJACENT: dict[str, set[str]] = {
    "Gauteng": {"Limpopo", "Mpumalanga", "Free State", "North West"},
    "Limpopo": {"Gauteng", "Mpumalanga", "North West"},
    "Mpumalanga": {"Gauteng", "Limpopo", "Free State", "KwaZulu-Natal"},
    "North West": {"Gauteng", "Limpopo", "Free State", "Northern Cape"},
    "Free State": {
        "Gauteng",
        "Mpumalanga",
        "North West",
        "KwaZulu-Natal",
        "Eastern Cape",
        "Northern Cape",
    },
    "KwaZulu-Natal": {"Mpumalanga", "Free State", "Eastern Cape"},
    "Eastern Cape": {"KwaZulu-Natal", "Free State", "Northern Cape", "Western Cape"},
    "Northern Cape": {"North West", "Free State", "Eastern Cape", "Western Cape"},
    "Western Cape": {"Eastern Cape", "Northern Cape"},
}

PROVINCES = sorted(ADJACENT)


@dataclass(frozen=True)
class Credential:
    code: str
    label: str
    issuer: str
    days: int  # first-time turnaround
    renew_days: int  # renewal of an expired credential
    cost_zar: int


COMPLIANCE_CATALOGUE: dict[str, Credential] = {
    c.code: c
    for c in [
        Credential("TCS", "Tax compliance status PIN", "SARS", 7, 3, 0),
        Credential("BBBEE", "B-BBEE affidavit", "Commissioner of oaths", 3, 2, 200),
        Credential(
            "COID",
            "Letter of good standing (COIDA)",
            "Department of Employment and Labour",
            14,
            7,
            0,
        ),
        Credential("CSD", "CSD registration", "National Treasury", 5, 2, 0),
        Credential("CIDB", "CIDB grading certificate", "CIDB", 30, 14, 4200),
    ]
}
