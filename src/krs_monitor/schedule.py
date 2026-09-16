"""Fortnightly Thursday reporting, anchored to the first requested send date."""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")
FIRST_REPORT_DATE = date(2026, 10, 1)
REPORT_TIME = time(9, 0)
INTERVAL_DAYS = 14


def _local_time(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("Schedule evaluation requires a timezone-aware datetime")
    return now.astimezone(WARSAW)


def is_report_due(now: datetime) -> bool:
    """Allow a run on its scheduled Thursday at or after 09:00 Warsaw time."""
    local = _local_time(now)
    days = (local.date() - FIRST_REPORT_DATE).days
    return days >= 0 and days % INTERVAL_DAYS == 0 and local.time() >= REPORT_TIME


def next_report_at(now: datetime) -> datetime:
    """Return the first scheduled 09:00 strictly after now, preserving local time."""
    local = _local_time(now)
    periods = max(0, (local.date() - FIRST_REPORT_DATE).days // INTERVAL_DAYS)
    next_date = FIRST_REPORT_DATE + timedelta(days=periods * INTERVAL_DAYS)
    candidate = datetime.combine(next_date, REPORT_TIME, tzinfo=WARSAW)
    if candidate <= local:
        candidate = datetime.combine(next_date + timedelta(days=INTERVAL_DAYS), REPORT_TIME, tzinfo=WARSAW)
    return candidate


def main() -> int:
    now = datetime.now(WARSAW)
    due = is_report_due(now)
    next_run = next_report_at(now).isoformat()
    print(f"Report due: {str(due).lower()}; next scheduled run: {next_run}")
    if output_path := os.getenv("GITHUB_OUTPUT"):
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"should_run={str(due).lower()}\nnext_run={next_run}\n")
    if summary_path := os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write(f"## KRS report schedule\n\nReport due: **{due}**. Next scheduled run: **{next_run}**.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
