import httpx
import pytest
import respx

from sources.trash_bins import TrashBinSource, CSV_URL, parse_csv


def test_parse_csv_returns_source_items(sample_csv_big5: bytes):
    items = parse_csv(sample_csv_big5)
    assert len(items) == 3

    first = items[0]
    assert first["name"] == "中山南路(西側)外交部"
    assert first["address"] == "中正區中山南路(西側)外交部"
    assert first["lat"] == 25.0384804
    assert first["lng"] == 121.5172055
    assert first["category"] == "trash_bin"
    assert "嚴禁" in first["note"]


def test_parse_csv_skips_rows_with_bad_coordinates():
    bad_csv = "行政區,地址,經度,緯度,備註,\n中正區,某處,not_a_number,25.0,備註,\n".encode("big5")
    items = parse_csv(bad_csv)
    assert len(items) == 0


@respx.mock
@pytest.mark.asyncio
async def test_check_returns_true_on_first_run():
    respx.head(CSV_URL).mock(
        return_value=httpx.Response(200, headers={"last-modified": "Mon, 01 Jan 2026"})
    )
    source = TrashBinSource()
    assert await source.check({}) is True


@respx.mock
@pytest.mark.asyncio
async def test_check_returns_false_when_unchanged():
    respx.head(CSV_URL).mock(
        return_value=httpx.Response(
            200, headers={"last-modified": "Mon, 01 Jan 2026", "content-length": "500"}
        )
    )
    source = TrashBinSource()
    state = {"etag": "Mon, 01 Jan 2026:500"}
    assert await source.check(state) is False


@respx.mock
@pytest.mark.asyncio
async def test_check_returns_true_when_changed():
    respx.head(CSV_URL).mock(
        return_value=httpx.Response(
            200, headers={"last-modified": "Tue, 02 Jan 2026", "content-length": "600"}
        )
    )
    source = TrashBinSource()
    state = {"etag": "Mon, 01 Jan 2026:500"}
    assert await source.check(state) is True


@respx.mock
@pytest.mark.asyncio
async def test_fetch_returns_items_and_new_state(sample_csv_big5: bytes):
    respx.get(CSV_URL).mock(
        return_value=httpx.Response(
            200,
            content=sample_csv_big5,
            headers={"last-modified": "Mon, 01 Jan 2026", "content-length": "500"},
        )
    )
    source = TrashBinSource()
    items, new_state = await source.fetch()

    assert len(items) == 3
    assert items[0]["category"] == "trash_bin"
    assert "etag" in new_state
    assert "data_hash" in new_state
