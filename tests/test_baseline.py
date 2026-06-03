from datetime import date

from krs_monitor.diffing import diff_json
from krs_monitor.reporting import generate_reports


def test_baseline_diff_has_no_changes() -> None:
    diff = diff_json(None, {"dane": {"nazwa": "CGI"}})

    assert diff == {"changed": False, "baseline": True, "differences": [], "comparison": []}


def test_baseline_report_mentions_initialization(tmp_path) -> None:
    results = [
        {"name": "CGI Polska S.A.", "krs": "0000307263", "status": "ok", "diff": diff_json(None, {"a": 1})}
    ]

    paths = generate_reports(results, date(2026, 6, 4), tmp_path)

    content = paths["markdown"].read_text(encoding="utf-8")
    assert "zmiany: NIE. Inicjalizacja baseline." in content
