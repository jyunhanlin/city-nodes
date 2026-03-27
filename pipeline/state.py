from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_STATE_DIR = Path("state")


def read_state(source_name: str, *, state_dir: Path = DEFAULT_STATE_DIR) -> dict:
    """Read check-state metadata for a source. Returns {} on first run."""
    path = state_dir / f"{source_name}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(
    source_name: str, state: dict, *, state_dir: Path = DEFAULT_STATE_DIR
) -> None:
    """Persist check-state metadata for a source."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"{source_name}.json"
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_data(
    source_name: str, *, state_dir: Path = DEFAULT_STATE_DIR
) -> list[dict[str, Any]]:
    """Read previously fetched items for diff comparison. Returns [] on first run."""
    path = state_dir / f"{source_name}_data.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def write_data(
    source_name: str,
    data: list[dict[str, Any]],
    *,
    state_dir: Path = DEFAULT_STATE_DIR,
) -> None:
    """Persist fetched items for future diff comparison."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"{source_name}_data.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
