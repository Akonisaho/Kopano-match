import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import DEV_JWT_SECRET, MIN_JWT_SECRET_BYTES, settings
from .routers import (
    admin,
    applications,
    auth,
    documents,
    matches,
    meta,
    notifications,
    opportunities,
    providers,
    smes,
)

if settings.environment != "dev" and (
    settings.jwt_secret == DEV_JWT_SECRET or len(settings.jwt_secret) < MIN_JWT_SECRET_BYTES
):
    raise RuntimeError(
        f"JWT_SECRET must be set to {MIN_JWT_SECRET_BYTES}+ random bytes outside dev"
    )

if settings.environment != "dev" and settings.scanner_provider == "mock":
    raise RuntimeError("SCANNER_PROVIDER must be a real scanner (clamav) outside dev")

if settings.environment != "dev" and not settings.mfa_encryption_key:
    raise RuntimeError("MFA_ENCRYPTION_KEY must be set outside dev")

_kopano_log = logging.getLogger("kopano")
if not _kopano_log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
    _kopano_log.addHandler(_handler)
    _kopano_log.setLevel(logging.INFO)

app = FastAPI(title="Kopano Match API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # explicit list, never "*"
    allow_credentials=False,  # bearer tokens, no cookies
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


for r in (
    auth,
    smes,
    documents,
    opportunities,
    matches,
    applications,
    providers,
    admin,
    meta,
    notifications,
):
    app.include_router(r.router)


@app.get("/health")
def health():
    return {"status": "ok"}
