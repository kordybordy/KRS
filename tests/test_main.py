from pathlib import Path

from krs_monitor.main import _load_previous_snapshot
from krs_monitor.normalize import write_json


def test_main_exposes_generated_report_date_to_workflow(tmp_path: Path, monkeypatch) -> None:
    from krs_monitor import main as monitor

    reports_dir = tmp_path / "reports"
    output_path = tmp_path / "github-output"
    monkeypatch.setattr(monitor, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(
        monitor,
        "_process_entity",
        lambda name, krs, started_at: {"name": name, "krs": krs, "status": "error", "error": "offline test"},
    )
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    assert monitor.main() == 0
    key, report_date = output_path.read_text(encoding="utf-8").strip().split("=")
    assert key == "report_date"
    assert (reports_dir / report_date / "report.json").is_file()
    assert (reports_dir / report_date / "summary.txt").is_file()


def test_load_previous_snapshot_applies_current_normalization(tmp_path: Path) -> None:
    latest_path = tmp_path / "latest.json"
    write_json(
        latest_path,
        {
            "odpis": {
                "naglowekP": {
                    "dataCzasOdpisu": "06.07.2026 21:46:22",
                    "numerKRS": "0000307263",
                }
            }
        },
    )

    assert _load_previous_snapshot(latest_path) == {
        "odpis": {"naglowekP": {"numerKRS": "0000307263"}}
    }
