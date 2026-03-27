from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DiffResult:
    added: int
    removed: int
    changed: int
    summary: str

    @property
    def has_changes(self) -> bool:
        return self.added > 0 or self.removed > 0 or self.changed > 0


def compute_diff(
    old_data: list[dict[str, Any]], new_data: list[dict[str, Any]]
) -> DiffResult:
    """Compare old and new items keyed by (lat, lng, name) to avoid silent drops at duplicate coordinates."""
    old_by_key = {(item["lat"], item["lng"], item["name"]): item for item in old_data}
    new_by_key = {(item["lat"], item["lng"], item["name"]): item for item in new_data}

    old_keys = set(old_by_key)
    new_keys = set(new_by_key)

    added = len(new_keys - old_keys)
    removed = len(old_keys - new_keys)

    changed = 0
    for key in old_keys & new_keys:
        if old_by_key[key] != new_by_key[key]:
            changed += 1

    parts: list[str] = []
    if added:
        parts.append(f"新增 {added} 筆")
    if removed:
        parts.append(f"刪除 {removed} 筆")
    if changed:
        parts.append(f"變更 {changed} 筆")

    return DiffResult(
        added=added,
        removed=removed,
        changed=changed,
        summary="、".join(parts) if parts else "無變更",
    )
