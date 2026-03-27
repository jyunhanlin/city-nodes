import json
from unittest.mock import MagicMock, patch

from pipeline.sheet import get_gspread_client, update_sheet


def test_update_sheet_clears_and_writes():
    mock_worksheet = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_client = MagicMock()
    mock_client.open_by_key.return_value = mock_spreadsheet

    items = [
        {
            "name": "外交部",
            "address": "中正區中山南路外交部",
            "lat": 25.038,
            "lng": 121.517,
            "category": "trash_bin",
            "note": "備註",
        }
    ]

    update_sheet(mock_client, "sheet-id-123", "工作表1", items)

    mock_client.open_by_key.assert_called_once_with("sheet-id-123")
    mock_spreadsheet.worksheet.assert_called_once_with("工作表1")
    mock_worksheet.clear.assert_called_once()
    mock_worksheet.update.assert_called_once()

    # Verify the data passed to update
    call_args = mock_worksheet.update.call_args
    rows = call_args[0][0]
    assert rows[0] == ["name", "address", "lat", "lng", "category", "note"]
    assert rows[1] == ["外交部", "中正區中山南路外交部", 25.038, 121.517, "trash_bin", "備註"]


def test_update_sheet_with_empty_items():
    mock_worksheet = MagicMock()
    mock_spreadsheet = MagicMock()
    mock_spreadsheet.worksheet.return_value = mock_worksheet
    mock_client = MagicMock()
    mock_client.open_by_key.return_value = mock_spreadsheet

    update_sheet(mock_client, "sheet-id", "Sheet1", [])

    mock_worksheet.clear.assert_called_once()
    call_args = mock_worksheet.update.call_args
    rows = call_args[0][0]
    assert len(rows) == 1  # header only


@patch("pipeline.sheet.gspread.service_account_from_dict")
def test_get_gspread_client(mock_from_dict):
    mock_from_dict.return_value = MagicMock()
    key_json = '{"type": "service_account", "project_id": "test"}'
    client = get_gspread_client(key_json)
    mock_from_dict.assert_called_once_with({"type": "service_account", "project_id": "test"})
    assert client is not None
