"""One call(prompt, schema) function. Provider comes from config; failure returns None.

The LLM never scores. It extracts and explains, and every caller has a deterministic fallback,
so a missing key or a flaky network degrades quietly.
"""

import base64
import json
import re
import urllib.request

from pydantic import BaseModel, ValidationError

from ..config import settings

TIMEOUT_SECONDS = 15
FILE_TIMEOUT_SECONDS = 40


def _gemini(prompt: str, file: tuple[bytes, str] | None = None, as_json: bool = False) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    parts: list[dict] = [{"text": prompt}]
    if file:
        data, mime = file
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}})
    payload: dict = {"contents": [{"parts": parts}]}
    if as_json:
        payload["generationConfig"] = {"responseMimeType": "application/json"}
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        # Key travels in a header, never in the URL, so it cannot land in access logs
        headers={"Content-Type": "application/json", "x-goog-api-key": settings.gemini_api_key},
    )
    timeout = FILE_TIMEOUT_SECONDS if file else TIMEOUT_SECONDS
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310  # nosec B310 - fixed https URL
        data = json.load(resp)
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _anthropic(prompt: str) -> str:
    body = json.dumps(
        {
            "model": "claude-haiku-5-5",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:  # noqa: S310  # nosec B310 - fixed https URL
        return json.load(resp)["content"][0]["text"]


def _raw(prompt: str, file: tuple[bytes, str] | None = None, as_json: bool = False) -> str | None:
    if settings.llm_provider == "gemini" and settings.gemini_api_key:
        return _gemini(prompt, file, as_json)
    if file:
        return None  # only Gemini reads files here
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        return _anthropic(prompt)
    return None


def call(prompt: str, schema: type[BaseModel] | None = None, file: tuple[bytes, str] | None = None):
    """Return a validated `schema` instance (or plain text if no schema), or None on any failure.

    `file` is (bytes, mime type) for a document the model should read. With a schema the model is
    asked for JSON directly, and the reply is still validated before anything uses it.
    """
    try:
        text = _raw(prompt, file, as_json=schema is not None)
    except Exception:  # noqa: BLE001 - network, quota, bad key: all degrade to the fallback
        return None
    if not text:
        return None
    if schema is None:
        return text.strip()
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return schema.model_validate_json(cleaned)
    except (ValidationError, ValueError):
        return None
