import json
from pathlib import Path

from krs_monitor.github_notifications import build_issue_notification


def _write_report(report_dir: Path, differences=None) -> None:
    report_dir.mkdir(parents=True)
    (report_dir / "summary.txt").write_text(
        "CGI Polska S.A. - KRS: 0000307263 - zmiany: TAK: 1 roznica.\n",
        encoding="utf-8",
    )
    (report_dir / "report.json").write_text(
        json.dumps(
            {
                "date": report_dir.name,
                "results": [
                    {
                        "name": "CGI Polska S.A.",
                        "krs": "0000307263",
                        "status": "ok",
                        "diff": {"differences": differences or []},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_build_issue_notification_detects_changes_and_mentions_users(tmp_path: Path) -> None:
    report_dir = tmp_path / "2026-07-06"
    _write_report(
        report_dir,
        [{"path": "root.dane.nazwa", "type": "changed", "before": "Old", "after": "New"}],
    )

    notification = build_issue_notification(report_dir, notify_users=["owner", "@reviewer"])

    assert notification.has_changes is True
    assert notification.title == "KRS monitor: changes detected for 2026-07-06"
    assert "Notifying: @owner @reviewer" in notification.body
    assert "- `root.dane.nazwa`: changed from `Old` to `New`" in notification.body


def test_build_issue_notification_marks_no_changes(tmp_path: Path) -> None:
    report_dir = tmp_path / "2026-07-06"
    _write_report(report_dir)

    notification = build_issue_notification(report_dir)

    assert notification.has_changes is False
    assert notification.title == "KRS monitor: no changes for 2026-07-06"


def test_build_issue_notification_ignores_email_addresses_as_mentions(tmp_path: Path) -> None:
    report_dir = tmp_path / "2026-07-06"
    _write_report(
        report_dir,
        [{"path": "root.dane.nazwa", "type": "changed", "before": "Old", "after": "New"}],
    )

    notification = build_issue_notification(report_dir, notify_users=["przemyslaw.dolegowski@dwf.law"])

    assert "Notifying:" not in notification.body
