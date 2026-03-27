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
