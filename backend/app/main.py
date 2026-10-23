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


for r in (auth, smes, documents, opportunities, matches, applications, providers, admin, meta):
    app.include_router(r.router)


@app.get("/health")
def health():
    return {"status": "ok"}
