from krs_monitor.diffing import compare_json, diff_json


def test_diff_detects_changed_value() -> None:
    diff = diff_json({"dane": {"siedziba": "Warszawa"}}, {"dane": {"siedziba": "Kraków"}})

    assert diff["changed"] is True
    assert diff["differences"] == [
        {"path": "root.dane.siedziba", "type": "changed", "before": "Warszawa", "after": "Kraków"}
    ]


def test_diff_detects_added_field() -> None:
    diff = diff_json({"a": 1}, {"a": 1, "b": 2})

    assert diff["differences"] == [{"path": "root.b", "type": "added", "before": None, "after": 2}]


def test_diff_detects_removed_field() -> None:
    diff = diff_json({"a": 1, "b": 2}, {"a": 1})

    assert diff["differences"] == [{"path": "root.b", "type": "removed", "before": 2, "after": None}]


def test_diff_no_changes() -> None:
    diff = diff_json({"a": [1, 2]}, {"a": [1, 2]})

    assert diff["changed"] is False
    assert diff["baseline"] is False
    assert diff["differences"] == []


def test_compare_json_includes_changed_and_unchanged_values() -> None:
    rows = compare_json({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4})

    assert rows == [
        {"path": "root.a", "change_status": "no_change", "old_file_value": 1, "new_file_value": 1},
        {"path": "root.b", "change_status": "changed", "old_file_value": 2, "new_file_value": 3},
        {"path": "root.c", "change_status": "added", "old_file_value": "<missing>", "new_file_value": 4},
    ]


def test_compare_json_baseline_marks_old_values_missing() -> None:
    rows = compare_json(None, {"a": {"b": "CGI"}})

    assert rows == [
        {
            "path": "root.a.b",
            "change_status": "baseline",
            "old_file_value": "<missing>",
            "new_file_value": "CGI",
        }
    ]
