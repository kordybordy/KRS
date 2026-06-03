"""Runtime configuration for the KRS monitor."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict


class TrackedEntity(TypedDict):
    """Entity monitored by KRS number."""

    name: str
    krs: str


TRACKED_ENTITIES: list[TrackedEntity] = [
    {
        "name": "CGI Information Systems and Management Consultants (Polska) Sp. z o.o.",
        "krs": "0000078664",
    },
    {
        "name": "CGI Polska S.A.",
        "krs": "0000307263",
    },
]

DATA_LATEST_DIR = Path("data/latest")
DATA_ARCHIVE_DIR = Path("data/archive")
REPORTS_DIR = Path("reports")

PRS_FULL_EXTRACT_ENDPOINT = "https://api-krs.ms.gov.pl/api/krs/OdpisPelny/{krs}"
PRS_REGISTER = "P"
PRS_FORMAT = "json"
REQUEST_TIMEOUT_SECONDS = 30
