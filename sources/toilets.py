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
