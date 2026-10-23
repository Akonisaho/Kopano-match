"""Malware scanning with ClamAV, over its clamd network protocol. No extra Python library.

ClamAV is an open-source antivirus engine. It runs as a separate service (see docker-compose.yml,
profile `scan`) and is not linked into this application. Uploads are streamed to it and only
stored if it answers OK. If it cannot be reached, the scan raises ScannerUnavailable and the
upload is refused: the safe default is to fail closed.
"""

import socket
import struct

from ..config import settings
from .base import MalwareScanner, ScannerUnavailable, ScanResult

CHUNK = 64 * 1024
LABEL = "ClamAV"


def _read_reply(sock: socket.socket) -> str:
    buf = b""
    while not buf.endswith(b"\0"):
        part = sock.recv(4096)
        if not part:
            break
        buf += part
        if len(buf) > 4096:
            break
    return buf.rstrip(b"\0").decode("utf8", "replace").strip()


def _connect() -> socket.socket:
    try:
        sock = socket.create_connection(
            (settings.clamav_host, settings.clamav_port), timeout=settings.clamav_timeout
        )
        sock.settimeout(settings.clamav_timeout)
        return sock
    except OSError as e:
        raise ScannerUnavailable(
            f"cannot reach ClamAV at {settings.clamav_host}:{settings.clamav_port}"
        ) from e


def ping() -> bool:
    """True if clamd answers PONG. Used by the key checker and the smoke test."""
    try:
        with _connect() as sock:
            sock.sendall(b"zPING\0")
            return _read_reply(sock) == "PONG"
    except (ScannerUnavailable, OSError):
        return False


class ClamAVScanner(MalwareScanner):
    def scan(self, data: bytes) -> ScanResult:
        try:
            with _connect() as sock:
                sock.sendall(b"zINSTREAM\0")
                for start in range(0, len(data), CHUNK):
                    chunk = data[start : start + CHUNK]
                    sock.sendall(struct.pack("!I", len(chunk)) + chunk)
                sock.sendall(struct.pack("!I", 0))  # end of stream
                reply = _read_reply(sock)
        except OSError as e:  # timeouts and resets mid-scan
            raise ScannerUnavailable("the scan did not complete") from e
        text = reply.removeprefix("stream:").strip()
        if text == "OK":
            return ScanResult(True, None, LABEL)
        if text.endswith("FOUND"):
            return ScanResult(False, text.removesuffix("FOUND").strip(), LABEL)
        raise ScannerUnavailable(f"unexpected answer from ClamAV: {text[:80]}")
