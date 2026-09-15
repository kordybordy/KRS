"""Email notifications for generated KRS monitoring reports."""

from __future__ import annotations

import argparse
import json
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path
from typing import Any, Mapping, Sequence

from krs_monitor.config import REPORTS_DIR

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    sender: str
    recipients: list[str]
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    use_ssl: bool = False
    timeout_seconds: int = 30
    subject_prefix: str = "KRS Monitor"
    max_details: int = 10


def load_email_config_from_env(env: Mapping[str, str] | None = None) -> EmailConfig | None:
    """Load optional SMTP email settings from environment variables."""

    env = os.environ if env is None else env
    smtp_host = _clean(env.get("KRS_EMAIL_SMTP_HOST"))
    recipients_raw = _clean(env.get("KRS_EMAIL_TO"))

    if not smtp_host and not recipients_raw:
        return None

    username = _clean(env.get("KRS_EMAIL_USERNAME"))
    password = _clean(env.get("KRS_EMAIL_PASSWORD"))
    sender = _clean(env.get("KRS_EMAIL_FROM")) or username

    missing = []
    if not smtp_host:
        missing.append("KRS_EMAIL_SMTP_HOST")
    if not sender:
        missing.append("KRS_EMAIL_FROM")
    if not recipients_raw:
        missing.append("KRS_EMAIL_TO")
    if username and not password:
        missing.append("KRS_EMAIL_PASSWORD")
    if password and not username:
        missing.append("KRS_EMAIL_USERNAME")
    if missing:
        raise ValueError(f"Missing email notification setting(s): {', '.join(missing)}")

    recipients = _split_recipients(recipients_raw)
    if not recipients:
        raise ValueError("KRS_EMAIL_TO must contain at least one recipient")

    use_ssl = _parse_bool(env.get("KRS_EMAIL_USE_SSL"), default=False)
    use_tls = _parse_bool(env.get("KRS_EMAIL_USE_TLS"), default=not use_ssl)
    if use_ssl and use_tls:
        raise ValueError("KRS_EMAIL_USE_SSL and KRS_EMAIL_USE_TLS cannot both be true")

    return EmailConfig(
        smtp_host=smtp_host,
        smtp_port=_parse_int(env.get("KRS_EMAIL_SMTP_PORT"), default=465 if use_ssl else 587),
        sender=sender,
        recipients=recipients,
        username=username,
        password=password,
        use_tls=use_tls,
        use_ssl=use_ssl,
        timeout_seconds=_parse_int(env.get("KRS_EMAIL_TIMEOUT_SECONDS"), default=30),
        subject_prefix=_clean(env.get("KRS_EMAIL_SUBJECT_PREFIX")) or "KRS Monitor",
        max_details=_parse_int(env.get("KRS_EMAIL_MAX_DETAILS"), default=10, minimum=0),
    )


def find_report_dir(reports_dir: Path, report_date: str | None = None) -> Path:
    """Return the requested report directory, or the latest directory with a summary."""

    if report_date:
        report_dir = reports_dir / report_date
        if not (report_dir / "summary.txt").exists():
            raise FileNotFoundError(f"No summary.txt found for report date {report_date}")
        return report_dir

    report_dirs = sorted(
        path
        for path in reports_dir.iterdir()
        if path.is_dir() and (path / "summary.txt").exists() and (path / "report.json").exists()
    )
    if not report_dirs:
        raise FileNotFoundError(f"No generated KRS reports found in {reports_dir}")
    return report_dirs[-1]


def build_email_message(config: EmailConfig, report_dir: Path) -> EmailMessage:
    """Build a plain-text email with available report files attached unchanged."""

    report_data = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    summary = (report_dir / "summary.txt").read_text(encoding="utf-8").strip()
    report_date = str(report_data.get("date") or report_dir.name)
    attachments = [
        (filename, subtype, (report_dir / filename).read_bytes())
        for filename, subtype in (("report.md", "markdown"), ("comparison.csv", "csv"))
        if (report_dir / filename).is_file()
    ]

    message = EmailMessage()
    message["From"] = config.sender
    message["To"] = ", ".join(config.recipients)
    message["Subject"] = f"[{config.subject_prefix}] {report_date} - {_report_status(report_data)}"
    message["Date"] = formatdate(localtime=True)
    sender_address = parseaddr(config.sender)[1]
    sender_domain = sender_address.rsplit("@", 1)[1] if "@" in sender_address else None
    message["Message-ID"] = make_msgid(domain=sender_domain)
    message.set_content(
        _build_body(report_data, summary, report_dir, config.max_details, [item[0] for item in attachments])
    )
    for filename, subtype, content in attachments:
        message.add_attachment(
            content,
            maintype="text",
            subtype=subtype,
            filename=filename,
            params={"charset": "utf-8"},
            cte="base64",
        )
    return message


def send_email(config: EmailConfig, message: EmailMessage) -> None:
    """Send an email message using SMTP."""

    if config.use_ssl:
        with smtplib.SMTP_SSL(
            config.smtp_host,
            config.smtp_port,
            timeout=config.timeout_seconds,
            context=ssl.create_default_context(),
        ) as server:
            _login_if_configured(server, config)
            _send_to_all_recipients(server, message)
        return

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=config.timeout_seconds) as server:
        if config.use_tls:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        _login_if_configured(server, config)
        _send_to_all_recipients(server, message)


def _send_to_all_recipients(server: smtplib.SMTP, message: EmailMessage) -> None:
    """Fail on partial acceptance without retrying recipients already accepted."""

    refused = server.send_message(message)
    if refused:
        raise RuntimeError(
            f"SMTP refused {len(refused)} recipient(s). "
            "Other recipients may already have received this message; no retry was attempted."
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send a KRS monitor email notification.")
    parser.add_argument("--reports-dir", type=Path, default=REPORTS_DIR)
    parser.add_argument("--report-date", help="Report date directory to send, for example 2026-07-06.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = load_email_config_from_env()
        if config is None:
            logger.info("Email notification is not configured; skipping.")
            return 0

        report_dir = find_report_dir(args.reports_dir, args.report_date)
        message = build_email_message(config, report_dir)
        send_email(config, message)
    except Exception as exc:
        smtp_code = getattr(exc, "smtp_code", None)
        status = f", SMTP status {smtp_code}" if isinstance(smtp_code, int) else ""
        logger.error(
            "Failed to send KRS email notification (%s%s). "
            "Some recipients may already have received this message; no retry was attempted.",
            type(exc).__name__,
            status,
        )
        return 1

    logger.info("Sent KRS email notification to %s recipient(s)", len(config.recipients))
    return 0


def _build_body(
    report_data: dict[str, Any],
    summary: str,
    report_dir: Path,
    max_details: int,
    attachments: Sequence[str] = (),
) -> str:
    lines = [
        f"KRS monitoring result for {report_data.get('date', report_dir.name)}",
        "",
    ]

    results = report_data.get("results", [])
    errors = [result for result in results if result.get("status") == "error"]
    detail_lines = _changed_detail_lines(report_data, max_details)
    if detail_lines:
        lines.extend(["Changed values:", "", *detail_lines, ""])
    elif errors or not results:
        lines.extend(["Changes could not be fully checked.", ""])
    else:
        lines.extend(["No changed values were reported.", ""])

    if not results or len(errors) == len(results):
        lines.extend(["Monitoring failed. No company could be checked successfully.", ""])
    elif errors:
        lines.extend(["Partial failure. Changes may be missing for companies that could not be checked.", ""])
    if errors:
        lines.extend(["Errors:", ""])
        lines.extend(
            f"- {result.get('name', 'Unknown entity')} (KRS {result.get('krs', 'unknown')}): "
            f"{result.get('error', 'Unknown error')}"
            for result in errors
        )
        lines.append("")

    lines.extend(["Summary:", "", summary or "No summary lines were generated.", ""])
    if attachments:
        lines.extend(["Attached reports:", *[f"- {filename}" for filename in attachments], ""])
    return "\n".join(lines)


def _report_status(report_data: dict[str, Any]) -> str:
    results = report_data.get("results", [])
    error_count = sum(result.get("status") == "error" for result in results)
    if not results or error_count == len(results):
        return "monitoring failed"
    if error_count:
        return "partial failure; changes detected" if _has_changes(report_data) else "partial failure"
    return "changes detected" if _has_changes(report_data) else "no changes"


def _changed_detail_lines(report_data: dict[str, Any], max_details: int) -> list[str]:
    lines: list[str] = []
    remaining = max(0, max_details)
    omitted = 0

    for result in report_data.get("results", []):
        differences = result.get("diff", {}).get("differences", [])
        if not differences:
            continue

        if remaining > 0:
            lines.append(f"{result.get('name', 'Unknown entity')} (KRS {result.get('krs', 'unknown')})")
        for difference in differences:
            if remaining <= 0:
                omitted += 1
                continue
            lines.append(_format_difference(difference))
            remaining -= 1

    if omitted:
        lines.append(f"...and {omitted} more changed value(s).")
    return lines


def _format_difference(difference: dict[str, Any]) -> str:
    path = difference.get("path", "unknown path")
    change_type = difference.get("type")
    if change_type == "added":
        return f"- {path}: added {_short_value(difference.get('after'))}"
    if change_type == "removed":
        return f"- {path}: removed {_short_value(difference.get('before'))}"
    return f"- {path}: changed from {_short_value(difference.get('before'))} to {_short_value(difference.get('after'))}"


def _short_value(value: Any, limit: int = 240) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    text = " ".join(text.split())
    if len(text) <= limit:
        return f"`{text}`"
    return f"`{text[: limit - 3]}...`"


def _has_changes(report_data: dict[str, Any]) -> bool:
    return any(result.get("diff", {}).get("differences") for result in report_data.get("results", []))


def _login_if_configured(server: smtplib.SMTP, config: EmailConfig) -> None:
    if config.username and config.password:
        server.login(config.username, config.password)


def _clean(value: str | None) -> str:
    return value.strip() if value else ""


def _split_recipients(value: str) -> list[str]:
    normalized = value.replace(";", ",").replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def _parse_int(value: str | None, default: int, minimum: int = 1) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value: {value}") from exc
    if parsed < minimum:
        raise ValueError(f"Integer value must be at least {minimum}: {value}")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
