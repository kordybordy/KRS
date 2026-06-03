"""Compute JSON diffs between KRS snapshots."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

ChangeType = Literal["added", "removed", "changed"]
ComparisonStatus = Literal["added", "removed", "changed", "no_change", "baseline"]


class Difference(TypedDict):
    path: str
    type: ChangeType
    before: Any
    after: Any


class DiffResult(TypedDict):
    changed: bool
    baseline: bool
    differences: list[Difference]


class ComparisonRow(TypedDict):
    path: str
    change_status: ComparisonStatus
    old_file_value: Any
    new_file_value: Any


_MISSING = object()
MISSING_DISPLAY = "<missing>"


def diff_json(previous: dict[str, Any] | None, current: dict[str, Any]) -> DiffResult:
    """Diff previous and current JSON snapshots."""

    if previous is None:
        return {"changed": False, "baseline": True, "differences": []}

    differences: list[Difference] = []
    _diff_values(previous, current, "root", differences)
    return {"changed": bool(differences), "baseline": False, "differences": differences}


def compare_json(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[ComparisonRow]:
    """Return a row-by-row comparison, including unchanged leaf values."""

    rows: list[ComparisonRow] = []
    if previous is None:
        _collect_subtree_rows(_MISSING, current, "root", "baseline", rows)
        return rows

    _compare_values(previous, current, "root", rows)
    return rows


def _diff_values(before: Any, after: Any, path: str, differences: list[Difference]) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            child_path = f"{path}.{key}"
            before_value = before.get(key, _MISSING)
            after_value = after.get(key, _MISSING)
            if before_value is _MISSING:
                differences.append({"path": child_path, "type": "added", "before": None, "after": after_value})
            elif after_value is _MISSING:
                differences.append({"path": child_path, "type": "removed", "before": before_value, "after": None})
            else:
                _diff_values(before_value, after_value, child_path, differences)
        return

    if isinstance(before, list) and isinstance(after, list):
        max_len = max(len(before), len(after))
        for index in range(max_len):
            child_path = f"{path}[{index}]"
            if index >= len(before):
                differences.append({"path": child_path, "type": "added", "before": None, "after": after[index]})
            elif index >= len(after):
                differences.append({"path": child_path, "type": "removed", "before": before[index], "after": None})
            else:
                _diff_values(before[index], after[index], child_path, differences)
        return

    if before != after:
        differences.append({"path": path, "type": "changed", "before": before, "after": after})


def _compare_values(before: Any, after: Any, path: str, rows: list[ComparisonRow]) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        if not before and not after:
            rows.append({"path": path, "change_status": "no_change", "old_file_value": before, "new_file_value": after})
            return
        for key in sorted(before.keys() | after.keys()):
            child_path = f"{path}.{key}"
            before_value = before.get(key, _MISSING)
            after_value = after.get(key, _MISSING)
            if before_value is _MISSING:
                _collect_subtree_rows(_MISSING, after_value, child_path, "added", rows)
            elif after_value is _MISSING:
                _collect_subtree_rows(before_value, _MISSING, child_path, "removed", rows)
            else:
                _compare_values(before_value, after_value, child_path, rows)
        return

    if isinstance(before, list) and isinstance(after, list):
        if not before and not after:
            rows.append({"path": path, "change_status": "no_change", "old_file_value": before, "new_file_value": after})
            return
        max_len = max(len(before), len(after))
        for index in range(max_len):
            child_path = f"{path}[{index}]"
            if index >= len(before):
                _collect_subtree_rows(_MISSING, after[index], child_path, "added", rows)
            elif index >= len(after):
                _collect_subtree_rows(before[index], _MISSING, child_path, "removed", rows)
            else:
                _compare_values(before[index], after[index], child_path, rows)
        return

    status: ComparisonStatus = "no_change" if before == after else "changed"
    rows.append({"path": path, "change_status": status, "old_file_value": before, "new_file_value": after})


def _collect_subtree_rows(
    before: Any,
    after: Any,
    path: str,
    status: Literal["added", "removed", "baseline"],
    rows: list[ComparisonRow],
) -> None:
    value = after if before is _MISSING else before
    if isinstance(value, dict):
        if not value:
            rows.append(
                {
                    "path": path,
                    "change_status": status,
                    "old_file_value": MISSING_DISPLAY if before is _MISSING else before,
                    "new_file_value": MISSING_DISPLAY if after is _MISSING else after,
                }
            )
            return
        for key in sorted(value):
            child_path = f"{path}.{key}"
            if before is _MISSING:
                _collect_subtree_rows(_MISSING, value[key], child_path, status, rows)
            else:
                _collect_subtree_rows(value[key], _MISSING, child_path, status, rows)
        return

    if isinstance(value, list):
        if not value:
            rows.append(
                {
                    "path": path,
                    "change_status": status,
                    "old_file_value": MISSING_DISPLAY if before is _MISSING else before,
                    "new_file_value": MISSING_DISPLAY if after is _MISSING else after,
                }
            )
            return
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]"
            if before is _MISSING:
                _collect_subtree_rows(_MISSING, item, child_path, status, rows)
            else:
                _collect_subtree_rows(item, _MISSING, child_path, status, rows)
        return

    rows.append(
        {
            "path": path,
            "change_status": status,
            "old_file_value": MISSING_DISPLAY if before is _MISSING else before,
            "new_file_value": MISSING_DISPLAY if after is _MISSING else after,
        }
    )
