from krs_monitor.diffing import diff_json


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


def test_diff_includes_comparison_rows_for_changed_and_unchanged_values() -> None:
    diff = diff_json({"a": 1, "b": 2}, {"a": 1, "b": 3})

    assert diff["comparison"] == [
        {"path": "root.a", "status": "no_change", "before": 1, "after": 1},
        {"path": "root.b", "status": "changed", "before": 2, "after": 3},
    ]
