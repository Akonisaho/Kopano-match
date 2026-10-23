"""Rebuild the schema, apply grants, load the planted demo data.  Run from backend/:  python seed.py

DESTRUCTIVE: drops and recreates every table. It refuses to run unless ENVIRONMENT=dev.
Runs as the admin role; the app itself connects as kopano_app, which cannot touch the audit log.
All demo accounts share SEED_PASSWORD (default below). Never use this seed outside a demo.
"""

import os
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app import models as m
from app.adapters.mock import registry_provider, tax_provider
from app.auth import hash_password
from app.config import settings
from app.db import Base
from app.engine.taxonomy import COMPLIANCE_CATALOGUE
from app.engine.types import DocStatus
from app.seed_data import OPP_META, build_seed
from app.services import run_matching

NS = uuid.UUID("6f1d3a52-1c1e-4b52-9a54-0c2f7d3a9e11")
DB_DIR = Path(__file__).parent / "db"
SEED_PASSWORD = os.environ.get("SEED_PASSWORD", "Demo-Password-1!")

PROVIDERS = {
    "corporate": (
        "Metro Enterprise Group",
        "corporate@kopano.demo",
        "Corporate Procurement Lead",
        "2001/000001/06",
    ),
    "funder": (
        "Growth Catalyst Fund",
        "funder@kopano.demo",
        "Funding Programme Manager",
        "2005/000002/06",
    ),
    "support": ("Enterprise Africa", "support@kopano.demo", "Programme Director", "2008/000003/06"),
}


def sid(key: str) -> uuid.UUID:
    return uuid.uuid5(NS, key)


def main() -> None:
    if settings.environment != "dev":
        raise SystemExit("Refusing to reseed: ENVIRONMENT is not 'dev'.")
    admin = create_engine(settings.admin_database_url)
    with admin.begin() as conn:
        conn.execute(text((DB_DIR / "init.sql").read_text()))
    Base.metadata.drop_all(admin)
    Base.metadata.create_all(admin)
    with admin.begin() as conn:
        conn.execute(text((DB_DIR / "grants.sql").read_text()))

    smes, opps, meta = build_seed()
    pw = hash_password(SEED_PASSWORD)
    today = date.today()
    consent = dict(consent_version=settings.consent_version, consent_at=datetime.now(UTC))

    with Session(admin) as db:
        provider_orgs = {}
        for role, (name, email, person, reg) in PROVIDERS.items():
            org = m.Organisation(
                id=sid(f"org-{role}"),
                name=name,
                org_type=role,
                registration_number=reg,
                verification_status="verified",
            )
            db.add(org)
            db.flush()
            db.add(
                m.User(
                    id=sid(f"u-{role}"),
                    email=email,
                    password_hash=pw,
                    full_name=person,
                    role=role,
                    organisation_id=org.id,
                    **consent,
                )
            )
            provider_orgs[role] = org
        db.add(
            m.User(
                id=sid("u-admin"),
                email="admin@kopano.demo",
                password_hash=pw,
                full_name="Platform Reviewer",
                role="admin",
                **consent,
            )
        )

        for s in smes:
            mt = meta[s.id]
            org = m.Organisation(
                id=sid(s.id),
                name=s.name,
                org_type="sme",
                registration_number=mt["registration_number"],
            )
            db.add(org)
            db.flush()
            db.add(
                m.User(
                    id=sid(f"u-{s.id}"),
                    email=f"{s.id}@sme.demo",
                    password_hash=pw,
                    full_name=f"{s.name} owner",
                    role="sme",
                    organisation_id=org.id,
                    **consent,
                )
            )
            db.add(
                m.SmeProfile(
                    organisation_id=org.id,
                    sector=s.sector,
                    province=s.province,
                    annual_turnover=s.turnover,
                    years_trading=s.years_trading,
                    largest_past_contract=s.largest_past_contract,
                    capability_codes=s.capability_codes,
                    ownership=s.ownership,
                )
            )

            flagged = False
            for provider, r in (
                ("registry", registry_provider().lookup(org.registration_number)),
                ("tax", tax_provider().compliance_status(org.registration_number)),
            ):
                flagged |= r.flagged
                db.add(
                    m.Verification(
                        subject_type="organisation",
                        subject_id=org.id,
                        provider=provider,
                        result=r.result,
                        confidence=r.confidence,
                        source_label=r.source_label,
                        flagged=r.flagged,
                        checked_at=r.checked_at,
                    )
                )
            # Planted SMEs and a share of the filler have a completed identity check
            if int(s.id[-3:]) <= 13 or int(s.id[-3:]) % 2 == 0:
                db.add(
                    m.Verification(
                        subject_type="identity",
                        subject_id=org.id,
                        provider="identity",
                        result="verified",
                        confidence=0.97,
                        source_label="mock adapter (identity + liveness)",
                        flagged=False,
                    )
                )
            org.verification_status = "under_review" if flagged else "verified"

            for code, status in s.documents.items():
                if status == DocStatus.MISSING:
                    continue
                expiry = (
                    today + timedelta(days=365)
                    if status == DocStatus.VALID
                    else today - timedelta(days=30)
                )
                doc = m.Document(
                    id=sid(f"{s.id}-{code}"),
                    organisation_id=org.id,
                    document_type=code,
                    issuer=COMPLIANCE_CATALOGUE[code].issuer,
                    file_url="none",
                    mime_type="application/pdf",
                    size_bytes=0,
                    hash_value=f"{mt['document_hash']}-{code}",
                    expiry_date=expiry,
                    retention_until=today + timedelta(days=365 * 5),
                )
                db.add(doc)
                db.flush()
                # Seed documents carry no file; the duplicate-hash case is planted on TCS
                dup = code == "TCS" and s.id == "sme-013"
                db.add(
                    m.Verification(
                        subject_type="document",
                        subject_id=doc.id,
                        provider="internal",
                        result="duplicate_hash" if dup else "verified",
                        confidence=1.0,
                        source_label="internal checks (type, size, expiry, hash)",
                        flagged=dup,
                    )
                )
        db.flush()

        for o in opps:
            role, kind, days, description = OPP_META[o.id]
            row = m.Opportunity(
                id=sid(o.id),
                organisation_id=provider_orgs[role].id,
                kind=kind,
                title=o.title,
                description=description,
                deadline=today + timedelta(days=days),
                sector=o.sector,
                province=o.province,
                contract_value=o.contract_value,
                duration_months=o.duration_months,
                payment_terms_days=o.payment_terms_days,
                scope_items=[{"code": i.code, "value": i.value} for i in o.scope_items],
                transformation_gap=o.transformation_gap,
            )
            db.add(row)
            db.flush()
            for r in o.requirements:
                db.add(
                    m.OpportunityRequirement(
                        opportunity_id=row.id,
                        requirement_type=r.type.value,
                        requirement_value=r.value,
                        mandatory=r.mandatory,
                        weight=r.weight,
                    )
                )
        db.flush()
        for o in opps:
            run_matching(db, sid(o.id))
        db.flush()

        # A few applications so the journey after matching is populated
        for sme_key, opp_key in (
            ("sme-004", "opp-1"),
            ("sme-005", "opp-1"),
            ("sme-001", "opp-1"),
            ("sme-007", "opp-4"),
            ("sme-008", "opp-8"),
        ):
            match = db.scalar(
                select(m.Match).where(
                    m.Match.sme_id == sid(sme_key), m.Match.opportunity_id == sid(opp_key)
                )
            )
            if match:
                db.add(m.Application(match_id=match.id))
        db.add(
            m.AuditLog(
                user_id=None,
                action="seed",
                entity_type="system",
                new_value={"smes": len(smes), "opportunities": len(opps)},
            )
        )
        db.commit()
    print(f"Seeded {len(smes)} SMEs and {len(opps)} opportunities.")
    print(
        "Logins: corporate@kopano.demo, funder@kopano.demo, support@kopano.demo, "
        "admin@kopano.demo, sme-001@sme.demo ... sme-040@sme.demo"
    )
    print(f"Password for all: {SEED_PASSWORD}")


if __name__ == "__main__":
    main()
