from pathlib import Path

from krs_monitor.main import _load_previous_snapshot
from krs_monitor.normalize import write_json


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
