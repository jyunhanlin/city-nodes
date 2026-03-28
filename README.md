# city-nodes

Automated pipeline that syncs Taipei city infrastructure data from government open data portals to [Google My Maps](https://www.google.com/maps/d/u/0/edit?mid=17fq-GCuHQ49J_Pw7HGh_kNm21px4zyA&usp=sharing).

## How it works

```
Government Open Data (CSV)
        |
        v
   Fetch & Parse ──> Diff (added/removed/changed)
        |                       |
        v                       v
   Google Sheets         GitHub Issue (notification)
        |
        v
   Google My Maps (manual re-import)
```

The pipeline runs weekly via GitHub Actions (Monday 00:00 UTC). When data changes are detected, it updates the corresponding Google Sheet and creates a GitHub Issue to notify you to re-import in Google My Maps.

## Data sources

| Source | Dataset | Records | Portal |
|--------|---------|---------|--------|
| `trash_bins` | [行人專用清潔箱](https://data.taipei/dataset/detail?id=a835f3ba-7f50-4b0d-91a6-9df128632d1c) | ~1,500 | data.taipei |
| `toilets` | [公廁點位資訊](https://data.taipei/dataset/detail?id=ca205b54-a06f-4d84-894c-d6ab5079ce79) | ~1,500 | data.taipei |

## Adding a new source

1. Create `sources/<name>.py` implementing the `DataSource` protocol (`check()` + `fetch()`)
2. Add entry in `config.yaml` with `sheet_id` and `sheet_name`
3. Register in `main.py` `SOURCE_REGISTRY`

See `sources/trash_bins.py` or `sources/toilets.py` for reference.

## Setup

```bash
# Install dependencies
uv sync --dev

# Run tests
uv run pytest

# Run pipeline locally (requires .env with credentials)
uv run main.py
```

### Environment variables

| Variable | Description |
|----------|-------------|
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON key |
| `GITHUB_TOKEN` | GitHub token for creating issues |
| `GITHUB_REPOSITORY` | Repository in `owner/repo` format |

## Tech stack

Python 3.12, httpx, gspread, pydantic-settings, GitHub Actions
