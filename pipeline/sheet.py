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
