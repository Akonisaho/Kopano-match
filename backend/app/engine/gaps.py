"""Readiness-axis requirement -> costed, dated gap."""

from .gate import credential_status
from .taxonomy import COMPLIANCE_CATALOGUE
from .types import READINESS_TYPES, SME, DocStatus, Gap, Opportunity


def build_gaps(opp: Opportunity, sme: SME, all_open: list[Opportunity]) -> list[Gap]:
    gaps: list[Gap] = []
    for req in opp.requirements:
        if req.type not in READINESS_TYPES:
            continue
        status = credential_status(req, sme)
        if status == DocStatus.VALID:
            continue
        code = req.value["doc"]
        cred = COMPLIANCE_CATALOGUE[code]
        unlocks = sum(
            1
            for other in all_open
            if other.id != opp.id
            and other.status == "open"
            and any(
                r.mandatory and r.type in READINESS_TYPES and r.value["doc"] == code
                for r in other.requirements
            )
        )
        gaps.append(
            Gap(
                credential=code,
                label=cred.label,
                status=status,
                mandatory=req.mandatory,
                issuer=cred.issuer,
                days=cred.renew_days if status == DocStatus.EXPIRED else cred.days,
                cost_zar=cred.cost_zar,
                also_unlocks=unlocks,
            )
        )
    return gaps
