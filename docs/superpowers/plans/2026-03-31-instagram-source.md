# Instagram Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Instagram data source that scrapes public accounts, extracts location names via Claude API, geocodes via Google Places API, and outputs SourceItem records to the existing pipeline.

**Architecture:** `InstagramSource` implements the `DataSource` protocol. Internally it runs a 4-step pipeline: scrape (Instaloader) → extract (Claude API) → deduplicate (Claude API) → geocode (Google Places). Two new pipeline modules (`llm.py`, `geocode.py`) encapsulate external API calls. Each step caches intermediate results in `state/` for incremental updates and failure recovery.

**Tech Stack:** Python 3.12, Instaloader 4.15+, Anthropic SDK 0.80+, Google Places API (New), httpx, pytest, respx

**Spec:** `docs/superpowers/specs/2026-03-31-instagram-source-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `pipeline/geocode.py` | Google Places Text Search wrapper — one function: `geocode_location()` |
| `pipeline/llm.py` | Claude API wrapper — `extract_locations()`, `deduplicate_locations()`, `_parse_json_response()` helper |
| `sources/instagram.py` | `InstagramSource` class — types, cache helpers, 4-step internal pipeline, `DataSource` protocol |
| `tests/test_geocode.py` | Tests for geocoding module |
| `tests/test_llm.py` | Tests for LLM module |
| `tests/test_instagram.py` | Tests for InstagramSource |

### Modified files

| File | Change |
|------|--------|
| `pyproject.toml` | Add `instaloader`, `anthropic` dependencies |
| `settings.py` | Add `anthropic_api_key`, `google_places_api_key` fields |
| `.env.example` | Add new env var placeholders |
| `main.py` | Add `TYPE_REGISTRY`, `create_source()`, update source creation loop |
| `tests/test_main.py` | Add tests for `create_source()` |
| `config.yaml` | Add `ig_maokaishungry` entry |
| `.github/workflows/update.yml` | Add env vars + `timeout-minutes` |

---

### Task 1: Foundation — Dependencies + Settings + Environment

**Files:**
- Modify: `pyproject.toml`
- Modify: `settings.py`
- Modify: `.env.example`

- [ ] **Step 1: Add new dependencies to pyproject.toml**

```toml
dependencies = [
    "gspread>=6.0.0",
    "httpx>=0.27.0",
    "pydantic-settings>=2.0.0",
    "pyyaml>=6.0",
    "instaloader>=4.15",
    "anthropic>=0.80.0",
]
```

- [ ] **Step 2: Add new settings fields to settings.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_service_account_key: str = ""
    github_token: str = ""
    github_repository: str = ""
    anthropic_api_key: str = ""
    google_places_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

- [ ] **Step 3: Update .env.example**

```
GOOGLE_SERVICE_ACCOUNT_KEY={"type":"service_account","project_id":"..."}
GITHUB_TOKEN=
GITHUB_REPOSITORY=owner/repo
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_PLACES_API_KEY=AIza...
```

- [ ] **Step 4: Install dependencies**

Run: `uv sync --dev`
Expected: Dependencies install successfully.

- [ ] **Step 5: Run existing tests to verify no breakage**

Run: `uv run pytest -v`
Expected: All existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock settings.py .env.example
git commit -m "feat: add instaloader + anthropic dependencies and settings"
```

---

### Task 2: Google Places Geocoding Module

**Files:**
- Create: `pipeline/geocode.py`
- Create: `tests/test_geocode.py`

- [ ] **Step 1: Write failing tests for geocode_location**

Create `tests/test_geocode.py`:

```python
import httpx
import pytest
import respx

from pipeline.geocode import PLACES_TEXT_SEARCH_URL, geocode_location


@respx.mock
@pytest.mark.asyncio
async def test_geocode_location_returns_source_item():
    respx.post(PLACES_TEXT_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "places": [
                    {
                        "formattedAddress": "台北市信義區松仁路8號",
                        "location": {"latitude": 25.0336, "longitude": 121.5678},
                    }
                ]
            },
        )
    )

    result = await geocode_location(
        "一蘭拉麵", "信義區", api_key="test-key", category="restaurant"
    )

    assert result is not None
    assert result["name"] == "一蘭拉麵"
    assert result["address"] == "台北市信義區松仁路8號"
    assert result["lat"] == 25.0336
    assert result["lng"] == 121.5678
    assert result["category"] == "restaurant"
    assert result["note"] == ""


@respx.mock
@pytest.mark.asyncio
async def test_geocode_location_returns_none_when_no_results():
    respx.post(PLACES_TEXT_SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"places": []})
    )

    result = await geocode_location(
        "不存在的地方", "", api_key="test-key", category="restaurant"
    )

    assert result is None


@respx.mock
@pytest.mark.asyncio
async def test_geocode_location_builds_query_with_area():
    route = respx.post(PLACES_TEXT_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "places": [
                    {
                        "formattedAddress": "addr",
                        "location": {"latitude": 25.0, "longitude": 121.0},
                    }
                ]
            },
        )
    )

    await geocode_location("鼎泰豐", "大安區", api_key="k", category="restaurant")

    request_body = route.calls[0].request
    import json
    body = json.loads(request_body.content)
    assert body["textQuery"] == "鼎泰豐 大安區"
    assert body["languageCode"] == "zh-TW"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_geocode.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.geocode'`

- [ ] **Step 3: Implement pipeline/geocode.py**

Create `pipeline/geocode.py`:

```python
from __future__ import annotations

import logging

import httpx

from sources.base import SourceItem

logger = logging.getLogger(__name__)

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"


async def geocode_location(
    name: str,
    area: str,
    *,
    api_key: str,
    category: str = "",
) -> SourceItem | None:
    """Look up a location by name using Google Places Text Search API.

    Returns a SourceItem with address and coordinates, or None if not found.
    """
    query = f"{name} {area}" if area else name
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            PLACES_TEXT_SEARCH_URL,
            headers={
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "places.formattedAddress,places.location",
            },
            json={"textQuery": query, "languageCode": "zh-TW"},
        )
    resp.raise_for_status()
    places = resp.json().get("places", [])
    if not places:
        logger.warning(f"Geocode: no results for '{query}'")
        return None

    place = places[0]
    return {
        "name": name,
        "address": place["formattedAddress"],
        "lat": place["location"]["latitude"],
        "lng": place["location"]["longitude"],
        "category": category,
        "note": "",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_geocode.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/geocode.py tests/test_geocode.py
git commit -m "feat: add Google Places geocoding module"
```

---

### Task 3: LLM Extraction and Deduplication Module

**Files:**
- Create: `pipeline/llm.py`
- Create: `tests/test_llm.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_llm.py`:

```python
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pipeline.llm import (
    _parse_json_response,
    deduplicate_locations,
    extract_locations,
)


def test_parse_json_response_plain():
    assert _parse_json_response('[{"a": 1}]') == [{"a": 1}]


def test_parse_json_response_code_block():
    text = '```json\n[{"a": 1}]\n```'
    assert _parse_json_response(text) == [{"a": 1}]


def test_parse_json_response_code_block_no_lang():
    text = '```\n[{"a": 1}]\n```'
    assert _parse_json_response(text) == [{"a": 1}]


@pytest.mark.asyncio
@patch("pipeline.llm.anthropic.AsyncAnthropic")
async def test_extract_locations_single_batch(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text=json.dumps(
                [
                    {"post_shortcode": "abc", "name": "一蘭拉麵", "area": "信義區"},
                    {"post_shortcode": "abc", "name": "鼎泰豐", "area": ""},
                ]
            )
        )
    ]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    posts = [{"shortcode": "abc", "caption": "今天吃一蘭拉麵跟鼎泰豐"}]
    results = await extract_locations(posts, api_key="test-key")

    assert len(results) == 2
    assert results[0]["name"] == "一蘭拉麵"
    assert results[1]["name"] == "鼎泰豐"
    mock_client.messages.create.assert_called_once()


@pytest.mark.asyncio
@patch("pipeline.llm.anthropic.AsyncAnthropic")
async def test_extract_locations_multiple_batches(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="[]")]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    # 25 posts → 2 batches (20 + 5) with EXTRACT_BATCH_SIZE=20
    posts = [{"shortcode": f"p{i}", "caption": f"post {i}"} for i in range(25)]
    await extract_locations(posts, api_key="test-key")

    assert mock_client.messages.create.call_count == 2


@pytest.mark.asyncio
@patch("pipeline.llm.anthropic.AsyncAnthropic")
async def test_extract_locations_handles_bad_json(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="not json at all")]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    posts = [{"shortcode": "abc", "caption": "test"}]
    results = await extract_locations(posts, api_key="test-key")

    assert results == []


@pytest.mark.asyncio
@patch("pipeline.llm.anthropic.AsyncAnthropic")
async def test_deduplicate_locations(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text=json.dumps(
                [
                    {
                        "canonical_name": "一蘭拉麵 台北本店",
                        "area": "信義區",
                        "source_posts": ["abc", "def"],
                    }
                ]
            )
        )
    ]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    locations = [
        {"name": "一蘭拉麵", "area": "信義區", "source_posts": ["abc"]},
        {"name": "一蘭拉面 台北", "area": "", "source_posts": ["def"]},
    ]
    results = await deduplicate_locations(locations, api_key="test-key")

    assert len(results) == 1
    assert results[0]["canonical_name"] == "一蘭拉麵 台北本店"
    assert set(results[0]["source_posts"]) == {"abc", "def"}


@pytest.mark.asyncio
async def test_deduplicate_locations_empty_input():
    results = await deduplicate_locations([], api_key="test-key")
    assert results == []


@pytest.mark.asyncio
@patch("pipeline.llm.anthropic.AsyncAnthropic")
async def test_deduplicate_locations_handles_bad_json(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="broken")]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    locations = [{"name": "A", "area": "", "source_posts": ["p1"]}]
    results = await deduplicate_locations(locations, api_key="test-key")

    # Falls back to passthrough
    assert len(results) == 1
    assert results[0]["canonical_name"] == "A"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_llm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.llm'`

- [ ] **Step 3: Implement pipeline/llm.py**

Create `pipeline/llm.py`:

```python
from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

EXTRACT_BATCH_SIZE = 20
EXTRACT_MODEL = "claude-haiku-4-5-20251001"
DEDUP_MODEL = "claude-haiku-4-5-20251001"


def _parse_json_response(text: str) -> Any:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # Remove opening ```json or ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


async def extract_locations(
    posts: list[dict[str, str]],
    *,
    api_key: str,
) -> list[dict[str, str]]:
    """Extract location names from Instagram post captions using Claude API.

    Args:
        posts: List of dicts with 'shortcode' and 'caption' keys.
        api_key: Anthropic API key.

    Returns:
        List of dicts with 'post_shortcode', 'name', and 'area' keys.
    """
    client = anthropic.AsyncAnthropic(api_key=api_key)
    all_results: list[dict[str, str]] = []

    for i in range(0, len(posts), EXTRACT_BATCH_SIZE):
        batch = posts[i : i + EXTRACT_BATCH_SIZE]
        captions_text = "\n---\n".join(
            f"[{p['shortcode']}]\n{p['caption']}" for p in batch
        )

        response = await client.messages.create(
            model=EXTRACT_MODEL,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "從以下 Instagram 貼文中提取地點資訊。\n"
                        "每篇貼文可能提到 0 到多個地點。回傳 JSON array。\n\n"
                        f"貼文：\n{captions_text}\n\n"
                        "回傳格式：\n"
                        '[{"post_shortcode": "...", "name": "店名", "area": "區域"}]\n\n'
                        "規則：\n"
                        "- 只提取明確的店名/地點，不要猜測\n"
                        "- 如果貼文沒有提到任何地點，跳過該篇\n"
                        "- area 填寫行政區或商圈名稱（如 caption 有提到），沒有則為空字串"
                    ),
                }
            ],
        )

        try:
            results = _parse_json_response(response.content[0].text)
            all_results.extend(results)
        except (json.JSONDecodeError, IndexError, KeyError) as exc:
            logger.warning(f"Failed to parse LLM extract response for batch {i}: {exc}")

    return all_results


async def deduplicate_locations(
    locations: list[dict[str, Any]],
    *,
    api_key: str,
) -> list[dict[str, Any]]:
    """Group duplicate location names using Claude API.

    Args:
        locations: List of dicts with 'name', 'area', and 'source_posts' keys.
        api_key: Anthropic API key.

    Returns:
        List of dicts with 'canonical_name', 'area', and 'source_posts' keys.
    """
    if not locations:
        return []

    client = anthropic.AsyncAnthropic(api_key=api_key)

    names_text = "\n".join(
        f"- {loc['name']} (area: {loc['area']}, posts: {','.join(loc['source_posts'])})"
        for loc in locations
    )

    response = await client.messages.create(
        model=DEDUP_MODEL,
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": (
                    "以下是從 Instagram 提取的地點名稱列表，\n"
                    "請將指向同一個地點的名稱分為同一組，\n"
                    "每組選出一個最正式的名稱作為代表。\n\n"
                    f"{names_text}\n\n"
                    "回傳 JSON array:\n"
                    '[{"canonical_name": "正式名稱", "area": "區域", '
                    '"source_posts": ["shortcode1", "shortcode2"]}]\n\n'
                    "規則：\n"
                    "- 合併同一地點的所有 source_posts\n"
                    "- area 取最具體的那個\n"
                    "- canonical_name 選最正式、最完整的名稱"
                ),
            }
        ],
    )

    try:
        return _parse_json_response(response.content[0].text)
    except (json.JSONDecodeError, IndexError, KeyError) as exc:
        logger.warning(f"Failed to parse dedup response: {exc}")
        return [
            {
                "canonical_name": loc["name"],
                "area": loc["area"],
                "source_posts": loc["source_posts"],
            }
            for loc in locations
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_llm.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/llm.py tests/test_llm.py
git commit -m "feat: add LLM extraction and deduplication module"
```

---

### Task 4: InstagramSource

**Files:**
- Create: `sources/instagram.py`
- Create: `tests/test_instagram.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_instagram.py`:

```python
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sources.instagram import InstagramSource


@pytest.fixture
def ig_source(tmp_path):
    settings = MagicMock()
    settings.anthropic_api_key = "test-anthropic-key"
    settings.google_places_api_key = "test-places-key"
    return InstagramSource(
        name="ig_test",
        target="testaccount",
        category="restaurant",
        settings=settings,
        state_dir=tmp_path,
    )


@pytest.mark.asyncio
async def test_check_always_returns_true(ig_source):
    assert await ig_source.check({}) is True
    assert await ig_source.check({"last_post_timestamp": "2026-03-20T00:00:00+00:00"}) is True


def test_merge_extracted(ig_source):
    existing = [
        {"name": "一蘭拉麵", "area": "信義區", "source_posts": ["p1"]},
        {"name": "鼎泰豐", "area": "", "source_posts": ["p1"]},
    ]
    new = [
        {"name": "一蘭拉麵", "area": "信義區", "source_posts": ["p2"]},
        {"name": "CoCo", "area": "大安區", "source_posts": ["p2"]},
    ]

    merged = ig_source._merge_extracted(existing, new)

    by_name = {loc["name"]: loc for loc in merged}
    assert len(by_name) == 3
    assert set(by_name["一蘭拉麵"]["source_posts"]) == {"p1", "p2"}
    assert by_name["鼎泰豐"]["source_posts"] == ["p1"]
    assert by_name["CoCo"]["source_posts"] == ["p2"]


@pytest.mark.asyncio
@patch("sources.instagram.geocode_location", new_callable=AsyncMock)
@patch("sources.instagram.deduplicate_locations", new_callable=AsyncMock)
@patch("sources.instagram.extract_locations", new_callable=AsyncMock)
async def test_fetch_first_run(mock_extract, mock_dedup, mock_geocode, ig_source):
    """First run: no caches, all steps execute."""
    ig_source._scrape = AsyncMock(
        return_value=[
            {
                "shortcode": "abc123",
                "caption": "好吃的拉麵",
                "timestamp": "2026-03-20T12:00:00+00:00",
                "location_name": "",
                "location_lat": None,
                "location_lng": None,
            }
        ]
    )
    mock_extract.return_value = [
        {"post_shortcode": "abc123", "name": "一蘭拉麵", "area": "信義區"}
    ]
    mock_dedup.return_value = [
        {"canonical_name": "一蘭拉麵", "area": "信義區", "source_posts": ["abc123"]}
    ]
    mock_geocode.return_value = {
        "name": "一蘭拉麵",
        "address": "台北市信義區松仁路8號",
        "lat": 25.0336,
        "lng": 121.5678,
        "category": "restaurant",
        "note": "",
    }

    await ig_source.check({})
    items, new_state = await ig_source.fetch()

    assert len(items) == 1
    assert items[0]["name"] == "一蘭拉麵"
    assert items[0]["address"] == "台北市信義區松仁路8號"
    assert items[0]["lat"] == 25.0336
    assert items[0]["category"] == "restaurant"
    assert new_state["last_post_timestamp"] == "2026-03-20T12:00:00+00:00"

    mock_extract.assert_called_once()
    mock_dedup.assert_called_once()
    mock_geocode.assert_called_once()


@pytest.mark.asyncio
@patch("sources.instagram.geocode_location", new_callable=AsyncMock)
@patch("sources.instagram.deduplicate_locations", new_callable=AsyncMock)
@patch("sources.instagram.extract_locations", new_callable=AsyncMock)
async def test_fetch_incremental_skips_cached(
    mock_extract, mock_dedup, mock_geocode, ig_source
):
    """Incremental: cached posts are not re-extracted, cached locations not re-geocoded."""
    # Pre-populate caches
    ig_source._write_cache(
        "posts",
        [
            {
                "shortcode": "old1",
                "caption": "old post",
                "timestamp": "2026-03-10T00:00:00+00:00",
                "location_name": "",
                "location_lat": None,
                "location_lng": None,
            }
        ],
    )
    ig_source._write_cache(
        "extracted",
        [{"name": "舊店", "area": "", "source_posts": ["old1"]}],
    )
    ig_source._write_cache(
        "geocoded",
        [
            {
                "name": "舊店",
                "address": "舊地址",
                "lat": 25.0,
                "lng": 121.0,
                "category": "restaurant",
                "note": "",
            }
        ],
    )

    # Scrape returns one new post
    ig_source._scrape = AsyncMock(
        return_value=[
            {
                "shortcode": "new1",
                "caption": "new post",
                "timestamp": "2026-03-25T00:00:00+00:00",
                "location_name": "",
                "location_lat": None,
                "location_lng": None,
            }
        ]
    )

    # Extract only processes the new post
    mock_extract.return_value = [
        {"post_shortcode": "new1", "name": "新店", "area": "中山區"}
    ]

    # Dedup returns both old and new
    mock_dedup.return_value = [
        {"canonical_name": "舊店", "area": "", "source_posts": ["old1"]},
        {"canonical_name": "新店", "area": "中山區", "source_posts": ["new1"]},
    ]

    # Geocode is only called for "新店" (舊店 is cached)
    mock_geocode.return_value = {
        "name": "新店",
        "address": "新地址",
        "lat": 25.1,
        "lng": 121.1,
        "category": "restaurant",
        "note": "",
    }

    await ig_source.check({"last_post_timestamp": "2026-03-10T00:00:00+00:00"})
    items, new_state = await ig_source.fetch()

    assert len(items) == 2
    names = {item["name"] for item in items}
    assert names == {"舊店", "新店"}

    # Extract was called only with the new post
    extract_call_posts = mock_extract.call_args[0][0]
    assert len(extract_call_posts) == 1
    assert extract_call_posts[0]["shortcode"] == "new1"

    # Geocode was called only once (for 新店)
    mock_geocode.assert_called_once()
    assert mock_geocode.call_args[0][0] == "新店"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_instagram.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sources.instagram'`

- [ ] **Step 3: Implement sources/instagram.py**

Create `sources/instagram.py`:

```python
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

import instaloader

from pipeline.geocode import geocode_location
from pipeline.llm import deduplicate_locations, extract_locations
from sources.base import SourceItem

logger = logging.getLogger(__name__)

DEFAULT_STATE_DIR = Path("state")


class RawPost(TypedDict):
    shortcode: str
    caption: str
    timestamp: str
    location_name: str
    location_lat: float | None
    location_lng: float | None


class ExtractedLocation(TypedDict):
    name: str
    area: str
    source_posts: list[str]


class InstagramSource:
    def __init__(
        self,
        *,
        name: str,
        target: str,
        category: str = "",
        settings: Any = None,
        state_dir: Path = DEFAULT_STATE_DIR,
    ) -> None:
        self.name = name
        self.target = target
        self.category = category
        self._api_key = settings.anthropic_api_key if settings else ""
        self._places_key = settings.google_places_api_key if settings else ""
        self._state_dir = state_dir
        self._state: dict = {}

    async def check(self, state: dict) -> bool:
        self._state = state
        return True

    async def fetch(self) -> tuple[list[SourceItem], dict]:
        state = self._state

        # Step 1: Scrape new posts and merge with cached
        cached_posts = self._read_cache("posts") or []
        new_posts = await self._scrape(state)
        all_posts = new_posts + cached_posts
        if new_posts:
            self._write_cache("posts", all_posts)

        # Step 2: Extract locations from unprocessed posts
        cached_extracted: list[ExtractedLocation] = self._read_cache("extracted") or []
        processed = {sc for loc in cached_extracted for sc in loc["source_posts"]}
        unprocessed = [p for p in all_posts if p["shortcode"] not in processed]

        if unprocessed:
            new_extracted = await self._extract(unprocessed)
            all_extracted = self._merge_extracted(cached_extracted, new_extracted)
            self._write_cache("extracted", all_extracted)
        else:
            all_extracted = cached_extracted

        # Step 3: Deduplicate
        deduped = await self._deduplicate(all_extracted)
        deduped_names = {d["canonical_name"] for d in deduped}

        # Step 4: Geocode new locations (filter stale cache entries)
        geocode_cache: dict[str, SourceItem] = {
            item["name"]: item
            for item in (self._read_cache("geocoded") or [])
            if item["name"] in deduped_names
        }
        new_locs = [d for d in deduped if d["canonical_name"] not in geocode_cache]

        if new_locs:
            new_items = await self._geocode(new_locs)
            for item in new_items:
                geocode_cache[item["name"]] = item

        self._write_cache("geocoded", list(geocode_cache.values()))
        items = list(geocode_cache.values())

        # Build new state
        new_state: dict[str, str] = {}
        if all_posts:
            new_state["last_post_timestamp"] = max(
                p["timestamp"] for p in all_posts
            )

        return items, new_state

    async def _scrape(self, state: dict) -> list[RawPost]:
        """Scrape Instagram posts using Instaloader."""
        last_ts = state.get("last_post_timestamp", "")
        last_dt = datetime.fromisoformat(last_ts) if last_ts else None

        def _do_scrape() -> list[RawPost]:
            loader = instaloader.Instaloader(
                download_pictures=False,
                download_videos=False,
                download_video_thumbnails=False,
                download_comments=False,
                save_metadata=False,
            )

            if self.target.startswith("#"):
                hashtag = instaloader.Hashtag.from_name(
                    loader.context, self.target[1:]
                )
                post_iter = hashtag.get_posts()
            else:
                profile = instaloader.Profile.from_username(
                    loader.context, self.target
                )
                post_iter = profile.get_posts()

            posts: list[RawPost] = []
            for post in post_iter:
                post_dt = post.date_utc.replace(tzinfo=timezone.utc)
                if last_dt and post_dt <= last_dt:
                    break
                posts.append(
                    {
                        "shortcode": post.shortcode,
                        "caption": post.caption or "",
                        "timestamp": post_dt.isoformat(),
                        "location_name": (
                            post.location.name if post.location else ""
                        ),
                        "location_lat": (
                            post.location.lat if post.location else None
                        ),
                        "location_lng": (
                            post.location.lng if post.location else None
                        ),
                    }
                )
            return posts

        return await asyncio.to_thread(_do_scrape)

    async def _extract(self, posts: list[RawPost]) -> list[ExtractedLocation]:
        """Extract locations from post captions using LLM."""
        raw_results = await extract_locations(
            [{"shortcode": p["shortcode"], "caption": p["caption"]} for p in posts],
            api_key=self._api_key,
        )

        groups: dict[tuple[str, str], list[str]] = {}
        for r in raw_results:
            key = (r["name"], r.get("area", ""))
            groups.setdefault(key, []).append(r["post_shortcode"])

        return [
            {"name": name, "area": area, "source_posts": shortcodes}
            for (name, area), shortcodes in groups.items()
        ]

    def _merge_extracted(
        self,
        existing: list[ExtractedLocation],
        new: list[ExtractedLocation],
    ) -> list[ExtractedLocation]:
        """Merge new extracted locations into existing list."""
        merged: dict[tuple[str, str], list[str]] = {}
        for loc in existing:
            key = (loc["name"], loc["area"])
            merged.setdefault(key, []).extend(loc["source_posts"])
        for loc in new:
            key = (loc["name"], loc["area"])
            merged.setdefault(key, []).extend(loc["source_posts"])
        return [
            {"name": name, "area": area, "source_posts": sorted(set(shortcodes))}
            for (name, area), shortcodes in merged.items()
        ]

    async def _deduplicate(
        self, locations: list[ExtractedLocation]
    ) -> list[dict[str, Any]]:
        """Deduplicate locations using LLM fuzzy matching."""
        return await deduplicate_locations(locations, api_key=self._api_key)

    async def _geocode(self, locations: list[dict[str, Any]]) -> list[SourceItem]:
        """Geocode locations using Google Places API."""
        items: list[SourceItem] = []
        for loc in locations:
            name = loc["canonical_name"]
            area = loc.get("area", "")
            result = await geocode_location(
                name, area, api_key=self._places_key, category=self.category
            )
            if result:
                items.append(result)
            else:
                logger.warning(f"[{self.name}] Could not geocode: {name}")
        return items

    def _read_cache(self, suffix: str) -> list[dict] | None:
        path = self._state_dir / f"{self.name}_{suffix}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_cache(self, suffix: str, data: list[dict]) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        path = self._state_dir / f"{self.name}_{suffix}.json"
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_instagram.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add sources/instagram.py tests/test_instagram.py
git commit -m "feat: add InstagramSource with scrape/extract/dedup/geocode pipeline"
```

---

### Task 5: Main Registry and Source Creation

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write failing tests for create_source**

Add to `tests/test_main.py`:

```python
from main import create_source
from sources.trash_bins import TrashBinSource
from sources.toilets import ToiletSource
from sources.instagram import InstagramSource


def test_create_source_existing_source():
    source = create_source("trash_bins", {}, settings=MagicMock())
    assert isinstance(source, TrashBinSource)


def test_create_source_existing_toilet():
    source = create_source("toilets", {}, settings=MagicMock())
    assert isinstance(source, ToiletSource)


def test_create_source_instagram_type():
    settings = MagicMock()
    config = {"type": "instagram", "target": "testuser", "category": "restaurant"}
    source = create_source("ig_test", config, settings=settings)
    assert isinstance(source, InstagramSource)
    assert source.name == "ig_test"
    assert source.target == "testuser"
    assert source.category == "restaurant"


def test_create_source_unknown_raises():
    with pytest.raises(ValueError, match="Unknown source"):
        create_source("nonexistent", {}, settings=MagicMock())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_main.py::test_create_source_existing_source -v`
Expected: FAIL — `ImportError: cannot import name 'create_source' from 'main'`

- [ ] **Step 3: Implement TYPE_REGISTRY and create_source in main.py**

Add imports and new code to `main.py`:

```python
from sources.instagram import InstagramSource
```

Add after `SOURCE_REGISTRY`:

```python
TYPE_REGISTRY: dict[str, type] = {
    "instagram": InstagramSource,
}


def create_source(name: str, config: dict[str, Any], settings: Settings) -> DataSource:
    """Create a DataSource instance by name or type."""
    if name in SOURCE_REGISTRY:
        return SOURCE_REGISTRY[name]()
    source_type = config.get("type")
    if source_type and source_type in TYPE_REGISTRY:
        return TYPE_REGISTRY[source_type](
            name=name,
            target=config["target"],
            category=config.get("category", ""),
            settings=settings,
        )
    raise ValueError(f"Unknown source: {name}")
```

- [ ] **Step 4: Update main() to use create_source**

In the `main()` function, replace:

```python
        if name not in SOURCE_REGISTRY:
            logger.warning(f"[{name}] Unknown source, skipping.")
            continue
        source = SOURCE_REGISTRY[name]()
```

With:

```python
        try:
            source = create_source(name, source_config, settings)
        except ValueError:
            logger.warning(f"[{name}] Unknown source, skipping.")
            continue
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest -v`
Expected: All tests pass (existing + new).

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add TYPE_REGISTRY and create_source for parameterized sources"
```

---

### Task 6: Configuration and Workflow

**Files:**
- Modify: `config.yaml`
- Modify: `.github/workflows/update.yml`

- [ ] **Step 1: Add ig_maokaishungry to config.yaml**

```yaml
sources:
  trash_bins:
    enabled: true
    sheet_id: '1qFWE4ofT9cA4nz5xQV1ZOD-BMRmr-lzd8Q7howQ3hjY'
    sheet_name: '工作表1'
  toilets:
    enabled: true
    sheet_id: '1yLwmMRjMm_xMgYKn2el17O2P0oB1edZDcgPRxYsIQdc'
    sheet_name: '工作表1'
  ig_maokaishungry:
    enabled: false
    type: instagram
    target: 'maokaishungry'
    category: 'restaurant'
    sheet_id: ''
    sheet_name: '工作表1'
```

Note: `enabled: false` and empty `sheet_id` until a new Google Sheet is created.

- [ ] **Step 2: Update GitHub Actions workflow**

In `.github/workflows/update.yml`, add `timeout-minutes` to the job:

```yaml
jobs:
  update:
    runs-on: ubuntu-latest
    timeout-minutes: 30
```

Add new env vars to the "Run pipeline" step:

```yaml
      - name: Run pipeline
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GOOGLE_PLACES_API_KEY: ${{ secrets.GOOGLE_PLACES_API_KEY }}
        run: uv run main.py
```

- [ ] **Step 3: Run all tests to verify nothing breaks**

Run: `uv run pytest -v`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add config.yaml .github/workflows/update.yml
git commit -m "feat: add Instagram source config and workflow env vars"
```

---

## Activation Checklist

After all tasks are complete, these manual steps are needed before enabling:

1. **Create a new Google Sheet** for ig_maokaishungry and share it with the GCP service account
2. **Update `config.yaml`** with the real `sheet_id` and set `enabled: true`
3. **Enable Places API (New)** in GCP console
4. **Create a Google Places API key** (restrict to Places API)
5. **Add GitHub Secrets**: `ANTHROPIC_API_KEY`, `GOOGLE_PLACES_API_KEY`
6. **Run `workflow_dispatch`** to trigger backfill of all 782 posts
