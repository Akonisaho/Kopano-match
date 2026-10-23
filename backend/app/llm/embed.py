"""Text embeddings for semantic search. Advisory only: they rank what to look at, never who qualifies.

`embed` returns None when no provider is configured or the call fails, and every caller then falls
back to plain keyword overlap, so search keeps working offline.
"""

import json
import math
import urllib.request

from ..config import settings
from . import local

TIMEOUT_SECONDS = 20
DIMENSIONS = 768
MAX_BATCH = 50


def _call(texts: list[str], task: str) -> list[list[float]]:
    model = f"models/{settings.embedding_model}"
    body = json.dumps(
        {
            "requests": [
                {
                    "model": model,
                    "content": {"parts": [{"text": t[:6000]}]},
                    "taskType": task,
                    "outputDimensionality": DIMENSIONS,
                }
                for t in texts
            ]
        }
    ).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/{model}:batchEmbedContents",
        data=body,
        # Key travels in a header, never in the URL, so it cannot land in access logs
        headers={"Content-Type": "application/json", "x-goog-api-key": settings.gemini_api_key},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:  # noqa: S310  # nosec B310 - fixed https URL
        data = json.load(resp)
    return [e["values"] for e in data["embeddings"]]


def embed(texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]] | None:
    """task: RETRIEVAL_DOCUMENT for things searched, RETRIEVAL_QUERY for what someone typed."""
    if not texts:
        return None
    if settings.llm_provider == "local":
        return local.embed(texts)
    if settings.llm_provider != "gemini" or not settings.gemini_api_key:
        return None
    try:
        out: list[list[float]] = []
        for i in range(0, len(texts), MAX_BATCH):
            out.extend(_call(texts[i : i + MAX_BATCH], task))
        return out if len(out) == len(texts) else None
    except Exception:  # noqa: BLE001 - network, quota, bad key: all degrade to keyword search
        return None


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# Unrelated texts score about 0.5 with these embeddings and close matches 0.8 or more, so raw
# cosine looks flat. This stretches 0.45 to 0.95 across 0 to 100. A display aid, not a probability.
FLOOR, CEIL = 0.45, 0.95


LOCAL_FLOOR, LOCAL_CEIL = 0.04, 0.55  # hashed word vectors spread differently


def calibrated(c: float) -> int:
    lo, hi = (LOCAL_FLOOR, LOCAL_CEIL) if settings.llm_provider == "local" else (FLOOR, CEIL)
    return max(0, min(100, round(100 * (c - lo) / (hi - lo))))
