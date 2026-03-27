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
async def test_notify_skips_when_no_token(capsys):
    await notify_update("trash_bins", "新增 3 筆", token="", repository="user/repo")
    captured = capsys.readouterr()
    assert "skipping" in captured.out.lower() or "skip" in captured.out.lower()


@respx.mock
@pytest.mark.asyncio
async def test_notify_skips_when_no_repository(capsys):
    await notify_update("trash_bins", "新增 3 筆", token="ghp_test", repository="")
    captured = capsys.readouterr()
    assert "skipping" in captured.out.lower() or "skip" in captured.out.lower()
