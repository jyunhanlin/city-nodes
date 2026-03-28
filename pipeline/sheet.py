from __future__ import annotations

import json
from typing import Any

import gspread

HEADER_DISPLAY = ["name", "address", "latitude", "longitude", "category", "note"]
HEADER_KEYS = ["name", "address", "lat", "lng", "category", "note"]


def get_gspread_client(service_account_key: str = "") -> gspread.Client:
    """Create a gspread client.

    - If service_account_key is provided (local dev): use JSON key directly.
    - Otherwise (CI/WIF): use default credentials from GOOGLE_APPLICATION_CREDENTIALS.
    """
    if service_account_key:
        key_dict = json.loads(service_account_key)
        return gspread.service_account_from_dict(key_dict)

    import google.auth
    from google.auth.transport.requests import Request

    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials, _ = google.auth.default(scopes=scopes)
    return gspread.authorize(credentials)


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

    rows: list[list] = [HEADER_DISPLAY]
    for item in items:
        rows.append([item[col] for col in HEADER_KEYS])

    worksheet.update(rows, value_input_option="RAW")
