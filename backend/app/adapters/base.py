"""One interface per external source. Routers depend on these, never on a concrete provider.

Real adapters (CIPC, CSD, SARS TCS, an identity vendor) implement the same bases and are
selected in config.py. Only the mocks are wired for the hackathon.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class VerificationResult:
    result: str  # verified | not_found | non_compliant | rejected
    confidence: float
    source_label: str  # shown in the UI next to the tick
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def flagged(self) -> bool:
        return self.result != "verified"


@dataclass(frozen=True)
class ScanResult:
    clean: bool
    signature: str | None
    source_label: str


class ScannerUnavailable(RuntimeError):
    """The scanner could not give an answer. Callers must treat this as 'not scanned', never as clean."""


class MalwareScanner(ABC):
    @abstractmethod
    def scan(self, data: bytes) -> ScanResult:
        """Scan an upload before it is stored. A real engine (for example ClamAV) goes here."""


class IdentityProvider(ABC):
    @abstractmethod
    def verify(self, masked_id_number: str, selfie: bytes) -> VerificationResult:
        """Implementations must not retain `selfie`. Only the outcome is stored."""


class RegistryProvider(ABC):
    @abstractmethod
    def lookup(self, registration_number: str) -> VerificationResult:
        """Company registry check (CIPC / CSD)."""


class TaxProvider(ABC):
    @abstractmethod
    def compliance_status(self, registration_number: str) -> VerificationResult:
        """SARS tax compliance status."""
