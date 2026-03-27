# City Nodes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an automated pipeline that fetches Taipei trash bin locations from government open data, updates a Google Sheet, and notifies the user to reimport into Google My Maps.

**Architecture:** Strategy Pattern — each data source implements `check()` + `fetch()` with a shared pipeline for diffing, Sheet updates, and GitHub Issue notifications. Sources run in parallel via `asyncio.gather`. State is tracked in git for persistence across GitHub Actions runs.

**Tech Stack:** Python 3.12, uv, httpx (async HTTP), gspread (Google Sheets), pydantic-settings (env config), pyyaml (config file), pytest + pytest-asyncio + respx (testing)

**Spec:** `docs/superpowers/specs/2026-03-27-city-nodes-design.md`

---

## File Structure

```
city-nodes/
├── sources/
│   ├── __init__.py              # empty
│   ├── base.py                  # DataSource Protocol, SourceItem TypedDict
│   └── trash_bins.py            # TrashBinSource (check + fetch for government CSV)
├── pipeline/
│   ├── __init__.py              # empty
│   ├── state.py                 # read/write state JSON + cached data
│   ├── diff.py                  # DiffResult dataclass, compute_diff()
│   ├── sheet.py                 # get_gspread_client(), update_sheet()
│   └── notify.py                # notify_update() via GitHub Issues API
├── tests/
│   ├── __init__.py              # empty
│   ├── conftest.py              # shared fixtures (sample SourceItems, tmp state dir)
│   ├── test_state.py            # state read/write tests
│   ├── test_diff.py             # diff logic tests
│   ├── test_trash_bins.py       # CSV parsing + check/fetch tests
│   ├── test_sheet.py            # sheet update with mocked gspread
│   └── test_notify.py           # notification with mocked httpx
├── state/
│   └── .gitkeep                 # keep empty dir in git
├── settings.py                  # pydantic Settings class
├── main.py                      # async orchestrator entry point
├── config.yaml                  # source configuration
├── pyproject.toml               # project metadata + dependencies
├── .python-version              # pins Python 3.12
├── .gitignore
├── .env.example                 # template for local env vars
└── .github/
    └── workflows/
        └── update.yml           # cron + manual trigger workflow
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `config.yaml`
- Create: `sources/__init__.py`
- Create: `pipeline/__init__.py`
- Create: `tests/__init__.py`
- Create: `state/.gitkeep`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "city-nodes"
version = "0.1.0"
description = "Automated city data pipeline for Google My Maps"
requires-python = ">=3.12"
dependencies = [
    "gspread>=6.0.0",
    "httpx>=0.27.0",
    "pydantic-settings>=2.0.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "respx>=0.22.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Create .python-version**

```
3.12
```

- [ ] **Step 3: Create .gitignore**

```
.env
__pycache__/
.venv/
*.pyc
.pytest_cache/
```

- [ ] **Step 4: Create .env.example**

```
GOOGLE_SERVICE_ACCOUNT_KEY={"type":"service_account","project_id":"..."}
GITHUB_TOKEN=
GITHUB_REPOSITORY=owner/repo
```

- [ ] **Step 5: Create config.yaml**

```yaml
sources:
  trash_bins:
    enabled: true
    sheet_id: "your-google-sheet-id"
    sheet_name: "工作表1"
```

- [ ] **Step 6: Create empty __init__.py files and state/.gitkeep**

Create empty files:
- `sources/__init__.py`
- `pipeline/__init__.py`
- `tests/__init__.py`
- `tests/conftest.py` (empty for now)
- `state/.gitkeep`

- [ ] **Step 7: Verify uv sync**

Run: `uv sync --all-extras`
Expected: Dependencies install successfully, `.venv/` created.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .python-version .gitignore .env.example config.yaml \
  sources/__init__.py pipeline/__init__.py tests/__init__.py tests/conftest.py \
  state/.gitkeep uv.lock
git commit -m "chore: project scaffolding with uv"
```

---

### Task 2: Settings Module

**Files:**
- Create: `settings.py`
- Create: `tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings.py
import pytest
from pydantic import ValidationError


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_KEY", '{"type":"test"}')
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("GITHUB_REPOSITORY", "user/repo")

    from settings import Settings

    s = Settings()
    assert s.google_service_account_key == '{"type":"test"}'
    assert s.github_token == "ghp_test"
    assert s.github_repository == "user/repo"


def test_settings_optional_fields_have_defaults(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_KEY", '{"type":"test"}')

    from settings import Settings

    s = Settings()
    assert s.github_token == ""
    assert s.github_repository == ""


def test_settings_fails_without_required_key():
    import os

    # Ensure the env var is not set
    os.environ.pop("GOOGLE_SERVICE_ACCOUNT_KEY", None)

    from settings import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'settings'`

- [ ] **Step 3: Write minimal implementation**

```python
# settings.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_service_account_key: str
    github_token: str = ""
    github_repository: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_settings.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add settings.py tests/test_settings.py
git commit -m "feat: add Settings module with pydantic-settings"
```

---

### Task 3: DataSource Protocol and SourceItem

**Files:**
- Create: `sources/base.py`

No tests needed — these are type-only definitions.

- [ ] **Step 1: Create type definitions**

```python
# sources/base.py
from __future__ import annotations

from typing import Protocol, TypedDict


class SourceItem(TypedDict):
    """Normalized data item shared across all sources."""

    name: str       # marker label (e.g. "中山南路 外交部")
    address: str    # full address (e.g. "中正區中山南路 外交部")
    lat: float      # latitude
    lng: float      # longitude
    category: str   # e.g. "trash_bin", "toilet"
    note: str       # extra info


class DataSource(Protocol):
    """Interface that every data source must implement."""

    name: str

    async def check(self, state: dict) -> bool:
        """Lightweight probe. Return True if the source has new data.

        Args:
            state: Previously saved state dict (empty on first run).
        """
        ...

    async def fetch(self) -> tuple[list[SourceItem], dict]:
        """Download and normalize data.

        Returns:
            A tuple of (items, new_state) where new_state will be persisted
            for the next check() call.
        """
        ...
```

Note: the Protocol is refined from the spec — `check()` receives the previous state as a parameter (so sources don't read state files themselves), and `fetch()` returns `(items, new_state)` so the pipeline can save state after all steps succeed.

- [ ] **Step 2: Verify import works**

Run: `uv run python -c "from sources.base import SourceItem, DataSource; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add sources/base.py
git commit -m "feat: add DataSource Protocol and SourceItem type"
```

---

### Task 4: State Management

**Files:**
- Create: `pipeline/state.py`
- Create: `tests/test_state.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_state.py
from pathlib import Path

from pipeline.state import read_state, write_state, read_data, write_data


def test_read_state_returns_empty_when_no_file(tmp_path):
    result = read_state("nonexistent", state_dir=tmp_path)
    assert result == {}


def test_write_and_read_state(tmp_path):
    state = {"etag": "abc:123", "data_hash": "sha256..."}
    write_state("trash_bins", state, state_dir=tmp_path)
    result = read_state("trash_bins", state_dir=tmp_path)
    assert result == state


def test_read_data_returns_empty_when_no_file(tmp_path):
    result = read_data("nonexistent", state_dir=tmp_path)
    assert result == []


def test_write_and_read_data(tmp_path):
    items = [
        {
            "name": "外交部",
            "address": "中正區中山南路外交部",
            "lat": 25.0384804,
            "lng": 121.5172055,
            "category": "trash_bin",
            "note": "備註",
        }
    ]
    write_data("trash_bins", items, state_dir=tmp_path)
    result = read_data("trash_bins", state_dir=tmp_path)
    assert result == items


def test_state_preserves_chinese_characters(tmp_path):
    state = {"memo": "測試中文"}
    write_state("test", state, state_dir=tmp_path)
    raw = (tmp_path / "test.json").read_text(encoding="utf-8")
    assert "測試中文" in raw  # not escaped as \u
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.state'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/state.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_state.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/state.py tests/test_state.py
git commit -m "feat: add state management for source check metadata and data"
```

---

### Task 5: Diff Logic

**Files:**
- Create: `pipeline/diff.py`
- Create: `tests/test_diff.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_diff.py
from pipeline.diff import compute_diff, DiffResult


def _item(name: str, lat: float, lng: float, note: str = "") -> dict:
    return {
        "name": name,
        "address": f"區{name}",
        "lat": lat,
        "lng": lng,
        "category": "trash_bin",
        "note": note,
    }


def test_no_changes():
    old = [_item("A", 25.0, 121.0)]
    new = [_item("A", 25.0, 121.0)]
    diff = compute_diff(old, new)
    assert diff.added == 0
    assert diff.removed == 0
    assert diff.changed == 0
    assert diff.has_changes is False
    assert diff.summary == "無變更"


def test_added_items():
    old = [_item("A", 25.0, 121.0)]
    new = [_item("A", 25.0, 121.0), _item("B", 25.1, 121.1)]
    diff = compute_diff(old, new)
    assert diff.added == 1
    assert diff.removed == 0
    assert diff.has_changes is True
    assert "新增 1 筆" in diff.summary


def test_removed_items():
    old = [_item("A", 25.0, 121.0), _item("B", 25.1, 121.1)]
    new = [_item("A", 25.0, 121.0)]
    diff = compute_diff(old, new)
    assert diff.removed == 1
    assert diff.added == 0
    assert "刪除 1 筆" in diff.summary


def test_changed_items():
    old = [_item("A", 25.0, 121.0, note="old")]
    new = [_item("A modified", 25.0, 121.0, note="new")]
    diff = compute_diff(old, new)
    assert diff.changed == 1
    assert diff.added == 0
    assert diff.removed == 0
    assert "變更 1 筆" in diff.summary


def test_mixed_changes():
    old = [_item("A", 25.0, 121.0), _item("B", 25.1, 121.1)]
    new = [_item("A modified", 25.0, 121.0), _item("C", 25.2, 121.2)]
    diff = compute_diff(old, new)
    assert diff.added == 1     # C added
    assert diff.removed == 1   # B removed
    assert diff.changed == 1   # A changed
    assert diff.has_changes is True


def test_empty_old_data():
    new = [_item("A", 25.0, 121.0)]
    diff = compute_diff([], new)
    assert diff.added == 1
    assert diff.has_changes is True


def test_empty_both():
    diff = compute_diff([], [])
    assert diff.has_changes is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_diff.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.diff'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/diff.py
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
    """Compare old and new items keyed by (lat, lng) coordinates."""
    old_by_key = {(item["lat"], item["lng"]): item for item in old_data}
    new_by_key = {(item["lat"], item["lng"]): item for item in new_data}

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_diff.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/diff.py tests/test_diff.py
git commit -m "feat: add diff logic for comparing source data"
```

---

### Task 6: Trash Bin Source

**Files:**
- Create: `sources/trash_bins.py`
- Create: `tests/test_trash_bins.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Create test fixture with sample CSV data**

```python
# tests/conftest.py
import pytest

# Sample CSV matching the real government data format (Big5 encoded).
# Header: 行政區,地址,經度,緯度,備註,
# Note the trailing comma — the real data has it.
SAMPLE_CSV_UTF8 = (
    "行政區,地址,經度,緯度,備註,\n"
    "中正區,中山南路(西側)外交部,121.5172055,25.0384804,嚴禁投入家用垃圾，違者重罰新臺幣6000元,\n"
    "中正區,公園路中央氣象局,121.5150107,25.0380556,嚴禁投入家用垃圾，違者重罰新臺幣6000元,\n"
    "大安區,忠孝東路四段1號,121.5434,25.0418,嚴禁投入家用垃圾，違者重罰新臺幣6000元,\n"
)

SAMPLE_CSV_BIG5 = SAMPLE_CSV_UTF8.encode("big5")


@pytest.fixture
def sample_csv_big5() -> bytes:
    return SAMPLE_CSV_BIG5
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_trash_bins.py
import httpx
import pytest
import respx

from sources.trash_bins import TrashBinSource, CSV_URL, parse_csv


def test_parse_csv_returns_source_items(sample_csv_big5: bytes):
    items = parse_csv(sample_csv_big5)
    assert len(items) == 3

    first = items[0]
    assert first["name"] == "中山南路(西側)外交部"
    assert first["address"] == "中正區中山南路(西側)外交部"
    assert first["lat"] == 25.0384804
    assert first["lng"] == 121.5172055
    assert first["category"] == "trash_bin"
    assert "嚴禁" in first["note"]


def test_parse_csv_skips_rows_with_bad_coordinates():
    bad_csv = "行政區,地址,經度,緯度,備註,\n中正區,某處,not_a_number,25.0,備註,\n".encode("big5")
    items = parse_csv(bad_csv)
    assert len(items) == 0


@respx.mock
@pytest.mark.asyncio
async def test_check_returns_true_on_first_run():
    respx.head(CSV_URL).mock(
        return_value=httpx.Response(200, headers={"last-modified": "Mon, 01 Jan 2026"})
    )
    source = TrashBinSource()
    assert await source.check({}) is True


@respx.mock
@pytest.mark.asyncio
async def test_check_returns_false_when_unchanged():
    respx.head(CSV_URL).mock(
        return_value=httpx.Response(
            200, headers={"last-modified": "Mon, 01 Jan 2026", "content-length": "500"}
        )
    )
    source = TrashBinSource()
    state = {"etag": "Mon, 01 Jan 2026:500"}
    assert await source.check(state) is False


@respx.mock
@pytest.mark.asyncio
async def test_check_returns_true_when_changed():
    respx.head(CSV_URL).mock(
        return_value=httpx.Response(
            200, headers={"last-modified": "Tue, 02 Jan 2026", "content-length": "600"}
        )
    )
    source = TrashBinSource()
    state = {"etag": "Mon, 01 Jan 2026:500"}
    assert await source.check(state) is True


@respx.mock
@pytest.mark.asyncio
async def test_fetch_returns_items_and_new_state(sample_csv_big5: bytes):
    respx.get(CSV_URL).mock(
        return_value=httpx.Response(
            200,
            content=sample_csv_big5,
            headers={"last-modified": "Mon, 01 Jan 2026", "content-length": "500"},
        )
    )
    source = TrashBinSource()
    items, new_state = await source.fetch()

    assert len(items) == 3
    assert items[0]["category"] == "trash_bin"
    assert "etag" in new_state
    assert "data_hash" in new_state
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_trash_bins.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sources.trash_bins'`

- [ ] **Step 4: Write minimal implementation**

```python
# sources/trash_bins.py
from __future__ import annotations

import csv
import hashlib
import io

import httpx

from sources.base import SourceItem

CSV_URL = (
    "https://data.taipei/api/dataset/"
    "a835f3ba-7f50-4b0d-91a6-9df128632d1c/resource/"
    "267d550f-c6ec-46e0-b8af-fd5a464eb098/download"
)


def parse_csv(raw: bytes) -> list[SourceItem]:
    """Parse Big5-encoded government CSV into normalized SourceItems."""
    text = raw.decode("big5")
    reader = csv.DictReader(io.StringIO(text))

    items: list[SourceItem] = []
    for row in reader:
        try:
            lat = float(row["緯度"])
            lng = float(row["經度"])
        except (ValueError, KeyError):
            continue

        items.append(
            {
                "name": row.get("地址", ""),
                "address": f"{row.get('行政區', '')}{row.get('地址', '')}",
                "lat": lat,
                "lng": lng,
                "category": "trash_bin",
                "note": row.get("備註", "").strip(),
            }
        )

    return items


class TrashBinSource:
    name = "trash_bins"

    async def check(self, state: dict) -> bool:
        if not state:
            return True

        async with httpx.AsyncClient() as client:
            resp = await client.head(CSV_URL)

        last_modified = resp.headers.get("last-modified", "")
        content_length = resp.headers.get("content-length", "")
        current_etag = f"{last_modified}:{content_length}"

        return current_etag != state.get("etag", "")

    async def fetch(self) -> tuple[list[SourceItem], dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(CSV_URL)
        resp.raise_for_status()

        items = parse_csv(resp.content)

        data_hash = hashlib.sha256(resp.content).hexdigest()
        last_modified = resp.headers.get("last-modified", "")
        content_length = resp.headers.get("content-length", "")

        new_state = {
            "etag": f"{last_modified}:{content_length}",
            "data_hash": data_hash,
        }

        return items, new_state
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_trash_bins.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add sources/trash_bins.py tests/test_trash_bins.py tests/conftest.py
git commit -m "feat: add TrashBinSource with CSV parsing and check/fetch"
```

---

### Task 7: Sheet Update

**Files:**
- Create: `pipeline/sheet.py`
- Create: `tests/test_sheet.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sheet.py
import json
from unittest.mock import MagicMock, patch

from pipeline.sheet import get_gspread_client, update_sheet


def test_update_sheet_clears_and_writes():
    mock_worksheet = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_client = MagicMock()
    mock_client.open_by_key.return_value = mock_spreadsheet

    items = [
        {
            "name": "外交部",
            "address": "中正區中山南路外交部",
            "lat": 25.038,
            "lng": 121.517,
            "category": "trash_bin",
            "note": "備註",
        }
    ]

    update_sheet(mock_client, "sheet-id-123", "工作表1", items)

    mock_client.open_by_key.assert_called_once_with("sheet-id-123")
    mock_spreadsheet.worksheet.assert_called_once_with("工作表1")
    mock_worksheet.clear.assert_called_once()
    mock_worksheet.update.assert_called_once()

    # Verify the data passed to update
    call_args = mock_worksheet.update.call_args
    rows = call_args[0][0]
    assert rows[0] == ["name", "address", "lat", "lng", "category", "note"]
    assert rows[1] == ["外交部", "中正區中山南路外交部", 25.038, 121.517, "trash_bin", "備註"]


def test_update_sheet_with_empty_items():
    mock_worksheet = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_client = MagicMock()
    mock_client.open_by_key.return_value = mock_spreadsheet

    update_sheet(mock_client, "sheet-id", "Sheet1", [])

    mock_worksheet.clear.assert_called_once()
    call_args = mock_worksheet.update.call_args
    rows = call_args[0][0]
    assert len(rows) == 1  # header only


@patch("pipeline.sheet.gspread.service_account_from_dict")
def test_get_gspread_client(mock_from_dict):
    mock_from_dict.return_value = MagicMock()
    key_json = '{"type": "service_account", "project_id": "test"}'
    client = get_gspread_client(key_json)
    mock_from_dict.assert_called_once_with({"type": "service_account", "project_id": "test"})
    assert client is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sheet.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.sheet'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/sheet.py
from __future__ import annotations

import json
from typing import Any

import gspread

HEADER = ["name", "address", "lat", "lng", "category", "note"]


def get_gspread_client(service_account_key: str) -> gspread.Client:
    """Create a gspread client from a JSON service account key string."""
    key_dict = json.loads(service_account_key)
    return gspread.service_account_from_dict(key_dict)


def update_sheet(
    client: gspread.Client,
    sheet_id: str,
    sheet_name: str,
    items: list[dict[str, Any]],
) -> None:
    """Full overwrite of a Google Sheet with source items."""
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.worksheet(sheet_name)

    worksheet.clear()

    rows: list[list] = [HEADER]
    for item in items:
        rows.append([item[col] for col in HEADER])

    worksheet.update(rows, value_input_option="RAW")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sheet.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/sheet.py tests/test_sheet.py
git commit -m "feat: add Google Sheet update with full overwrite"
```

---

### Task 8: GitHub Issue Notification

**Files:**
- Create: `pipeline/notify.py`
- Create: `tests/test_notify.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_notify.py
import httpx
import pytest
import respx

from pipeline.notify import notify_update


@respx.mock
@pytest.mark.asyncio
async def test_notify_creates_github_issue():
    route = respx.post("https://api.github.com/repos/user/repo/issues").mock(
        return_value=httpx.Response(201, json={"number": 42})
    )

    await notify_update("trash_bins", "新增 3 筆", token="ghp_test", repository="user/repo")

    assert route.called
    import json

    payload = json.loads(route.calls[0].request.content)
    assert "trash_bins" in payload["title"]
    assert "新增 3 筆" in payload["body"]


@respx.mock
@pytest.mark.asyncio
async def test_notify_skips_when_no_token(capsys):
    await notify_update("trash_bins", "新增 3 筆", token="", repository="user/repo")
    captured = capsys.readouterr()
    assert "skipping" in captured.out.lower() or "skip" in captured.out.lower()


@respx.mock
@pytest.mark.asyncio
async def test_notify_skips_when_no_repository(capsys):
    await notify_update("trash_bins", "新增 3 筆", token="ghp_test", repository="")
    captured = capsys.readouterr()
    assert "skipping" in captured.out.lower() or "skip" in captured.out.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_notify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.notify'`

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/notify.py
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


async def notify_update(
    source_name: str,
    summary: str,
    *,
    token: str,
    repository: str,
) -> None:
    """Open a GitHub Issue to notify the user of data updates.

    Silently skips if token or repository is not configured (local dev).
    """
    if not token or not repository:
        print(f"[{source_name}] {summary} (GitHub notification skipping — missing token or repo)")
        return

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{repository}/issues",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={
                "title": f"[city-nodes] {source_name} 資料更新",
                "body": (
                    f"## 變更摘要\n\n"
                    f"{summary}\n\n"
                    f"請到 Google My Maps 點「重新匯入並合併」→「重新匯入」更新地圖。"
                ),
            },
        )
        resp.raise_for_status()
        logger.info(f"[{source_name}] GitHub Issue #{resp.json()['number']} created")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_notify.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/notify.py tests/test_notify.py
git commit -m "feat: add GitHub Issue notification"
```

---

### Task 9: Main Orchestrator

**Files:**
- Create: `main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from main import run_source


@pytest.mark.asyncio
@patch("main.notify_update", new_callable=AsyncMock)
@patch("main.update_sheet")
@patch("main.write_data")
@patch("main.write_state")
@patch("main.read_data", return_value=[])
@patch("main.read_state", return_value={})
async def test_run_source_first_run(
    mock_read_state,
    mock_read_data,
    mock_write_state,
    mock_write_data,
    mock_update_sheet,
    mock_notify,
):
    source = AsyncMock()
    source.name = "test_source"
    source.check.return_value = True
    source.fetch.return_value = (
        [{"name": "A", "address": "A", "lat": 25.0, "lng": 121.0, "category": "test", "note": ""}],
        {"etag": "new", "data_hash": "abc"},
    )

    config = {"sheet_id": "sid", "sheet_name": "Sheet1"}

    settings = MagicMock()
    settings.google_service_account_key = '{"type":"test"}'
    settings.github_token = "ghp_test"
    settings.github_repository = "user/repo"

    with patch("main.get_gspread_client") as mock_client:
        await run_source(source, config, settings)

    source.check.assert_called_once_with({})
    source.fetch.assert_called_once()
    mock_update_sheet.assert_called_once()
    mock_notify.assert_called_once()
    mock_write_state.assert_called_once()
    mock_write_data.assert_called_once()


@pytest.mark.asyncio
@patch("main.read_state", return_value={"etag": "old"})
async def test_run_source_skips_when_no_update(mock_read_state):
    source = AsyncMock()
    source.name = "test_source"
    source.check.return_value = False

    config = {"sheet_id": "sid", "sheet_name": "Sheet1"}
    settings = MagicMock()

    await run_source(source, config, settings)

    source.check.assert_called_once()
    source.fetch.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'main'` or ImportError

- [ ] **Step 3: Write minimal implementation**

```python
# main.py
from __future__ import annotations

import asyncio
import logging
from typing import Any

import yaml

from pipeline.diff import compute_diff
from pipeline.notify import notify_update
from pipeline.sheet import get_gspread_client, update_sheet
from pipeline.state import read_data, read_state, write_data, write_state
from settings import Settings
from sources.base import DataSource
from sources.trash_bins import TrashBinSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

SOURCE_REGISTRY: dict[str, type] = {
    "trash_bins": TrashBinSource,
}


async def run_source(
    source: DataSource, config: dict[str, Any], settings: Settings
) -> None:
    """Run the full pipeline for a single source."""
    logger.info(f"[{source.name}] Checking for updates...")

    state = read_state(source.name)

    if not await source.check(state):
        logger.info(f"[{source.name}] No updates found, skipping.")
        return

    logger.info(f"[{source.name}] Update detected, fetching...")
    items, new_state = await source.fetch()
    logger.info(f"[{source.name}] Fetched {len(items)} items.")

    old_data = read_data(source.name)
    diff = compute_diff(old_data, items)
    logger.info(f"[{source.name}] Diff: {diff.summary}")

    if not diff.has_changes and old_data:
        logger.info(f"[{source.name}] Data identical, skipping sheet update.")
        write_state(source.name, new_state)
        return

    # Update Google Sheet
    client = get_gspread_client(settings.google_service_account_key)
    await asyncio.to_thread(
        update_sheet, client, config["sheet_id"], config["sheet_name"], items
    )
    logger.info(f"[{source.name}] Google Sheet updated.")

    # Notify via GitHub Issue
    summary = diff.summary if old_data else f"初次匯入 {len(items)} 筆資料"
    await notify_update(
        source.name,
        summary,
        token=settings.github_token,
        repository=settings.github_repository,
    )

    # Persist state and data (last — so failures above cause retry)
    write_state(source.name, new_state)
    write_data(source.name, items)
    logger.info(f"[{source.name}] State saved.")


async def main() -> None:
    settings = Settings()

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    tasks = []
    for name, source_config in config["sources"].items():
        if not source_config.get("enabled", False):
            logger.info(f"[{name}] Disabled, skipping.")
            continue
        if name not in SOURCE_REGISTRY:
            logger.warning(f"[{name}] Unknown source, skipping.")
            continue
        source = SOURCE_REGISTRY[name]()
        tasks.append(run_source(source, source_config, settings))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Source failed: {result}", exc_info=result)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_main.py -v`
Expected: 2 passed

- [ ] **Step 5: Run all tests**

Run: `uv run pytest -v`
Expected: All tests pass (expect ~19 total)

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add async main orchestrator"
```

---

### Task 10: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/update.yml`

- [ ] **Step 1: Create workflow file**

```yaml
# .github/workflows/update.yml
name: Update city nodes

on:
  schedule:
    - cron: '0 0 * * 1' # Every Monday at UTC 00:00
  workflow_dispatch: # Manual trigger button

permissions:
  contents: write
  issues: write

env:
  GOOGLE_SERVICE_ACCOUNT_KEY: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_KEY }}
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  GITHUB_REPOSITORY: ${{ github.repository }}

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5

      - name: Run pipeline
        run: uv run main.py

      - name: Commit state changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add state/
          git diff --staged --quiet || (git commit -m "chore: update source states" && git push)
```

- [ ] **Step 2: Verify YAML syntax**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/update.yml')); print('Valid YAML')"`
Expected: `Valid YAML`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/update.yml
git commit -m "ci: add GitHub Actions workflow for weekly updates"
```

---

### Task 11: End-to-End Local Verification

This task validates the full pipeline works locally before relying on GitHub Actions.

**Prerequisites:**
1. A Google Cloud Service Account JSON key
2. A Google Sheet shared with the Service Account email
3. Update `config.yaml` with the real Sheet ID
4. Create `.env` with real credentials

- [ ] **Step 1: Set up local .env**

```bash
cp .env.example .env
# Edit .env with real values:
# GOOGLE_SERVICE_ACCOUNT_KEY={"type":"service_account",...}
# GITHUB_TOKEN=  (leave empty for local — skips notification)
# GITHUB_REPOSITORY=  (leave empty for local)
```

- [ ] **Step 2: Update config.yaml with real Sheet ID**

Edit `config.yaml` and replace `your-google-sheet-id` with the actual Google Sheet ID from the URL: `https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`

- [ ] **Step 3: Run the pipeline locally**

Run: `uv run python main.py`

Expected output (first run):
```
[INFO] [trash_bins] Checking for updates...
[INFO] [trash_bins] Update detected, fetching...
[INFO] [trash_bins] Fetched ~1506 items.
[INFO] [trash_bins] Diff: 初次匯入 1506 筆資料
[INFO] [trash_bins] Google Sheet updated.
[INFO] [trash_bins] GitHub notification skipping — missing token or repo
[INFO] [trash_bins] State saved.
```

- [ ] **Step 4: Verify Google Sheet has data**

Open the Google Sheet in browser. Confirm:
- Row 1 is the header: `name | address | lat | lng | category | note`
- ~1506 data rows below
- Chinese characters display correctly

- [ ] **Step 5: Run again to verify skip behavior**

Run: `uv run python main.py`

Expected output (second run, no changes):
```
[INFO] [trash_bins] Checking for updates...
[INFO] [trash_bins] No updates found, skipping.
```

- [ ] **Step 6: Verify state files**

Run: `cat state/trash_bins.json`
Expected: JSON with `etag` and `data_hash` fields.

Run: `wc -l state/trash_bins_data.json`
Expected: Large file with ~1506 items.

- [ ] **Step 7: Run all tests one final time**

Run: `uv run pytest -v`
Expected: All tests pass.

- [ ] **Step 8: Commit state and config (do NOT commit .env)**

```bash
git add state/ config.yaml
git commit -m "chore: initial state after first successful run"
```
