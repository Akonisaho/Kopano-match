"""Deterministic mocks. Their outcomes populate the admin review queue, so keep them stable.

- Registration numbers ending in 7 come back not found.
- One registration number returns non-compliant tax status (sme-011 in the seed).
- Identity: the selfie is discarded; only an outcome and confidence are returned.
"""

from ..config import settings
from .base import (
    IdentityProvider,
    RegistryProvider,
    TaxProvider,
    VerificationResult,
)

NON_COMPLIANT_REGISTRATIONS = {"2018/100011/06"}


class MockIdentityProvider(IdentityProvider):
    def verify(self, masked_id_number: str, selfie: bytes) -> VerificationResult:
        del selfie  # POPIA data minimisation: never persisted, never logged
        return VerificationResult("verified", 0.97, "mock adapter (identity + liveness)")


class MockRegistryProvider(RegistryProvider):
    def lookup(self, registration_number: str) -> VerificationResult:
        if registration_number.endswith("7"):
            return VerificationResult("not_found", 0.0, "mock adapter (CIPC)")
        return VerificationResult("verified", 0.99, "mock adapter (CIPC)")


class MockTaxProvider(TaxProvider):
    def compliance_status(self, registration_number: str) -> VerificationResult:
        if registration_number in NON_COMPLIANT_REGISTRATIONS:
            return VerificationResult("non_compliant", 0.95, "mock adapter (SARS TCS)")
        return VerificationResult("verified", 0.95, "mock adapter (SARS TCS)")


_PROVIDERS = {
    "identity": {"mock": MockIdentityProvider},
    "registry": {"mock": MockRegistryProvider},
    "tax": {"mock": MockTaxProvider},
}


def _build(kind: str, name: str):
    try:
        return _PROVIDERS[kind][name]()
    except KeyError:
        raise RuntimeError(f"No {kind} provider named {name!r} is registered") from None


def identity_provider() -> IdentityProvider:
    return _build("identity", settings.identity_provider)


def registry_provider() -> RegistryProvider:
    return _build("registry", settings.registry_provider)


def tax_provider() -> TaxProvider:
    return _build("tax", settings.tax_provider)
