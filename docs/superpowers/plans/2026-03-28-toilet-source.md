# Toilet Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `ToiletSource` data source for Taipei public restroom locations, following the existing `TrashBinSource` pattern.

**Architecture:** New `sources/toilets.py` implements the `DataSource` Protocol (same as `TrashBinSource`). CSV is UTF-8 with BOM from data.taipei, metadata check via data.gov.tw. Registered in `main.py` and configured in `config.yaml`.

**Tech Stack:** Python 3.12, httpx, csv, pytest, respx

**Spec:** `docs/superpowers/specs/2026-03-28-toilet-source-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `sources/toilets.py` | CSV parsing + `ToiletSource` class |
| Create | `tests/test_toilets.py` | Unit tests for parsing + check + fetch |
| Modify | `tests/conftest.py` | Add `sample_toilet_csv` fixture |
| Modify | `config.yaml` | Add `toilets` source entry |
| Modify | `main.py` | Register `ToiletSource` in `SOURCE_REGISTRY` |

---

### Task 1: Test fixture for toilet CSV

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add sample toilet CSV fixture to conftest.py**

Add after the existing `sample_csv_big5` fixture in `tests/conftest.py`:

```python
# Sample toilet CSV (UTF-8 with BOM).
# Header has trailing space on 改善級 — matches the real data.
SAMPLE_TOILET_CSV_UTF8 = (
    "\ufeff行政區,公廁類別,公廁名稱,公廁地址,經度,緯度,管理單位,座數,特優級,優等級,普通級,改善級 ,無障礙廁座數,親子廁座數\n"
    "士林區,交通,捷運劍潭站(淡水信義線),臺北市士林區中山北路五段65號,121.525078,25.084873,捷運劍潭站(夜),5,5,0,0,0,0,1\n"
    "大安區,公園綠地,大安森林公園,臺北市大安區新生南路二段1號,121.535370,25.029867,大安森林公園,8,0,3,5,0,1,1\n"
    "中正區,加油站,台亞中正站,臺北市中正區重慶南路三段15號,121.510234,25.027654,台亞中正站,3,0,0,0,0,0,0\n"
)

SAMPLE_TOILET_CSV_BYTES = SAMPLE_TOILET_CSV_UTF8.encode("utf-8")


@pytest.fixture
def sample_toilet_csv() -> bytes:
    return SAMPLE_TOILET_CSV_BYTES
```

- [ ] **Step 2: Run existing tests to make sure nothing is broken**

Run: `cd /Users/jhlin/playground/city-nodes && python -m pytest tests/conftest.py tests/test_trash_bins.py -v`
Expected: All existing tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add sample toilet CSV fixture"
```

---

### Task 2: `parse_csv` — test and implement

**Files:**
- Create: `sources/toilets.py`
- Create: `tests/test_toilets.py`

- [ ] **Step 1: Write failing tests for `parse_csv`**

Create `tests/test_toilets.py`:

```python
import httpx
import pytest
import respx

from sources.toilets import ToiletSource, CSV_URL, METADATA_URL, parse_csv


def test_parse_csv_returns_source_items(sample_toilet_csv: bytes):
    items = parse_csv(sample_toilet_csv)
    assert len(items) == 3

    first = items[0]
    assert first["name"] == "捷運劍潭站(淡水信義線)"
    assert first["address"] == "臺北市士林區中山北路五段65號"
    assert first["lat"] == 25.084873
    assert first["lng"] == 121.525078
    assert first["category"] == "toilet"
    assert first["note"] == "交通 / 5座 / 特優5"

    second = items[1]
    assert second["note"] == "公園綠地 / 8座 / 優等3 普通5"

    third = items[2]
    assert third["note"] == "加油站 / 3座"


def test_parse_csv_skips_rows_with_bad_coordinates():
    bad_csv = (
        "\ufeff行政區,公廁類別,公廁名稱,公廁地址,經度,緯度,管理單位,座數,特優級,優等級,普通級,改善級 ,無障礙廁座數,親子廁座數\n"
        "中正區,交通,某站,某地址,not_a_number,25.0,管理單位,3,0,0,0,0,0,0\n"
    ).encode("utf-8")
    items = parse_csv(bad_csv)
    assert len(items) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jhlin/playground/city-nodes && python -m pytest tests/test_toilets.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sources.toilets'`

- [ ] **Step 3: Implement `parse_csv` and constants in `sources/toilets.py`**

Create `sources/toilets.py`:

```python
from __future__ import annotations

import csv
import hashlib
import io
import logging

import httpx

from sources.base import SourceItem

logger = logging.getLogger(__name__)

CSV_URL = (
    "https://data.taipei/api/dataset/"
    "ca205b54-a06f-4d84-894c-d6ab5079ce79/resource/"
    "9e0e6ad4-b9f9-4810-8551-0cffd1b915b3/download"
)

METADATA_URL = "https://data.gov.tw/api/v2/rest/dataset/138798"

GRADE_FIELDS = ["特優級", "優等級", "普通級", "改善級"]
GRADE_LABELS = ["特優", "優等", "普通", "改善"]


def _build_note(row: dict[str, str]) -> str:
    """Compose note from category, stall count, and non-zero grades."""
    parts = [row.get("公廁類別", "")]

    stalls = row.get("座數", "").strip()
    if stalls:
        parts.append(f"{stalls}座")

    grades = []
    for field, label in zip(GRADE_FIELDS, GRADE_LABELS):
        value = row.get(field, "").strip()
        try:
            count = int(value)
        except (ValueError, TypeError):
            continue
        if count > 0:
            grades.append(f"{label}{count}")

    if grades:
        parts.append(" ".join(grades))

    return " / ".join(parts)


def parse_csv(raw: bytes) -> list[SourceItem]:
    """Parse UTF-8 (with BOM) government CSV into normalized SourceItems."""
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    items: list[SourceItem] = []
    for row in reader:
        # Strip whitespace from keys to handle trailing spaces in headers
        row = {k.strip(): v for k, v in row.items()}
        try:
            lat = float(row["緯度"])
            lng = float(row["經度"])
        except (ValueError, KeyError):
            continue

        items.append(
            {
                "name": row.get("公廁名稱", ""),
                "address": row.get("公廁地址", ""),
                "lat": lat,
                "lng": lng,
                "category": "toilet",
                "note": _build_note(row),
            }
        )

    return items
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/jhlin/playground/city-nodes && python -m pytest tests/test_toilets.py::test_parse_csv_returns_source_items tests/test_toilets.py::test_parse_csv_skips_rows_with_bad_coordinates -v`
Expected: Both PASS.

- [ ] **Step 5: Commit**

```bash
git add sources/toilets.py tests/test_toilets.py
git commit -m "feat: add toilet CSV parser with tests"
```

---

### Task 3: `ToiletSource.check()` — test and implement

**Files:**
- Modify: `sources/toilets.py`
- Modify: `tests/test_toilets.py`

- [ ] **Step 1: Add failing tests for `check()` to `tests/test_toilets.py`**

Append to `tests/test_toilets.py`:

```python
@respx.mock
@pytest.mark.asyncio
async def test_check_returns_true_on_first_run():
    metadata = {"success": True, "result": {"modifiedDate": "2026-03-04 14:40:28"}}
    respx.get(METADATA_URL).mock(return_value=httpx.Response(200, json=metadata))
    source = ToiletSource()
    assert await source.check({}) is True


@respx.mock
@pytest.mark.asyncio
async def test_check_returns_false_when_unchanged():
    metadata = {"success": True, "result": {"modifiedDate": "2026-03-04 14:40:28"}}
    respx.get(METADATA_URL).mock(return_value=httpx.Response(200, json=metadata))
    source = ToiletSource()
    state = {"modified_date": "2026-03-04 14:40:28"}
    assert await source.check(state) is False


@respx.mock
@pytest.mark.asyncio
async def test_check_returns_true_when_changed():
    metadata = {"success": True, "result": {"modifiedDate": "2026-03-10 09:00:00"}}
    respx.get(METADATA_URL).mock(return_value=httpx.Response(200, json=metadata))
    source = ToiletSource()
    state = {"modified_date": "2026-03-04 14:40:28"}
    assert await source.check(state) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/jhlin/playground/city-nodes && python -m pytest tests/test_toilets.py::test_check_returns_true_on_first_run -v`
Expected: FAIL — `ToiletSource` not defined.

- [ ] **Step 3: Implement `ToiletSource` class with `check()` in `sources/toilets.py`**

Add at the bottom of `sources/toilets.py`:

```python
class ToiletSource:
    name = "toilets"

    async def check(self, state: dict) -> bool:
        if not state:
            return True

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(METADATA_URL)
            resp.raise_for_status()
            modified_date = resp.json()["result"]["modifiedDate"]
        except Exception as exc:
            logger.warning(f"[{self.name}] Metadata check failed: {exc}; assuming update needed.")
            return True

        return modified_date != state.get("modified_date", "")
```

- [ ] **Step 4: Run check tests to verify they pass**

Run: `cd /Users/jhlin/playground/city-nodes && python -m pytest tests/test_toilets.py::test_check_returns_true_on_first_run tests/test_toilets.py::test_check_returns_false_when_unchanged tests/test_toilets.py::test_check_returns_true_when_changed -v`
Expected: All 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add sources/toilets.py tests/test_toilets.py
git commit -m "feat: add ToiletSource.check() with tests"
```

---

### Task 4: `ToiletSource.fetch()` — test and implement

**Files:**
- Modify: `sources/toilets.py`
- Modify: `tests/test_toilets.py`

- [ ] **Step 1: Add failing test for `fetch()` to `tests/test_toilets.py`**

Append to `tests/test_toilets.py`:

```python
@respx.mock
@pytest.mark.asyncio
async def test_fetch_returns_items_and_new_state(sample_toilet_csv: bytes):
    respx.get(CSV_URL).mock(
        return_value=httpx.Response(200, content=sample_toilet_csv)
    )
    metadata = {"success": True, "result": {"modifiedDate": "2026-03-04 14:40:28"}}
    respx.get(METADATA_URL).mock(return_value=httpx.Response(200, json=metadata))

    source = ToiletSource()
    items, new_state = await source.fetch()

    assert len(items) == 3
    assert items[0]["category"] == "toilet"
    assert items[0]["name"] == "捷運劍潭站(淡水信義線)"
    assert new_state["modified_date"] == "2026-03-04 14:40:28"
    assert "data_hash" in new_state
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/jhlin/playground/city-nodes && python -m pytest tests/test_toilets.py::test_fetch_returns_items_and_new_state -v`
Expected: FAIL — `ToiletSource` has no `fetch` method.

- [ ] **Step 3: Add `fetch()` method to `ToiletSource` in `sources/toilets.py`**

Add inside the `ToiletSource` class, after `check()`:

```python
    async def fetch(self) -> tuple[list[SourceItem], dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(CSV_URL)
        resp.raise_for_status()

        items = parse_csv(resp.content)

        data_hash = hashlib.sha256(resp.content).hexdigest()

        # Fetch current modifiedDate for state
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                meta_resp = await client.get(METADATA_URL)
            meta_resp.raise_for_status()
            modified_date = meta_resp.json()["result"]["modifiedDate"]
        except Exception:
            modified_date = ""

        new_state = {
            "modified_date": modified_date,
            "data_hash": data_hash,
        }

        return items, new_state
```

- [ ] **Step 4: Run all toilet tests to verify they pass**

Run: `cd /Users/jhlin/playground/city-nodes && python -m pytest tests/test_toilets.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sources/toilets.py tests/test_toilets.py
git commit -m "feat: add ToiletSource.fetch() with tests"
```

---

### Task 5: Register in config and main

**Files:**
- Modify: `config.yaml`
- Modify: `main.py`

- [ ] **Step 1: Add toilets entry to `config.yaml`**

Append to `config.yaml` after the `trash_bins` block:

```yaml
  toilets:
    enabled: true
    sheet_id: '1yLwmMRjMm_xMgYKn2el17O2P0oB1edZDcgPRxYsIQdc'
    sheet_name: '工作表1'
```

- [ ] **Step 2: Register `ToiletSource` in `main.py`**

Add import at the top of `main.py`, next to the existing `TrashBinSource` import:

```python
from sources.toilets import ToiletSource
```

Update `SOURCE_REGISTRY`:

```python
SOURCE_REGISTRY: dict[str, type] = {
    "trash_bins": TrashBinSource,
    "toilets": ToiletSource,
}
```

- [ ] **Step 3: Run full test suite**

Run: `cd /Users/jhlin/playground/city-nodes && python -m pytest -v`
Expected: All tests PASS (existing + new toilet tests).

- [ ] **Step 4: Commit**

```bash
git add config.yaml main.py
git commit -m "feat: register ToiletSource in config and main"
```
