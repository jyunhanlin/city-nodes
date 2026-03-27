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
    "a835f3ba-7f50-4b0d-91a6-9df128632d1c/resource/"
    "267d550f-c6ec-46e0-b8af-fd5a464eb098/download"
)

METADATA_URL = "https://data.gov.tw/api/v2/rest/dataset/121355"


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

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(METADATA_URL)
            resp.raise_for_status()
            modified_date = resp.json()["result"]["modifiedDate"]
        except Exception as exc:
            logger.warning(f"[{self.name}] Metadata check failed: {exc}; assuming update needed.")
            return True

        return modified_date != state.get("modified_date", "")

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
