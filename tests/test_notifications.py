import json
from pathlib import Path

from krs_monitor.notifications import build_email_message, find_report_dir, load_email_config_from_env


def _write_report(report_dir: Path) -> None:
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
                        "diff": {
                            "differences": [
                                {"path": "root.dane.nazwa", "type": "changed", "before": "Old", "after": "New"}
                            ]
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_load_email_config_returns_none_when_unconfigured() -> None:
    assert load_email_config_from_env({}) is None


def test_load_email_config_parses_recipients_and_defaults() -> None:
    config = load_email_config_from_env(
        {
            "KRS_EMAIL_SMTP_HOST": "smtp.example.com",
            "KRS_EMAIL_FROM": "monitor@example.com",
            "KRS_EMAIL_TO": "one@example.com, two@example.com",
        }
    )

    assert config is not None
    assert config.smtp_host == "smtp.example.com"
    assert config.smtp_port == 587
    assert config.recipients == ["one@example.com", "two@example.com"]
    assert config.use_tls is True
    assert config.use_ssl is False


def test_find_report_dir_picks_latest_report(tmp_path: Path) -> None:
    _write_report(tmp_path / "2026-07-01")
    _write_report(tmp_path / "2026-07-06")

    assert find_report_dir(tmp_path).name == "2026-07-06"


def test_build_email_message_contains_summary_and_changed_details(tmp_path: Path) -> None:
    report_dir = tmp_path / "2026-07-06"
    _write_report(report_dir)
    config = load_email_config_from_env(
        {
            "KRS_EMAIL_SMTP_HOST": "smtp.example.com",
            "KRS_EMAIL_FROM": "monitor@example.com",
            "KRS_EMAIL_TO": "owner@example.com",
            "KRS_EMAIL_SUBJECT_PREFIX": "KRS",
        }
    )

    message = build_email_message(config, report_dir)
    body = message.get_content()

    assert message["Subject"] == "[KRS] 2026-07-06 - changes detected"
    assert "CGI Polska S.A. - KRS: 0000307263 - zmiany: TAK: 1 roznica." in body
    assert "- root.dane.nazwa: changed from `Old` to `New`" in body
