"""Command-line entrypoint for KRS monitoring."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from krs_monitor.config import DATA_ARCHIVE_DIR, DATA_LATEST_DIR, REPORTS_DIR, TRACKED_ENTITIES
from krs_monitor.diffing import diff_json
from krs_monitor.normalize import normalize_payload, read_json, write_json
from krs_monitor.prs_client import PrsClientError, fetch_full_extract_by_krs
from krs_monitor.reporting import EntityRunResult, generate_reports

logger = logging.getLogger(__name__)
WARSAW_TZ = ZoneInfo("Europe/Warsaw")


def main() -> int:
    configure_logging()
    run_started_at = datetime.now(WARSAW_TZ)
    results: list[EntityRunResult] = []

    for entity in TRACKED_ENTITIES:
        results.append(_process_entity(entity["name"], entity["krs"], run_started_at))

    try:
        paths = generate_reports(results, run_started_at.date(), REPORTS_DIR)
    except OSError:
        logger.exception("Critical error: could not generate reports")
        return 1

    summary = paths["summary"].read_text(encoding="utf-8")
    print(summary, end="")
    logger.info("Generated reports in %s", paths["report_dir"])
    return 0


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _process_entity(name: str, krs: str, run_started_at: datetime) -> EntityRunResult:
    logger.info("Processing %s (KRS %s)", name, krs)
    try:
        raw_payload = fetch_full_extract_by_krs(krs)
    except PrsClientError as exc:
        logger.error("Skipping snapshot update for KRS %s because fetch failed: %s", krs, exc)
        return {"name": name, "krs": krs, "status": "error", "error": str(exc)}

    try:
        archive_path = _archive_path(krs, run_started_at)
        write_json(archive_path, raw_payload)

        current = normalize_payload(raw_payload)
        latest_path = DATA_LATEST_DIR / f"{krs}.json"
        previous = _load_previous_snapshot(latest_path)
        diff = diff_json(previous, current)
        write_json(latest_path, current)
    except (OSError, TypeError, ValueError) as exc:
        logger.exception("Skipping latest snapshot update for KRS %s because processing failed", krs)
        return {"name": name, "krs": krs, "status": "error", "error": str(exc)}

    return {
        "name": name,
        "krs": krs,
        "status": "ok",
        "diff": diff,
        "archive_path": str(archive_path),
        "latest_path": str(latest_path),
    }


def _load_previous_snapshot(path: Path) -> dict | None:
    if not path.exists():
        return None
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"Previous snapshot is not a JSON object: {path}")
    return data


def _archive_path(krs: str, run_started_at: datetime) -> Path:
    safe_timestamp = run_started_at.isoformat(timespec="seconds").replace(":", "-")
    return DATA_ARCHIVE_DIR / krs / f"{safe_timestamp}.json"


if __name__ == "__main__":
    raise SystemExit(main())
