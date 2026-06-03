"""Client for the official PRS KRS OpenAPI."""

from __future__ import annotations

import logging
from typing import Any

import requests

from krs_monitor.config import (
    PRS_FORMAT,
    PRS_FULL_EXTRACT_ENDPOINT,
    PRS_REGISTER,
    REQUEST_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


class PrsClientError(RuntimeError):
    """Raised when the PRS KRS API cannot return a valid full extract."""


def fetch_full_extract_by_krs(krs: str) -> dict[str, Any]:
    """Fetch the full KRS extract for an entrepreneur register entity by KRS number."""

    url = PRS_FULL_EXTRACT_ENDPOINT.format(krs=krs)
    params = {"rejestr": PRS_REGISTER, "format": PRS_FORMAT}
    logger.info("Fetching full KRS extract for KRS %s from PRS OpenAPI", krs)

    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        logger.exception("PRS KRS API returned HTTP %s for KRS %s", status, krs)
        raise PrsClientError(f"PRS KRS API returned HTTP {status} for KRS {krs}") from exc
    except requests.RequestException as exc:
        logger.exception("Failed to fetch PRS KRS full extract for KRS %s", krs)
        raise PrsClientError(f"Failed to fetch PRS KRS full extract for KRS {krs}: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        logger.exception("PRS KRS API returned invalid JSON for KRS %s", krs)
        raise PrsClientError(f"PRS KRS API returned invalid JSON for KRS {krs}") from exc

    if not isinstance(payload, dict):
        raise PrsClientError(f"PRS KRS API returned non-object JSON for KRS {krs}")

    logger.info("Fetched full KRS extract for KRS %s", krs)
    return payload
