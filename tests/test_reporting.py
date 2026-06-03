import csv
import json
from datetime import date

from krs_monitor.config import TRACKED_ENTITIES
from krs_monitor.reporting import generate_reports


def _result(name, krs, differences=None, baseline=False):
    return {
        "name": name,
        "krs": krs,
        "status": "ok",
        "diff": {"changed": bool(differences), "baseline": baseline, "differences": differences or []},
    }


def test_report_contains_yes_no_summary_and_details(tmp_path) -> None:
    results = [
        _result(
            TRACKED_ENTITIES[0]["name"],
            TRACKED_ENTITIES[0]["krs"],
            [{"path": "root.foo.bar", "type": "changed", "before": "A", "after": "B"}],
        ),
        _result(TRACKED_ENTITIES[1]["name"], TRACKED_ENTITIES[1]["krs"]),
    ]

    paths = generate_reports(results, date(2026, 6, 4), tmp_path)
    markdown = paths["markdown"].read_text(encoding="utf-8")

    assert "CGI Information Systems and Management Consultants (Polska) Sp. z o.o. - KRS: 0000078664 – zmiany: TAK: 1 różnica." in markdown
    assert "CGI Polska S.A. - KRS: 0000307263 – zmiany: NIE." in markdown
    assert "## Zmienione wartości" in markdown
    assert "- root.foo.bar: zmieniono z `A` na `B`" in markdown
    assert markdown.index("## Zmienione wartości") < markdown.index("## Szczegóły zmian")
    assert "Pełna tabela porównania wartości starego i nowego pliku znajduje się w `comparison.csv`." in markdown


def test_report_json_contains_structured_results(tmp_path) -> None:
    results = [_result(TRACKED_ENTITIES[0]["name"], TRACKED_ENTITIES[0]["krs"])]

    paths = generate_reports(results, date(2026, 6, 4), tmp_path)

    data = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert data["date"] == "2026-06-04"
    assert data["results"][0]["diff"]["changed"] is False


def test_report_marks_entity_error(tmp_path) -> None:
    paths = generate_reports(
        [{"name": "CGI Polska S.A.", "krs": "0000307263", "status": "error", "error": "HTTP 500"}],
        date(2026, 6, 4),
        tmp_path,
    )

    assert "BŁĄD: HTTP 500" in paths["markdown"].read_text(encoding="utf-8")


def test_report_writes_comparison_csv(tmp_path) -> None:
    results = [
        _result(
            "CGI Polska S.A.",
            "0000307263",
            [{"path": "root.a", "type": "changed", "before": "old", "after": "new"}],
        )
    ]
    results[0]["diff"]["comparison"] = [
        {"path": "root.b", "status": "no_change", "before": 2, "after": 2},
        {"path": "root.a", "status": "changed", "before": "old", "after": "new"},
    ]

    paths = generate_reports(results, date(2026, 6, 4), tmp_path)

    assert paths["comparison_csv"].read_bytes().startswith(b"\xef\xbb\xbf")

    with paths["comparison_csv"].open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows == [
        {
            "entity_name": "CGI Polska S.A.",
            "krs": "0000307263",
            "path": "root.a",
            "status": "changed",
            "old_file_value": "old",
            "new_file_value": "new",
        },
        {
            "entity_name": "CGI Polska S.A.",
            "krs": "0000307263",
            "path": "root.b",
            "status": "no_change",
            "old_file_value": "2",
            "new_file_value": "2",
        },
    ]
