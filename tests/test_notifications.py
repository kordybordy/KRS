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
    assert "Ostatni raport ze zmianami: 2026-07-06" in body
    assert "comparison.csv" not in body
    assert not list(message.iter_attachments())


def test_email_references_latest_real_change_before_current_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_report(tmp_path / "2026-08-20")
    _write_report(tmp_path / "2026-08-27")
    _write_report(
        tmp_path / "2026-09-03",
        results=[{"status": "ok", "diff": {"baseline": True, "differences": [{"path": "initial"}]}}],
    )
    _write_report(
        tmp_path / "2026-09-10",
        results=[{"status": "error", "diff": {"differences": [{"path": "unreliable"}]}}],
    )
    report_dir = tmp_path / "2026-09-15"
    _write_report(report_dir, results=[{"status": "ok", "diff": {"differences": []}}])
    _write_report(tmp_path / "2026-09-24")
    monkeypatch.setenv("GITHUB_REPOSITORY", "kordybordy/KRS")
    monkeypatch.delenv("GITHUB_SERVER_URL", raising=False)
    config = notifications.EmailConfig("smtp.example.com", 587, "monitor@example.com", ["owner@example.com"])

    body = build_email_message(config, report_dir).get_content()

    assert "Ostatni raport ze zmianami: 2026-08-27" in body
    assert "Raport: https://github.com/kordybordy/KRS/blob/main/reports/2026-08-27/report.md" in body
    assert "2026-09-24" not in body
    assert body.index("No changed values were reported.") < body.index("Ostatni raport ze zmianami:")
    assert body.index("Ostatni raport ze zmianami:") < body.index("Summary:")


def test_current_changed_report_is_the_latest_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_report(tmp_path / "2026-08-27")
    report_dir = tmp_path / "2026-09-15"
    _write_report(report_dir)
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.example.com/")
    monkeypatch.setenv("GITHUB_REPOSITORY", "team/KRS")
    config = notifications.EmailConfig("smtp.example.com", 587, "monitor@example.com", ["owner@example.com"])

    body = build_email_message(config, report_dir).get_content()

    assert "Ostatni raport ze zmianami: 2026-09-15" in body
    assert "https://github.example.com/team/KRS/blob/main/reports/2026-09-15/report.md" in body
    assert "2026-08-27" not in body
    assert body.index("Changed values:") < body.index("Ostatni raport ze zmianami:")


def test_local_email_reference_uses_relative_report_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report_dir = tmp_path / "2026-09-15"
    _write_report(report_dir)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    config = notifications.EmailConfig("smtp.example.com", 587, "monitor@example.com", ["owner@example.com"])

    body = build_email_message(config, report_dir).get_content()

    assert "Raport: reports/2026-09-15/report.md" in body
    assert str(tmp_path) not in body


@pytest.mark.parametrize("baseline", [False, True])
def test_email_states_when_history_has_no_report_with_real_changes(tmp_path: Path, baseline: bool) -> None:
    report_dir = tmp_path / "2026-09-15"
    _write_report(
        report_dir,
        results=[{"status": "ok", "diff": {"baseline": baseline, "differences": [{"path": "initial"}] if baseline else []}}],
    )
    config = notifications.EmailConfig("smtp.example.com", 587, "monitor@example.com", ["owner@example.com"])

    message = build_email_message(config, report_dir)
    body = message.get_content()

    assert "Ostatni raport ze zmianami: nie znaleziono w dostępnej historii." in body
    assert "Changed values:" not in body
    assert message["Subject"].endswith("no changes")


@pytest.mark.parametrize(
    "historical_contents",
    [
        "not-json-private-content",
        "[]",
        '{"date": "2026-09-10", "results": null}',
        '{"date": "2099-01-01", "results": []}',
        '{"date": "2026-09-10", "results": [{"status": "ok", "diff": {"differences": "invalid"}}]}',
    ],
)
def test_malformed_history_qualifies_last_known_change_without_blocking_email(
    tmp_path: Path, historical_contents: str, caplog: pytest.LogCaptureFixture
) -> None:
    _write_report(tmp_path / "2026-08-27")
    malformed_dir = tmp_path / "2026-09-10"
    _write_report(malformed_dir)
    (malformed_dir / "report.json").write_text(historical_contents, encoding="utf-8")
    report_dir = tmp_path / "2026-09-15"
    _write_report(report_dir, results=[{"status": "ok", "diff": {"differences": []}}])
    config = notifications.EmailConfig("smtp.example.com", 587, "monitor@example.com", ["owner@example.com"])

    body = build_email_message(config, report_dir).get_content()

    assert "Ostatni raport ze zmianami: nie można potwierdzić" in body
    assert "Ostatni potwierdzony raport ze zmianami: 2026-08-27" in body
    assert "reports/2026-08-27/report.md" in body
    assert "reports/2026-09-10/report.json" in caplog.text
    assert "not-json-private-content" not in caplog.text
    assert str(tmp_path) not in caplog.text


def test_unreadable_history_does_not_claim_there_were_no_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    historical_dir = tmp_path / "2026-09-10"
    _write_report(historical_dir)
    report_dir = tmp_path / "2026-09-15"
    _write_report(report_dir, results=[{"status": "ok", "diff": {"differences": []}}])
    original_read_text = Path.read_text

    def read_text(path: Path, *args, **kwargs):
        if path == historical_dir / "report.json":
            raise PermissionError("private filesystem detail")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    config = notifications.EmailConfig("smtp.example.com", 587, "monitor@example.com", ["owner@example.com"])

    body = build_email_message(config, report_dir).get_content()

    assert "Ostatni raport ze zmianami: nie można potwierdzić" in body
    assert "nie znaleziono" not in body
    assert "PermissionError" in caplog.text
    assert "private filesystem detail" not in caplog.text


def test_unreadable_history_older_than_last_change_does_not_make_reference_uncertain(tmp_path: Path) -> None:
    (tmp_path / "2026-08-20").mkdir()
    _write_report(tmp_path / "2026-08-27")
    report_dir = tmp_path / "2026-09-15"
    _write_report(report_dir, results=[{"status": "ok", "diff": {"differences": []}}])
    config = notifications.EmailConfig("smtp.example.com", 587, "monitor@example.com", ["owner@example.com"])

    body = build_email_message(config, report_dir).get_content()

    assert "Ostatni raport ze zmianami: 2026-08-27" in body
    assert "nie można potwierdzić" not in body


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
@pytest.mark.parametrize("refusal_mode", ["none", "one", "all"])
def test_main_sends_unchanged_weekly_report_over_verified_smtp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    use_ssl: bool,
    refusal_mode: str,
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
            if refusal_mode == "all":
                raise notifications.smtplib.SMTPRecipientsRefused(
                    {recipient: (550, b"Mailbox unavailable") for recipient in config.recipients}
                )
            return {"second@example.com": (550, b"Mailbox unavailable")} if refusal_mode == "one" else {}

    monkeypatch.setattr(notifications, "load_email_config_from_env", lambda: config)
    monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(notifications.smtplib, "SMTP_SSL", FakeSMTP)

    exit_code = notifications.main(["--reports-dir", str(tmp_path), "--report-date", report_dir.name])

    assert exit_code == (0 if refusal_mode == "none" else 1)
    assert len(sent) == 1
    assert sent[0]["Subject"] == "[KRS Monitor] 2026-09-17 - no changes"
    assert "No changed values were reported." in sent[0].get_content()
    assert events == (["login", "send"] if use_ssl else ["ehlo", "starttls", "ehlo", "login", "send"])
    assert len(contexts) == 1
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED
    assert contexts[0].check_hostname is True
    for recipient in config.recipients:
        assert recipient not in caplog.text
    if refusal_mode != "none":
        assert "Failed to send KRS email notification" in caplog.text
        assert "no retry was attempted" in caplog.text
        assert "Sent KRS email notification" not in caplog.text
