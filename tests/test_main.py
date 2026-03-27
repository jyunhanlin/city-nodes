import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from main import run_source


@pytest.mark.asyncio
@patch("main.notify_update", new_callable=AsyncMock)
@patch("main.update_sheet")
@patch("main.write_data")
@patch("main.write_state")
@patch("main.read_data", return_value=[])
@patch("main.read_state", return_value={})
async def test_run_source_first_run(
    mock_read_state,
    mock_read_data,
    mock_write_state,
    mock_write_data,
    mock_update_sheet,
    mock_notify,
):
    source = AsyncMock()
    source.name = "test_source"
    source.check.return_value = True
    source.fetch.return_value = (
        [{"name": "A", "address": "A", "lat": 25.0, "lng": 121.0, "category": "test", "note": ""}],
        {"etag": "new", "data_hash": "abc"},
    )

    config = {"sheet_id": "sid", "sheet_name": "Sheet1"}

    settings = MagicMock()
    settings.google_service_account_key = '{"type":"test"}'
    settings.github_token = "ghp_test"
    settings.github_repository = "user/repo"

    gs_client = MagicMock()
    await run_source(source, config, settings, gs_client)

    source.check.assert_called_once_with({})
    source.fetch.assert_called_once()
    mock_update_sheet.assert_called_once()
    mock_notify.assert_called_once()
    mock_write_state.assert_called_once()
    mock_write_data.assert_called_once()


@pytest.mark.asyncio
@patch("main.read_state", return_value={"etag": "old"})
async def test_run_source_skips_when_no_update(mock_read_state):
    source = AsyncMock()
    source.name = "test_source"
    source.check.return_value = False

    config = {"sheet_id": "sid", "sheet_name": "Sheet1"}
    settings = MagicMock()
    gs_client = MagicMock()

    await run_source(source, config, settings, gs_client)

    source.check.assert_called_once()
    source.fetch.assert_not_called()
