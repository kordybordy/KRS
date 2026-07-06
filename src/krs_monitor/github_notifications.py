"""GitHub issue notifications for generated KRS monitoring reports."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from krs_monitor.config import REPORTS_DIR
from krs_monitor.notifications import find_report_dir

_GITHUB_USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


@dataclass(frozen=True)
class IssueNotification:
    has_changes: bool
    title: str
    body: str


def build_issue_notification(
    report_dir: Path,
    *,
    notify_users: Sequence[str] = (),
    max_details: int = 10,
) -> IssueNotification:
    """Build a GitHub issue title and body from a generated report directory."""

    report_data = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    summary = (report_dir / "summary.txt").read_text(encoding="utf-8").strip()
    report_date = str(report_data.get("date") or report_dir.name)
    has_changes = any(result.get("diff", {}).get("differences") for result in report_data.get("results", []))
    title = f"KRS monitor: changes detected for {report_date}" if has_changes else f"KRS monitor: no changes for {report_date}"

    lines = [f"## KRS monitoring summary for {report_date}", ""]
    mentions = _mention_line(notify_users)
    if mentions:
        lines.extend([mentions, ""])

    lines.extend([summary or "No summary lines were generated.", ""])

    details = _changed_detail_lines(report_data, max_details)
    if details:
        lines.extend(["## Changed values", "", *details, ""])
    else:
        lines.extend(["No changed values were reported.", ""])

    lines.extend(
        [
            "## Report files",
            "",
            f"- `{report_dir.as_posix()}/report.md`",
            f"- `{report_dir.as_posix()}/comparison.csv`",
            "",
            "_Generated automatically by the KRS monitor workflow._",
            "",
        ]
    )
    return IssueNotification(has_changes=has_changes, title=title, body="\n".join(lines))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a GitHub issue notification for a KRS monitor report.")
    parser.add_argument("--reports-dir", type=Path, default=REPORTS_DIR)
    parser.add_argument("--report-date", help="Report date directory to notify about, for example 2026-07-06.")
    parser.add_argument("--body-file", type=Path, default=Path("krs-github-issue-body.md"))
    parser.add_argument("--github-output", type=Path, default=Path(os.environ["GITHUB_OUTPUT"]) if os.getenv("GITHUB_OUTPUT") else None)
    parser.add_argument("--notify-users", default=os.getenv("KRS_GITHUB_NOTIFY_USERS", ""))
    parser.add_argument("--max-details", type=int, default=int(os.getenv("KRS_GITHUB_MAX_DETAILS", "10")))
    args = parser.parse_args(argv)

    report_dir = find_report_dir(args.reports_dir, args.report_date)
    notification = build_issue_notification(
        report_dir,
        notify_users=_split_users(args.notify_users),
        max_details=args.max_details,
    )
    args.body_file.write_text(notification.body, encoding="utf-8")

    if args.github_output:
        _append_github_output(
            args.github_output,
            {
                "has_changes": "true" if notification.has_changes else "false",
                "title": notification.title,
                "body_file": str(args.body_file),
            },
        )
    else:
        print(notification.title)
        print(notification.body)

    return 0


def _changed_detail_lines(report_data: dict[str, Any], max_details: int) -> list[str]:
    lines: list[str] = []
    remaining = max(0, max_details)
    omitted = 0

    for result in report_data.get("results", []):
        differences = result.get("diff", {}).get("differences", [])
        if not differences:
            continue

        if remaining > 0:
            lines.append(f"### {result.get('name', 'Unknown entity')} - KRS: {result.get('krs', 'unknown')}")
            lines.append("")
        for difference in differences:
            if remaining <= 0:
                omitted += 1
                continue
            lines.append(_format_difference(difference))
            remaining -= 1
        if remaining > 0:
            lines.append("")

    if lines and lines[-1] == "":
        lines.pop()
    if omitted:
        lines.append(f"...and {omitted} more changed value(s).")
    return lines


def _format_difference(difference: dict[str, Any]) -> str:
    path = difference.get("path", "unknown path")
    change_type = difference.get("type")
    if change_type == "added":
        return f"- `{path}`: added `{_short_value(difference.get('after'))}`"
    if change_type == "removed":
        return f"- `{path}`: removed `{_short_value(difference.get('before'))}`"
    return (
        f"- `{path}`: changed from `{_short_value(difference.get('before'))}` "
        f"to `{_short_value(difference.get('after'))}`"
    )


def _short_value(value: Any, limit: int = 240) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _mention_line(users: Sequence[str]) -> str:
    mentions = [f"@{user}" for user in _valid_users(users)]
    return f"Notifying: {' '.join(mentions)}" if mentions else ""


def _split_users(value: str) -> list[str]:
    users = []
    for item in value.replace(";", ",").replace("\n", ",").split(","):
        user = item.strip().lstrip("@")
        if user:
            users.append(user)
    return users


def _valid_users(users: Sequence[str]) -> list[str]:
    valid = []
    for user in users:
        normalized = user.strip().lstrip("@")
        if _GITHUB_USERNAME_RE.match(normalized):
            valid.append(normalized)
    return valid


def _append_github_output(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


if __name__ == "__main__":
    raise SystemExit(main())
