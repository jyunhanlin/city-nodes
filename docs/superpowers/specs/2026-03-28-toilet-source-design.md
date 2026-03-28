# Toilet Source Design

Add a new `ToiletSource` data source for Taipei public restroom locations, following the same pattern as `TrashBinSource`.

## Data Source

- **Dataset**: 臺北市公廁點位資訊 (Taipei City Public Restroom Location Information)
- **Portal**: [data.taipei](https://data.taipei/dataset/detail?id=ca205b54-a06f-4d84-894c-d6ab5079ce79)
- **Format**: CSV (~1,982 records)
- **CSV URL**: `https://data.taipei/api/dataset/ca205b54-a06f-4d84-894c-d6ab5079ce79/resource/9e0e6ad4-b9f9-4810-8551-0cffd1b915b3/download`
- **Metadata URL**: `https://data.gov.tw/api/v2/rest/dataset/138798` (provides `modifiedDate` for change detection)
- **Last updated**: 2026-03-04 14:40:28

## CSV Fields

Source CSV columns:

| CSV Column | Description |
|------------|-------------|
| 行政區 | Administrative district |
| 公廁類別 | Restroom category (e.g. 加油站附設) |
| 公廁名稱 | Restroom name |
| 公廁地址 | Address |
| 經度 | Longitude |
| 緯度 | Latitude |
| 管理單位 | Management unit |
| 座數 | Number of stalls |
| 特優級 | Excellent grade stall count |
| 優等級 | Good grade stall count |
| 普通級 | Standard grade stall count |
| 改善級 | Needs improvement stall count |
| 無障礙廁座數 | Accessible stall count |
| 親子廁座數 | Family restroom stall count |

## Field Mapping

| CSV Column | SourceItem Field | Notes |
|------------|-----------------|-------|
| 公廁名稱 | `name` | |
| 公廁地址 | `address` | |
| 緯度 | `lat` | |
| 經度 | `lng` | |
| _(literal)_ | `category` | Fixed value `"toilet"` |
| 公廁類別 + 座數 + grade columns | `note` | Composite field, see format below |

### Note Format

Combine category, stall count, and non-zero grade counts:

```
{公廁類別} / {座數}座 / {non-zero grades}
```

Examples:
- `加油站附設 / 5座 / 特優3 優等2`
- `公園綠地 / 8座 / 普通8`
- `捷運站 / 12座` (if all grade columns are 0 or empty)

## Changes

### New file: `sources/toilets.py`

- `CSV_URL` and `METADATA_URL` constants
- `parse_csv(raw: bytes) -> list[SourceItem]` — parse CSV, map fields, compose `note`
  - CSV encoding: needs verification (Big5 or UTF-8); handle with fallback
- `ToiletSource` class implementing `DataSource` Protocol
  - `name = "toilets"`
  - `check(state)` — compare `modifiedDate` from metadata API (same logic as `TrashBinSource`)
  - `fetch()` — download CSV, parse, return items + new state

### Modified: `config.yaml`

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
```

### Modified: `main.py`

Add `ToiletSource` to `SOURCE_REGISTRY`:

```python
from sources.toilets import ToiletSource

SOURCE_REGISTRY: dict[str, type] = {
    "trash_bins": TrashBinSource,
    "toilets": ToiletSource,
}
```

### New file: `tests/test_toilets.py`

Mirror `test_trash_bins.py` structure:
- `test_parse_csv_returns_source_items` — verify field mapping and note composition
- `test_parse_csv_skips_rows_with_bad_coordinates`
- `test_check_returns_true_on_first_run`
- `test_check_returns_false_when_unchanged`
- `test_check_returns_true_when_changed`
- `test_fetch_returns_items_and_new_state`

### Modified: `tests/conftest.py`

Add `sample_toilet_csv` fixture with representative toilet CSV data.

### Auto-generated on first run

- `state/toilets.json` — metadata state
- `state/toilets_data.json` — cached data
