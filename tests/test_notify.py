import httpx
import pytest
import respx

from pipeline.notify import notify_update


@respx.mock
@pytest.mark.asyncio
async def test_notify_creates_github_issue():
    route = respx.post("https://api.github.com/repos/user/repo/issues").mock(
        return_value=httpx.Response(201, json={"number": 42})
    )

    await notify_update("trash_bins", "新增 3 筆", token="ghp_test", repository="user/repo")

    assert route.called
    import json

    payload = json.loads(route.calls[0].request.content)
    assert "trash_bins" in payload["title"]
    assert "新增 3 筆" in payload["body"]


@respx.mock
@pytest.mark.asyncio
async def test_notify_skips_when_no_token(caplog):
    import logging
    with caplog.at_level(logging.INFO, logger="pipeline.notify"):
        await notify_update("trash_bins", "新增 3 筆", token="", repository="user/repo")
    assert any("skipping" in record.message.lower() or "skip" in record.message.lower() for record in caplog.records)


@respx.mock
@pytest.mark.asyncio
async def test_notify_skips_when_no_repository(caplog):
    import logging
    with caplog.at_level(logging.INFO, logger="pipeline.notify"):
        await notify_update("trash_bins", "新增 3 筆", token="ghp_test", repository="")
    assert any("skipping" in record.message.lower() or "skip" in record.message.lower() for record in caplog.records)
