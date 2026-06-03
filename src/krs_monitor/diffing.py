"""Compute JSON diffs between KRS snapshots."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

ChangeType = Literal["added", "removed", "changed"]


class Difference(TypedDict):
    path: str
    type: ChangeType
    before: Any
    after: Any


class DiffResult(TypedDict):
    changed: bool
    baseline: bool
    differences: list[Difference]


_MISSING = object()


def diff_json(previous: dict[str, Any] | None, current: dict[str, Any]) -> DiffResult:
    """Diff previous and current JSON snapshots."""

    if previous is None:
        return {"changed": False, "baseline": True, "differences": []}

    differences: list[Difference] = []
    _diff_values(previous, current, "root", differences)
    return {"changed": bool(differences), "baseline": False, "differences": differences}


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
