"""Generate Markdown, JSON, and summary reports for KRS monitoring runs."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any, TypedDict

from krs_monitor.normalize import write_json


class EntityRunResult(TypedDict, total=False):
    name: str
    krs: str
    status: str
    error: str
    diff: dict[str, Any]
    archive_path: str
    latest_path: str
    comparison: list[dict[str, Any]]


class ReportPaths(TypedDict):
    report_dir: Path
    markdown: Path
    json: Path
    summary: Path
    comparison_csv: Path


def generate_reports(results: list[EntityRunResult], report_date: date, reports_dir: Path) -> ReportPaths:
    """Write Markdown, JSON, summary, and comparison CSV reports for one monitoring run."""

    report_dir = reports_dir / report_date.isoformat()
    report_dir.mkdir(parents=True, exist_ok=True)

    report_data = {"date": report_date.isoformat(), "results": results}
    markdown = _render_markdown(report_data)
    summary = _render_summary(results)

    markdown_path = report_dir / "report.md"
    json_path = report_dir / "report.json"
    summary_path = report_dir / "summary.txt"
    comparison_csv_path = report_dir / "comparison.csv"

    markdown_path.write_text(markdown, encoding="utf-8")
    write_json(json_path, report_data)
    summary_path.write_text(summary, encoding="utf-8")
    _write_comparison_csv(comparison_csv_path, results)

    return {
        "report_dir": report_dir,
        "markdown": markdown_path,
        "json": json_path,
        "summary": summary_path,
        "comparison_csv": comparison_csv_path,
    }


def _render_markdown(report_data: dict[str, Any]) -> str:
    results: list[EntityRunResult] = report_data["results"]
    lines = [f"# Raport monitoringu KRS - {report_data['date']}", "", "## Podsumowanie", ""]
    lines.extend(_summary_line(result) for result in results)
    lines.extend(["", "## Pełna tabela porównania", "", "Szczegółowe porównanie wartości stary/nowy jest zapisane w `comparison.csv`.", "", "## Szczegóły zmian", ""])

    for result in results:
        lines.extend([f"### {result['name']} - KRS: {result['krs']}", ""])
        if result.get("status") == "error":
            lines.extend([f"- BŁĄD: {result.get('error', 'Nieznany błąd')}", ""])
            continue

        diff = result.get("diff", {})
        if diff.get("baseline"):
            lines.extend(["- Inicjalizacja baseline - zapisano pierwszy snapshot do porównań.", ""])
            continue
        differences = diff.get("differences", [])
        if not differences:
            lines.extend(["- Brak zmian.", ""])
            continue
        for difference in differences:
            lines.append(_format_difference(difference))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_summary(results: list[EntityRunResult]) -> str:
    return "\n".join(_summary_line(result) for result in results) + "\n"


def _summary_line(result: EntityRunResult) -> str:
    prefix = f"{result['name']} - KRS: {result['krs']} –"
    if result.get("status") == "error":
        return f"{prefix} zmiany: NIE. BŁĄD: {result.get('error', 'Nieznany błąd')}"

    diff = result.get("diff", {})
    if diff.get("baseline"):
        return f"{prefix} zmiany: NIE. Inicjalizacja baseline."
    count = len(diff.get("differences", []))
    if count:
        noun = "różnica" if count == 1 else "różnice" if 2 <= count <= 4 else "różnic"
        return f"{prefix} zmiany: TAK: {count} {noun}."
    return f"{prefix} zmiany: NIE."


def _format_difference(difference: dict[str, Any]) -> str:
    path = difference["path"]
    change_type = difference["type"]
    if change_type == "added":
        return f"- {path}: dodano `{_format_value(difference.get('after'))}`"
    if change_type == "removed":
        return f"- {path}: usunięto `{_format_value(difference.get('before'))}`"
    return f"- {path}: zmieniono z `{_format_value(difference.get('before'))}` na `{_format_value(difference.get('after'))}`"


def _write_comparison_csv(path: Path, results: list[EntityRunResult]) -> None:
    fieldnames = ["entity_name", "krs", "path", "change_status", "old_file_value", "new_file_value"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            if result.get("status") == "error":
                writer.writerow(
                    {
                        "entity_name": result["name"],
                        "krs": result["krs"],
                        "path": "root",
                        "change_status": "error",
                        "old_file_value": "",
                        "new_file_value": result.get("error", "Nieznany błąd"),
                    }
                )
                continue
            for row in result.get("comparison", []):
                writer.writerow(
                    {
                        "entity_name": result["name"],
                        "krs": result["krs"],
                        "path": row["path"],
                        "change_status": row["change_status"],
                        "old_file_value": _format_csv_value(row.get("old_file_value")),
                        "new_file_value": _format_csv_value(row.get("new_file_value")),
                    }
                )


def _format_csv_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _format_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
