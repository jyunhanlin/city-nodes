# Instagram Source Design

Add a new `InstagramSource` data source that scrapes public Instagram accounts/hashtags, extracts location names via LLM, geocodes them via Google Places API, and outputs `SourceItem` records compatible with the existing pipeline.

## Overview

```
Instagram (public account/hashtag)
    │  Instaloader
    ▼
Raw Posts (caption, location tag, timestamp)
    │  Claude API (batch extraction)
    ▼
Extracted Locations (name, area)
    │  Fuzzy dedup via LLM
    ▼
Unique Locations
    │  Google Places Text Search
    ▼
list[SourceItem] → existing pipeline (diff → sheet → notify)
```

## First Target

- **Account**: [maokaishungry](https://www.instagram.com/maokaishungry/) (~782 posts, food blogger)
- **Category**: `restaurant`
- **Schedule**: Weekly (same as existing sources)
- **Backfill**: All existing posts on first run, incremental afterwards

## Data Structures

### RawPost

Intermediate structure from Instaloader scrape:

| Field | Type | Description |
|-------|------|-------------|
| `shortcode` | `str` | IG post ID (e.g. `"CxYz123"`) |
| `caption` | `str` | Post caption text |
| `timestamp` | `str` | ISO 8601 datetime |
| `location_name` | `str` | IG location tag name (empty if none) |
| `location_lat` | `float \| None` | Tagged latitude (often `None`) |
| `location_lng` | `float \| None` | Tagged longitude (often `None`) |

### ExtractedLocation

Intermediate structure from LLM extraction:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Location name (e.g. `"一蘭拉麵 台北本店"`) |
| `area` | `str` | District/area if mentioned (e.g. `"信義區"`) |
| `source_posts` | `list[str]` | Shortcodes of posts that reference this location |

### Output: SourceItem

| SourceItem Field | Source | Notes |
|-----------------|--------|-------|
| `name` | `ExtractedLocation.name` | Canonical name from LLM dedup |
| `address` | Google Places API | `formattedAddress` |
| `lat` | Google Places API | `location.latitude` |
| `lng` | Google Places API | `location.longitude` |
| `category` | `config.yaml` | e.g. `"restaurant"` |
| `note` | — | Empty string |

## InstagramSource.check(state)

Unlike government data sources that have a metadata API, Instagram has no lightweight "has new data?" endpoint. Strategy:

- **First run** (`state` is empty): return `True`
- **Subsequent runs**: always return `True` — the scrape step itself is lightweight (stops at `last_post_timestamp`), so there's no benefit to a separate check

This keeps the `DataSource` protocol contract intact while acknowledging that IG doesn't support cheap change detection.

## Settings Access

The current `DataSource` protocol does not pass `settings` to `check()` or `fetch()`. `InstagramSource` needs API keys for Claude and Google Places.

Solution: pass `settings` to `InstagramSource.__init__()` and store as instance attribute. The `create_source()` function in `main.py` already has access to settings:

```python
def create_source(name: str, config: dict, settings: Settings) -> DataSource:
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

Existing sources don't need settings at construction time, so they remain unchanged.

## Internal Pipeline (InstagramSource.fetch)

### Step 1: `_scrape(state)` — Instaloader

- Use Instaloader Python API (not CLI)
- `download_pictures=False`, `download_videos=False`, `download_comments=False`, `save_metadata=False`
- No login — public profiles only
- Incremental: stop when reaching `last_post_timestamp` from state
- First run: scrape all posts
- Output: `list[RawPost]`
- Cache: `state/{name}_posts.json`

### Step 2: `_extract(raw_posts)` — Claude API

- Batch 20 captions per API call (~40 calls for 782 posts)
- Use Claude API with JSON mode for structured output
- Posts with IG location tags are still sent to LLM (one post may mention multiple locations)
- Prompt extracts: location name, area (if mentioned in caption)
- Skip posts where LLM finds no location
- Incremental: only process new posts, merge into existing cache
- Output: `list[ExtractedLocation]`
- Cache: `state/{name}_extracted.json`

### Step 3: `_deduplicate(locations)` — Claude API

- Send all location names to LLM in one call
- LLM groups variants of the same location and picks a canonical name
- Example: `"一蘭拉麵 台北本店"` and `"一蘭拉面（台北）"` → same group
- Merge `source_posts` lists
- Runs on full list every time (fast — single LLM call)
- Output: `list[ExtractedLocation]` (deduplicated)
- No cache (pure in-memory, re-runs on full list each time)

### Step 4: `_geocode(locations)` — Google Places API

- Use Places API (New) Text Search endpoint
- Query: `"{name} {area}"` with `languageCode: "zh-TW"`
- Take first result → `formattedAddress`, `location.latitude`, `location.longitude`
- Incremental: only query new location names, cached locations read from cache
- Locations that fail to geocode are logged and skipped (not fatal)
- Output: `list[SourceItem]`
- Cache: `state/{name}_geocoded.json`

### Cache & Incremental Strategy

**First run (backfill):**
1. `_scrape()` fetches all 782 posts → cache
2. `_extract()` processes all via LLM → cache
3. `_deduplicate()` groups all names
4. `_geocode()` queries all unique locations → cache

**Subsequent runs (incremental):**
1. `_scrape()` fetches only new posts (stop at `last_post_timestamp`) → append to cache
2. `_extract()` processes only new posts → merge into cache
3. `_deduplicate()` re-runs on full list (single LLM call, cheap)
4. `_geocode()` queries only new location names → merge into cache

**Failure recovery:** Each step checks its cache before running. If step 2 failed mid-way, re-run will skip already-extracted posts.

## Config & Registry Changes

### config.yaml

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
    enabled: true
    type: instagram
    target: "maokaishungry"
    category: "restaurant"
    sheet_id: '<new Google Sheet ID>'
    sheet_name: '工作表1'
```

### main.py — Source creation

Add `TYPE_REGISTRY` for parameterized sources alongside existing `SOURCE_REGISTRY`:

```python
SOURCE_REGISTRY: dict[str, type] = {
    "trash_bins": TrashBinSource,
    "toilets": ToiletSource,
}

TYPE_REGISTRY: dict[str, type] = {
    "instagram": InstagramSource,
}

def create_source(name: str, config: dict) -> DataSource:
    if name in SOURCE_REGISTRY:
        return SOURCE_REGISTRY[name]()
    source_type = config.get("type")
    if source_type and source_type in TYPE_REGISTRY:
        return TYPE_REGISTRY[source_type](
            name=name,
            target=config["target"],
            category=config.get("category", ""),
        )
    raise ValueError(f"Unknown source: {name}")
```

Existing sources are unaffected — they have no `type` field and resolve via `SOURCE_REGISTRY`.

### settings.py

```python
class Settings(BaseSettings):
    google_service_account_key: str = ""
    github_token: str = ""
    github_repository: str = ""
    anthropic_api_key: str = ""        # new
    google_places_api_key: str = ""    # new
```

## Dependencies

### pyproject.toml additions

```toml
"instaloader>=4.15",
"anthropic>=0.80.0",
```

## GitHub Actions

### update.yml changes

Add two environment variables to the "Run pipeline" step:

```yaml
env:
  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  GOOGLE_PLACES_API_KEY: ${{ secrets.GOOGLE_PLACES_API_KEY }}
```

Add timeout to job:

```yaml
jobs:
  update:
    timeout-minutes: 30
```

### Required GitHub Secrets (new)

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key for LLM extraction |
| `GOOGLE_PLACES_API_KEY` | Google Places API key |

### GCP Setup (prerequisites)

- Enable Places API (New) in existing GCP project
- Create API key restricted to Places API

## File Changes

### New files

| File | Description |
|------|-------------|
| `sources/instagram.py` | `InstagramSource` class — scrape, orchestrate internal pipeline |
| `pipeline/llm.py` | Claude API wrapper — `extract_locations()`, `deduplicate_locations()` |
| `pipeline/geocode.py` | Google Places wrapper — `geocode_location()` |
| `tests/test_instagram.py` | InstagramSource tests |
| `tests/test_llm.py` | LLM extraction/dedup tests |
| `tests/test_geocode.py` | Geocoding tests |

### Modified files

| File | Change |
|------|--------|
| `main.py` | Add `TYPE_REGISTRY`, `create_source()`, pass settings to source |
| `config.yaml` | Add `ig_maokaishungry` entry |
| `settings.py` | Add `anthropic_api_key`, `google_places_api_key` |
| `pyproject.toml` | Add `instaloader`, `anthropic` dependencies |
| `.github/workflows/update.yml` | Add env vars, add `timeout-minutes` |

### Auto-generated on first run

| File | Description |
|------|-------------|
| `state/ig_maokaishungry.json` | Source state (`last_post_timestamp`) |
| `state/ig_maokaishungry_data.json` | Final SourceItem data (used by diff) |
| `state/ig_maokaishungry_posts.json` | Raw posts cache |
| `state/ig_maokaishungry_extracted.json` | LLM extraction cache |
| `state/ig_maokaishungry_geocoded.json` | Geocode results cache |

## Cost Estimates (backfill)

| Service | Usage | Estimated Cost |
|---------|-------|---------------|
| Claude API | ~40 extract calls + 1 dedup call | < $1 |
| Google Places API | ~200-400 unique locations | Free (within $200/month credit) |
| GitHub Actions | ~10-15 min runtime | Free (within free tier) |

## Reusability

Adding another Instagram account or hashtag requires only a new entry in `config.yaml`:

```yaml
ig_another_account:
  enabled: true
  type: instagram
  target: "another_username"   # or "#hashtag"
  category: "cafe"
  sheet_id: '<sheet id>'
  sheet_name: '工作表1'
```

No code changes needed. LLM extraction, deduplication, and geocoding logic are fully shared.
