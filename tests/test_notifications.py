import json
import ssl
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

import pytest

from krs_monitor import notifications
from krs_monitor.notifications import build_email_message, find_report_dir, load_email_config_from_env


def _write_report(report_dir: Path, results: list[dict] | None = None, summary: str | None = None) -> None:
    report_dir.mkdir(parents=True)
    (report_dir / "summary.txt").write_text(
        summary if summary is not None else "CGI Polska S.A. - KRS: 0000307263 - zmiany: TAK: 1 roznica.\n",
        encoding="utf-8",
    )
    (report_dir / "report.json").write_text(
        json.dumps(
            {
                "date": report_dir.name,
                "results": results if results is not None else [
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
    assert body.index("Changed values:") < body.index("Summary:")
    assert "Attached reports:" not in body
    assert "report.md" not in body
    assert "comparison.csv" not in body
    assert not list(message.iter_attachments())


@pytest.mark.parametrize(
    ("successful_results", "expected_status"),
    [
        ([], "monitoring failed"),
        ([{"status": "ok", "diff": {"differences": []}}], "partial failure"),
        (
            [{"status": "ok", "diff": {"differences": [{"path": "name", "before": "Old", "after": "New"}]}}],
            "partial failure; changes detected",
        ),
    ],
)
def test_failed_reports_are_not_described_as_no_changes(
    tmp_path: Path, successful_results: list[dict], expected_status: str
) -> None:
    report_dir = tmp_path / "2026-09-17"
    _write_report(
        report_dir,
        results=[*successful_results, {"name": "CGI Polska S.A.", "krs": "0000307263", "status": "error", "error": "PRS timeout"}],
        summary="CGI Polska S.A. - ERROR: PRS timeout\n",
    )
    config = notifications.EmailConfig("smtp.example.com", 587, "monitor@example.com", ["owner@example.com"])

    message = build_email_message(config, report_dir)
    body = message.get_content()

    assert message["Subject"] == f"[KRS Monitor] 2026-09-17 - {expected_status}"
    assert "no changes" not in message["Subject"]
    assert "PRS timeout" in body
    assert "No changed values were reported." not in body
    assert "Monitoring failed." in body if not successful_results else "Partial failure." in body


@pytest.mark.parametrize("include_markdown", [False, True])
def test_report_attachments_preserve_original_polish_and_bom_bytes(tmp_path: Path, include_markdown: bool) -> None:
    report_dir = tmp_path / "2026-09-17"
    _write_report(report_dir)
    csv_bytes = "old_file_value,new_file_value\n80 UDZIAŁÓW O ŁĄCZNEJ WYSOKOŚCI 50.000 ZŁ,81 UDZIAŁÓW\n".encode("utf-8-sig")
    expected_files = {"comparison.csv": csv_bytes}
    if include_markdown:
        expected_files["report.md"] = "# Zmienione wartości\nŁączna wysokość: 50.000 ZŁ\n".encode("utf-8")
    for filename, content in expected_files.items():
        (report_dir / filename).write_bytes(content)
    config = notifications.EmailConfig("smtp.example.com", 587, "KRS Monitor <monitor@example.com>", ["owner@example.com"])

    message = build_email_message(config, report_dir)
    delivered = BytesParser(policy=policy.default).parsebytes(message.as_bytes())
    attachments = {part.get_filename(): part.get_payload(decode=True) for part in delivered.iter_attachments()}
    body = delivered.get_body(preferencelist=("plain",)).get_content()

    assert attachments == expected_files
    assert attachments["comparison.csv"].startswith(b"\xef\xbb\xbf")
    assert "Attached reports:" in body
    assert "- comparison.csv" in body
    assert ("- report.md" in body) is include_markdown
    assert body.index("Changed values:") < body.index("Summary:")
    assert parsedate_to_datetime(delivered["Date"]).tzinfo is not None
    assert delivered["Message-ID"].endswith("@example.com>")


@pytest.mark.parametrize("use_ssl", [False, True])
@pytest.mark.parametrize("refuse_one_recipient", [False, True])
def test_main_sends_unchanged_weekly_report_over_verified_smtp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    use_ssl: bool,
    refuse_one_recipient: bool,
) -> None:
    report_dir = tmp_path / "2026-09-17"
    _write_report(
        report_dir,
        results=[{"name": "CGI Polska S.A.", "status": "ok", "diff": {"differences": []}}],
        summary="CGI Polska S.A. - zmiany: NIE.\n",
    )
    config = notifications.EmailConfig(
        "smtp.example.com", 465 if use_ssl else 587, "monitor@example.com", ["owner@example.com", "second@example.com"],
        username="monitor@example.com", password="test-token", use_ssl=use_ssl, use_tls=not use_ssl,
    )
    events = []
    sent = []
    contexts = []

    class FakeSMTP:
        def __init__(self, host, port, *, timeout, context=None):
            assert (host, port, timeout) == (config.smtp_host, config.smtp_port, config.timeout_seconds)
            if context is not None:
                contexts.append(context)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            events.append("ehlo")

        def starttls(self, *, context):
            contexts.append(context)
            events.append("starttls")

        def login(self, username, password):
            assert (username, password) == (config.username, config.password)
            events.append("login")

        def send_message(self, message):
            sent.append(message)
            events.append("send")
            return {"second@example.com": (550, b"Mailbox unavailable")} if refuse_one_recipient else {}

    monkeypatch.setattr(notifications, "load_email_config_from_env", lambda: config)
    monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(notifications.smtplib, "SMTP_SSL", FakeSMTP)

    exit_code = notifications.main(["--reports-dir", str(tmp_path), "--report-date", report_dir.name])

    assert exit_code == (1 if refuse_one_recipient else 0)
    assert len(sent) == 1
    assert sent[0]["Subject"] == "[KRS Monitor] 2026-09-17 - no changes"
    assert "No changed values were reported." in sent[0].get_content()
    assert events == (["login", "send"] if use_ssl else ["ehlo", "starttls", "ehlo", "login", "send"])
    assert len(contexts) == 1
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED
    assert contexts[0].check_hostname is True
    if refuse_one_recipient:
        assert "SMTP refused recipient(s): second@example.com" in caplog.text
        assert "no retry was attempted" in caplog.text
        assert "Sent KRS email notification" not in caplog.text
