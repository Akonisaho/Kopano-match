"""The ClamAV scanner: the protocol against a stand-in server, and a real ClamAV if one is running."""

import socket
import socketserver
import struct
import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from app.adapters import clamav
from app.adapters.base import MalwareScanner, ScannerUnavailable, ScanResult
from app.config import settings
from app.main import app

# The standard antivirus test string, split so this file is not itself quarantined
EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class FakeClamd(socketserver.ThreadingTCPServer):
    """Speaks just enough of the clamd protocol: PING, and INSTREAM with a canned answer."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, answer: str):
        super().__init__(("127.0.0.1", 0), FakeHandler)
        self.answer = answer
        self.received = b""


class FakeHandler(socketserver.BaseRequestHandler):
    def handle(self):
        command = b""
        while not command.endswith(b"\0"):
            command += self.request.recv(1)
        if command == b"zPING\0":
            self.request.sendall(b"PONG\0")
            return
        assert command == b"zINSTREAM\0"
        body = b""
        while True:
            (size,) = struct.unpack("!I", self._read(4))
            if size == 0:
                break
            body += self._read(size)
        self.server.received = body
        self.request.sendall(self.server.answer.encode() + b"\0")

    def _read(self, n: int) -> bytes:
        out = b""
        while len(out) < n:
            part = self.request.recv(n - len(out))
            if not part:
                raise ConnectionError
            out += part
        return out


@pytest.fixture
def clamd(monkeypatch):
    servers = []

    def start(answer: str) -> FakeClamd:
        server = FakeClamd(answer)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        monkeypatch.setattr(settings, "clamav_host", "127.0.0.1")
        monkeypatch.setattr(settings, "clamav_port", server.server_address[1])
        monkeypatch.setattr(settings, "clamav_timeout", 3.0)
        servers.append(server)
        return server

    yield start
    for s in servers:
        s.shutdown()
        s.server_close()


def test_clean_file_is_clean_and_the_whole_file_is_streamed(clamd):
    server = clamd("stream: OK")
    data = b"%PDF-1.4\n" + b"x" * 200_000  # larger than one chunk
    result = clamav.ClamAVScanner().scan(data)
    assert result == ScanResult(True, None, "ClamAV")
    assert server.received == data
    assert clamav.ping() is True


def test_infected_file_reports_the_signature(clamd):
    clamd("stream: Win.Test.EICAR_HDB-1 FOUND")
    result = clamav.ClamAVScanner().scan(EICAR)
    assert result.clean is False and result.signature == "Win.Test.EICAR_HDB-1"


def test_an_error_answer_is_never_treated_as_clean(clamd):
    clamd("INSTREAM size limit exceeded. ERROR")
    with pytest.raises(ScannerUnavailable):
        clamav.ClamAVScanner().scan(b"anything")


def test_unreachable_scanner_fails_closed(monkeypatch):
    with socket.socket() as s:  # find a port nothing listens on
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    monkeypatch.setattr(settings, "clamav_port", free)
    monkeypatch.setattr(settings, "clamav_timeout", 1.0)
    with pytest.raises(ScannerUnavailable):
        clamav.ClamAVScanner().scan(b"anything")
    assert clamav.ping() is False


def test_upload_is_refused_with_503_and_nothing_stored_when_the_scanner_is_down(monkeypatch):
    from app.routers import documents

    class Down(MalwareScanner):
        def scan(self, data):
            raise ScannerUnavailable("down")

    monkeypatch.setattr(documents, "malware_scanner", lambda: Down())
    client = TestClient(app)
    reg = client.post(
        "/auth/register",
        json={
            "email": f"{uuid.uuid4().hex[:8]}@kopano-test.com",
            "password": "a-long-test-password",
            "full_name": "Scan Down",
            "role": "sme",
            "organisation_name": "Scan Down Org",
            "consent": True,
        },
    )
    h = {"Authorization": "Bearer " + reg.json()["access_token"]}
    r = client.post(
        "/documents",
        headers=h,
        data={"document_type": "TCS"},
        files={"file": ("t.pdf", b"%PDF-1.4\nclean", "application/pdf")},
    )
    assert r.status_code == 503 and "not available" in r.json()["detail"]
    assert client.get("/documents", headers=h).json() == []


def test_upload_is_refused_when_the_scanner_flags_the_file(clamd, monkeypatch):
    clamd("stream: Win.Test.EICAR_HDB-1 FOUND")
    monkeypatch.setattr(settings, "scanner_provider", "clamav")
    client = TestClient(app)
    reg = client.post(
        "/auth/register",
        json={
            "email": f"{uuid.uuid4().hex[:8]}@kopano-test.com",
            "password": "a-long-test-password",
            "full_name": "Scan Hit",
            "role": "sme",
            "organisation_name": "Scan Hit Org",
            "consent": True,
        },
    )
    h = {"Authorization": "Bearer " + reg.json()["access_token"]}
    r = client.post(
        "/documents",
        headers=h,
        data={"document_type": "TCS"},
        files={"file": ("t.pdf", b"%PDF-1.4\n" + uuid.uuid4().bytes, "application/pdf")},
    )
    assert r.status_code == 422 and "security scan" in r.json()["detail"]
    assert client.get("/documents", headers=h).json() == []


@pytest.mark.skipif(
    not clamav.ping(), reason="no ClamAV running (docker compose --profile scan up -d clamav)"
)
def test_real_clamav_catches_eicar_and_passes_a_clean_file(monkeypatch):
    monkeypatch.setattr(settings, "scanner_provider", "clamav")
    scanner = clamav.ClamAVScanner()
    clean = scanner.scan(b"%PDF-1.4\nhello " + uuid.uuid4().bytes)
    assert clean.clean is True
    # ClamAV's test signature expects the file to BE the test string, so no header in front
    hit = scanner.scan(EICAR)
    assert hit.clean is False and "eicar" in hit.signature.lower()


@pytest.mark.skipif(
    not clamav.ping(), reason="no ClamAV running (docker compose --profile scan up -d clamav)"
)
def test_real_clamav_through_the_upload_endpoint(monkeypatch):
    import sys
    from datetime import date, timedelta
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from make_demo_documents import make_certificate

    monkeypatch.setattr(settings, "scanner_provider", "clamav")
    client = TestClient(app)
    reg = client.post(
        "/auth/register",
        json={
            "email": f"{uuid.uuid4().hex[:8]}@kopano-test.com",
            "password": "a-long-test-password",
            "full_name": "Real Scan",
            "role": "sme",
            "organisation_name": "Real Scan Org",
            "consent": True,
        },
    )
    h = {"Authorization": "Bearer " + reg.json()["access_token"]}
    bad = client.post(
        "/documents",
        headers=h,
        data={"document_type": "TCS"},
        files={"file": ("virus-test.pdf", EICAR, "application/pdf")},
    )
    assert bad.status_code == 422 and "security scan" in bad.json()["detail"]
    cert = make_certificate(
        f"Real Scan {uuid.uuid4().hex[:8]}", "TCS", date.today() + timedelta(days=300)
    )
    good = client.post(
        "/documents",
        headers=h,
        data={"document_type": "TCS"},
        files={"file": ("TCS.pdf", cert, "application/pdf")},
    )
    assert good.status_code == 201 and good.json()["verification"] == "verified"
