"""Normalize PRS KRS JSON payloads for stable snapshot comparisons."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

TECHNICAL_METADATA_KEYS = {
    "requestId",
    "request_id",
    "traceId",
    "trace_id",
    "correlationId",
    "correlation_id",
    "generatedAt",
    "generated_at",
    "downloadedAt",
    "downloaded_at",
    "timestamp",
}

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a recursively sorted and whitespace-normalized copy of a PRS payload."""

    normalized = _normalize_value(payload)
    if not isinstance(normalized, dict):
        raise TypeError("normalize_payload expects a dictionary payload")
    return normalized


def write_json(path: Path, data: Any) -> None:
    """Write JSON in a stable, UTF-8 format suitable for diffs and snapshots."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def read_json(path: Path) -> Any:
    """Read UTF-8 JSON from disk."""

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_value(value[key])
            for key in sorted(value)
            if key not in TECHNICAL_METADATA_KEYS
        }
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, str):
        return _WHITESPACE_RE.sub(" ", value).strip()
    return value
