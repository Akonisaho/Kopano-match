import csv
import io
import uuid
from collections import Counter

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import insights
from .. import models as m
from ..audit import write_audit
from ..auth import KINDS_BY_ROLE, PROVIDER_ROLES, current_user, require_role
from ..db import get_db
from ..llm import client, prompts
from ..schemas import ExtractIn, OpportunityIn
from ..services import consortium as build_consortium
from ..services import consortium_invitation
from ..services import run_matching

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _summary(o: m.Opportunity, provider_name: str | None = None) -> dict:
    return {
        "id": o.id,
        "title": o.title,
        "sector": o.sector,
        "province": o.province,
        "contract_value": float(o.contract_value),
        "duration_months": o.duration_months,
        "status": o.status,
        "kind": o.kind,
        "deadline": o.deadline,
        "provider": provider_name,
    }


def owned_opportunity(db: Session, user: m.User, opp_id: uuid.UUID) -> m.Opportunity:
    """Object-level authorisation: a corporate only reaches its own opportunities."""
    o = db.get(m.Opportunity, opp_id)
    if o is None or (user.role != "admin" and o.organisation_id != user.organisation_id):
        raise HTTPException(404, "Not found")
    return o


def _persist(db: Session, user: m.User, body: OpportunityIn) -> m.Opportunity:
    if body.kind not in KINDS_BY_ROLE[user.role]:
        raise HTTPException(
            422, f"A {user.role} account can post: {', '.join(KINDS_BY_ROLE[user.role])}"
        )
    o = m.Opportunity(
        organisation_id=user.organisation_id,
        kind=body.kind,
        description=body.description,
        deadline=body.deadline,
        title=body.title,
        sector=body.sector,
        province=body.province,
        contract_value=body.contract_value,
        duration_months=body.duration_months,
        payment_terms_days=body.payment_terms_days,
        scope_items=[i.model_dump() for i in body.scope_items],
        transformation_gap=body.transformation_gap,
    )
    db.add(o)
    db.flush()
    for r in body.requirements:
        db.add(
            m.OpportunityRequirement(
                opportunity_id=o.id,
                requirement_type=r.requirement_type.value,
                requirement_value=r.requirement_value,
                mandatory=r.mandatory,
                weight=r.weight,
            )
        )
    write_audit(
        db,
        user.id,
        "opportunity_create",
        "opportunity",
        o.id,
        new={"title": o.title, "requirements": len(body.requirements)},
    )
    return o


@router.post("", status_code=201)
def create(
    body: OpportunityIn,
    user: m.User = Depends(require_role(*PROVIDER_ROLES)),
    db: Session = Depends(get_db),
):
    o = _persist(db, user, body)
    db.commit()
    return _summary(o)


IMPORT_COLUMNS = [
    "title", "kind", "sector", "province", "contract_value", "duration_months",
    "payment_terms_days", "deadline", "description", "capabilities", "documents", "min_years",
]  # fmt: skip
IMPORT_TEMPLATE = (
    ",".join(IMPORT_COLUMNS)
    + "\nProvincial roads rehabilitation,procurement,construction,Gauteng,4200000,12,30,2026-12-01,"
    '"Resurfacing and drainage on provincial roads",CON-ROADS:2500000;CON-CIVIL:1700000,TCS;BBBEE;CIDB,3\n'
)
MAX_IMPORT_ROWS = 200
MAX_IMPORT_BYTES = 200_000


def _row_to_opportunity(row: dict) -> OpportunityIn:
    scope, requirements = [], []
    for part in filter(None, (row.get("capabilities") or "").split(";")):
        code, _, value = part.partition(":")
        scope.append({"code": code.strip(), "value": float(value)})
        requirements.append(
            {
                "requirement_type": "capability",
                "requirement_value": {"code": code.strip()},
                "weight": 10,
            }
        )
    for code in filter(None, (row.get("documents") or "").replace(" ", "").split(";")):
        kind = "certification" if code == "CIDB" else "compliance_doc"
        requirements.append(
            {"requirement_type": kind, "requirement_value": {"doc": code}, "weight": 10}
        )
    if (row.get("min_years") or "").strip():
        requirements.append(
            {
                "requirement_type": "min_years",
                "requirement_value": {"years": int(row["min_years"])},
                "weight": 5,
            }
        )
    return OpportunityIn.model_validate(
        {
            "kind": (row.get("kind") or "procurement").strip(),
            "title": (row.get("title") or "").strip(),
            "description": (row.get("description") or "").strip() or None,
            "deadline": (row.get("deadline") or "").strip() or None,
            "sector": (row.get("sector") or "").strip(),
            "province": (row.get("province") or "").strip(),
            "contract_value": float(row.get("contract_value") or 0),
            "duration_months": int(row.get("duration_months") or 0),
            "payment_terms_days": int(row.get("payment_terms_days") or 30),
            "scope_items": scope,
            "requirements": requirements,
        }
    )


@router.get("/import/template")
def import_template(user: m.User = Depends(require_role(*PROVIDER_ROLES))):
    return Response(
        IMPORT_TEMPLATE,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="opportunities-template.csv"'},
    )


@router.post("/import")
async def import_opportunities(
    dry_run: bool = False,
    file: UploadFile = File(...),
    user: m.User = Depends(require_role(*PROVIDER_ROLES)),
    db: Session = Depends(get_db),
):
    """Bulk-load opportunities from a CSV, so a procurement system can export and upload.
    All or nothing: one bad row stops the import and every problem is listed with its row."""
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "The file is too large (200 KB limit)")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    except UnicodeDecodeError:
        raise HTTPException(415, "Save the file as CSV (UTF-8)") from None
    if not reader.fieldnames or "title" not in reader.fieldnames:
        raise HTTPException(422, "The first row must be the column names. Download the template.")
    parsed: list[OpportunityIn] = []
    errors: list[dict] = []
    for n, row in enumerate(reader, start=2):
        if n - 1 > MAX_IMPORT_ROWS:
            raise HTTPException(422, f"At most {MAX_IMPORT_ROWS} rows per import")
        try:
            parsed.append(_row_to_opportunity(row))
        except Exception as e:  # noqa: BLE001 - any bad cell becomes a row-level message
            detail = (
                "; ".join(x["msg"].replace("Value error, ", "") for x in e.errors())
                if hasattr(e, "errors")
                else "check the numbers and codes in this row"
            )
            errors.append({"row": n, "error": detail})
    if errors or dry_run:
        if errors and not dry_run:
            raise HTTPException(422, {"message": "Nothing was imported", "errors": errors})
        return {
            "rows": len(parsed),
            "created": 0,
            "errors": errors,
            "titles": [p.title for p in parsed],
        }
    for body in parsed:
        _persist(db, user, body)
    db.commit()
    return {
        "rows": len(parsed),
        "created": len(parsed),
        "errors": [],
        "titles": [p.title for p in parsed],
    }


@router.post("/extract")
def extract(body: ExtractIn, user: m.User = Depends(require_role(*PROVIDER_ROLES))):
    prompt = prompts.EXTRACT_REQUIREMENTS.format(
        sectors=sorted({*prompts.SECTORS}),
        provinces=prompts.PROVINCES,
        docs=sorted(prompts.COMPLIANCE_CATALOGUE),
        codes=sorted(prompts.CAPABILITIES),
        text=body.text,
    )
    result = client.call(prompt, prompts.RequirementExtraction)
    if result is None:
        return {"source": "fallback", "draft": prompts.RequirementExtraction().model_dump()}
    return {"source": "llm", "draft": result.model_dump()}


@router.get("")
def list_opportunities(user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(m.Opportunity).order_by(m.Opportunity.created_at.desc())
    if user.role in PROVIDER_ROLES:
        q = q.where(m.Opportunity.organisation_id == user.organisation_id)
    elif user.role == "sme":
        q = q.where(m.Opportunity.status == "open")
    elif user.role != "admin":
        raise HTTPException(403, "Role not permitted")
    opps = list(db.scalars(q))
    counts: dict[uuid.UUID, Counter] = {}
    if user.role in (*PROVIDER_ROLES, "admin"):
        for opp_id, quadrant in db.execute(select(m.Match.opportunity_id, m.Match.quadrant)):
            counts.setdefault(opp_id, Counter())[quadrant] += 1
    names = {i: n for i, n in db.execute(select(m.Organisation.id, m.Organisation.name))}
    return [
        {
            **_summary(o, names.get(o.organisation_id)),
            **({"quadrants": dict(counts.get(o.id, {}))} if user.role != "sme" else {}),
        }
        for o in opps
    ]


@router.get("/{opp_id}")
def detail(opp_id: uuid.UUID, user: m.User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == "sme":
        o = db.get(m.Opportunity, opp_id)
        if o is None or o.status != "open":
            raise HTTPException(404, "Not found")
    else:
        o = owned_opportunity(db, user, opp_id)
    reqs = db.scalars(
        select(m.OpportunityRequirement).where(m.OpportunityRequirement.opportunity_id == o.id)
    )
    return {
        **_summary(o, db.get(m.Organisation, o.organisation_id).name),
        "description": o.description,
        "payment_terms_days": o.payment_terms_days,
        "scope_items": o.scope_items,
        "transformation_gap": o.transformation_gap,
        "requirements": [
            {
                "id": r.id,
                "requirement_type": r.requirement_type,
                "requirement_value": r.requirement_value,
                "mandatory": r.mandatory,
                "weight": r.weight,
            }
            for r in reqs
        ],
    }


def _match_row(match: m.Match, org: m.Organisation) -> dict:
    return {
        "match_id": match.id,
        "sme_id": match.sme_id,
        "sme_name": org.name,
        "verification_status": org.verification_status,
        "gate": match.gate,
        "quadrant": match.quadrant,
        "fit": float(match.fit_score),
        "readiness": float(match.readiness_score),
        "overall": float(match.overall_score),
        "risk_flags": match.risk_flags,
        "gap_count": len(match.explanation.get("gaps", [])),
        "status": match.status,
    }


@router.post("/{opp_id}/match")
def run_match(
    opp_id: uuid.UUID,
    user: m.User = Depends(require_role(*PROVIDER_ROLES, "admin")),
    db: Session = Depends(get_db),
):
    o = owned_opportunity(db, user, opp_id)
    saved = run_matching(db, o.id)
    write_audit(
        db,
        user.id,
        "match_run",
        "opportunity",
        o.id,
        new={"matches": len(saved), "model_version": "v1"},
    )
    db.commit()
    return _ranked(db, o.id)


@router.get("/{opp_id}/matches")
def matches(
    opp_id: uuid.UUID,
    user: m.User = Depends(require_role(*PROVIDER_ROLES, "admin")),
    db: Session = Depends(get_db),
):
    o = owned_opportunity(db, user, opp_id)
    return _ranked(db, o.id)


def _ranked(db: Session, opp_id: uuid.UUID) -> list[dict]:
    rows = db.execute(
        select(m.Match, m.Organisation)
        .join(m.Organisation, m.Organisation.id == m.Match.sme_id)
        .where(m.Match.opportunity_id == opp_id)
        .order_by(m.Match.overall_score.desc())
    ).all()
    stars = insights.star_map(db, [match.sme_id for match, _ in rows])
    out = []
    for match, org in rows:
        row = _match_row(match, org)
        # Context beside the score. The order above is by match score alone.
        rating, n = stars.get(match.sme_id, (None, 0))
        row["rating"], row["reviews"] = rating, n
        out.append(row)
    return out


@router.get("/{opp_id}/consortium")
def consortium(
    opp_id: uuid.UUID,
    user: m.User = Depends(require_role(*PROVIDER_ROLES, "admin")),
    db: Session = Depends(get_db),
):
    o = owned_opportunity(db, user, opp_id)
    built = build_consortium(db, o.id)
    if built is None:
        raise HTTPException(404, "Not found")
    _, smes, c = built
    invitation = consortium_invitation(db, o.id)
    if c is None:
        return {"consortium": None, "invitation": invitation}
    names = {s.id: s.name for s in smes}
    return {
        "consortium": {
            "lead": {"sme_id": c.lead_sme_id, "name": names[c.lead_sme_id]},
            "members": [{"sme_id": i, "name": names[i]} for i in c.member_sme_ids],
            "coverage_pct": c.coverage_pct,
            "uncovered_codes": c.uncovered_codes,
        },
        "invitation": invitation,
    }
