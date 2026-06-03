"""Compute JSON diffs between KRS snapshots."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

ChangeType = Literal["added", "removed", "changed"]
ComparisonStatus = Literal["added", "removed", "changed", "no_change"]


class Difference(TypedDict):
    path: str
    type: ChangeType
    before: Any
    after: Any


class ComparisonRow(TypedDict):
    path: str
    status: ComparisonStatus
    before: Any
    after: Any


class DiffResult(TypedDict):
    changed: bool
    baseline: bool
    differences: list[Difference]
    comparison: list[ComparisonRow]


_MISSING = object()


def diff_json(previous: dict[str, Any] | None, current: dict[str, Any]) -> DiffResult:
    """Diff previous and current JSON snapshots."""

    if previous is None:
        return {"changed": False, "baseline": True, "differences": [], "comparison": []}

    differences: list[Difference] = []
    comparison: list[ComparisonRow] = []
    _diff_values(previous, current, "root", differences, comparison)
    return {
        "changed": bool(differences),
        "baseline": False,
        "differences": differences,
        "comparison": comparison,
    }


def _diff_values(
    before: Any,
    after: Any,
    path: str,
    differences: list[Difference],
    comparison: list[ComparisonRow],
) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            child_path = f"{path}.{key}"
            before_value = before.get(key, _MISSING)
            after_value = after.get(key, _MISSING)
            if before_value is _MISSING:
                differences.append({"path": child_path, "type": "added", "before": None, "after": after_value})
                comparison.append({"path": child_path, "status": "added", "before": None, "after": after_value})
            elif after_value is _MISSING:
                differences.append({"path": child_path, "type": "removed", "before": before_value, "after": None})
                comparison.append({"path": child_path, "status": "removed", "before": before_value, "after": None})
            else:
                _diff_values(before_value, after_value, child_path, differences, comparison)
        return

    if isinstance(before, list) and isinstance(after, list):
        max_len = max(len(before), len(after))
        for index in range(max_len):
            child_path = f"{path}[{index}]"
            if index >= len(before):
                differences.append({"path": child_path, "type": "added", "before": None, "after": after[index]})
                comparison.append({"path": child_path, "status": "added", "before": None, "after": after[index]})
            elif index >= len(after):
                differences.append({"path": child_path, "type": "removed", "before": before[index], "after": None})
                comparison.append({"path": child_path, "status": "removed", "before": before[index], "after": None})
            else:
                _diff_values(before[index], after[index], child_path, differences, comparison)
        return

    if before != after:
        differences.append({"path": path, "type": "changed", "before": before, "after": after})
        comparison.append({"path": path, "status": "changed", "before": before, "after": after})
        return

    comparison.append({"path": path, "status": "no_change", "before": before, "after": after})
