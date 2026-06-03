import csv
import json
from datetime import date

from krs_monitor.config import TRACKED_ENTITIES
from krs_monitor.reporting import generate_reports


def _result(name, krs, differences=None, baseline=False, comparison=None):
    return {
        "name": name,
        "krs": krs,
        "status": "ok",
        "diff": {"changed": bool(differences), "baseline": baseline, "differences": differences or []},
        "comparison": comparison or [],
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
    assert "Szczegółowe porównanie wartości stary/nowy jest zapisane w `comparison.csv`." in markdown
    assert "- root.foo.bar: zmieniono z `A` na `B`" in markdown


def test_report_json_contains_structured_results(tmp_path) -> None:
    results = [_result(TRACKED_ENTITIES[0]["name"], TRACKED_ENTITIES[0]["krs"])]

    paths = generate_reports(results, date(2026, 6, 4), tmp_path)

    data = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert data["date"] == "2026-06-04"
    assert data["results"][0]["diff"]["changed"] is False


def test_report_writes_comparison_csv_with_old_new_and_status_columns(tmp_path) -> None:
    results = [
        _result(
            TRACKED_ENTITIES[0]["name"],
            TRACKED_ENTITIES[0]["krs"],
            comparison=[
                {
                    "path": "root.a",
                    "change_status": "no_change",
                    "old_file_value": "A",
                    "new_file_value": "A",
                },
                {
                    "path": "root.b",
                    "change_status": "changed",
                    "old_file_value": "old",
                    "new_file_value": "new",
                },
            ],
        )
    ]

    paths = generate_reports(results, date(2026, 6, 4), tmp_path)

    with paths["comparison_csv"].open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows == [
        {
            "entity_name": TRACKED_ENTITIES[0]["name"],
            "krs": TRACKED_ENTITIES[0]["krs"],
            "path": "root.a",
            "change_status": "no_change",
            "old_file_value": "A",
            "new_file_value": "A",
        },
        {
            "entity_name": TRACKED_ENTITIES[0]["name"],
            "krs": TRACKED_ENTITIES[0]["krs"],
            "path": "root.b",
            "change_status": "changed",
            "old_file_value": "old",
            "new_file_value": "new",
        },
    ]


def test_report_marks_entity_error(tmp_path) -> None:
    paths = generate_reports(
        [{"name": "CGI Polska S.A.", "krs": "0000307263", "status": "error", "error": "HTTP 500"}],
        date(2026, 6, 4),
        tmp_path,
    )

    assert "BŁĄD: HTTP 500" in paths["markdown"].read_text(encoding="utf-8")
