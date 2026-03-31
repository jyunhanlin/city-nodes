import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sources.instagram import InstagramSource


@pytest.fixture
def ig_source(tmp_path):
    settings = MagicMock()
    settings.anthropic_api_key = "test-anthropic-key"
    settings.google_places_api_key = "test-places-key"
    return InstagramSource(
        name="ig_test",
        target="testaccount",
        category="restaurant",
        settings=settings,
        state_dir=tmp_path,
    )


@pytest.mark.asyncio
async def test_check_always_returns_true(ig_source):
    assert await ig_source.check({}) is True
    assert await ig_source.check({"last_post_timestamp": "2026-03-20T00:00:00+00:00"}) is True


def test_merge_extracted(ig_source):
    existing = [
        {"name": "一蘭拉麵", "area": "信義區", "source_posts": ["p1"]},
        {"name": "鼎泰豐", "area": "", "source_posts": ["p1"]},
    ]
    new = [
        {"name": "一蘭拉麵", "area": "信義區", "source_posts": ["p2"]},
        {"name": "CoCo", "area": "大安區", "source_posts": ["p2"]},
    ]

    merged = ig_source._merge_extracted(existing, new)

    by_name = {loc["name"]: loc for loc in merged}
    assert len(by_name) == 3
    assert set(by_name["一蘭拉麵"]["source_posts"]) == {"p1", "p2"}
    assert by_name["鼎泰豐"]["source_posts"] == ["p1"]
    assert by_name["CoCo"]["source_posts"] == ["p2"]


@pytest.mark.asyncio
@patch("sources.instagram.geocode_location", new_callable=AsyncMock)
@patch("sources.instagram.extract_locations", new_callable=AsyncMock)
async def test_fetch_first_run(mock_extract, mock_geocode, ig_source):
    """First run: no caches, all steps execute."""
    ig_source._scrape = AsyncMock(
        return_value=[
            {
                "shortcode": "abc123",
                "caption": "好吃的拉麵",
                "timestamp": "2026-03-20T12:00:00+00:00",
                "location_name": "",
                "location_lat": None,
                "location_lng": None,
            }
        ]
    )
    mock_extract.return_value = [
        {"post_shortcode": "abc123", "name": "一蘭拉麵", "area": "信義區"}
    ]
    mock_geocode.return_value = {
        "name": "一蘭拉麵",
        "address": "台北市信義區松仁路8號",
        "lat": 25.0336,
        "lng": 121.5678,
        "category": "restaurant",
        "note": "",
    }

    await ig_source.check({})
    items, new_state = await ig_source.fetch()

    assert len(items) == 1
    assert items[0]["name"] == "一蘭拉麵"
    assert items[0]["address"] == "台北市信義區松仁路8號"
    assert items[0]["lat"] == 25.0336
    assert items[0]["category"] == "restaurant"
    assert new_state["last_post_timestamp"] == "2026-03-20T12:00:00+00:00"

    mock_extract.assert_called_once()
    mock_geocode.assert_called_once()


@pytest.mark.asyncio
@patch("sources.instagram.geocode_location", new_callable=AsyncMock)
@patch("sources.instagram.extract_locations", new_callable=AsyncMock)
async def test_fetch_incremental_skips_cached(
    mock_extract, mock_geocode, ig_source
):
    """Incremental: cached posts are not re-extracted, cached locations not re-geocoded."""
    # Pre-populate caches
    ig_source._write_cache(
        "posts",
        [
            {
                "shortcode": "old1",
                "caption": "old post",
                "timestamp": "2026-03-10T00:00:00+00:00",
                "location_name": "",
                "location_lat": None,
                "location_lng": None,
            }
        ],
    )
    ig_source._write_cache(
        "extracted",
        [{"name": "舊店", "area": "", "source_posts": ["old1"]}],
    )
    ig_source._write_cache(
        "geocoded",
        [
            {
                "name": "舊店",
                "address": "舊地址",
                "lat": 25.0,
                "lng": 121.0,
                "category": "restaurant",
                "note": "",
            }
        ],
    )

    # Scrape returns one new post
    ig_source._scrape = AsyncMock(
        return_value=[
            {
                "shortcode": "new1",
                "caption": "new post",
                "timestamp": "2026-03-25T00:00:00+00:00",
                "location_name": "",
                "location_lat": None,
                "location_lng": None,
            }
        ]
    )

    # Extract only processes the new post
    mock_extract.return_value = [
        {"post_shortcode": "new1", "name": "新店", "area": "中山區"}
    ]

    # Geocode is only called for "新店" (舊店 is already in geocode cache)
    mock_geocode.return_value = {
        "name": "新店",
        "address": "新地址",
        "lat": 25.1,
        "lng": 121.1,
        "category": "restaurant",
        "note": "",
    }

    await ig_source.check({"last_post_timestamp": "2026-03-10T00:00:00+00:00"})
    items, new_state = await ig_source.fetch()

    assert len(items) == 2
    names = {item["name"] for item in items}
    assert names == {"舊店", "新店"}

    # Extract was called only with the new post
    extract_call_posts = mock_extract.call_args[0][0]
    assert len(extract_call_posts) == 1
    assert extract_call_posts[0]["shortcode"] == "new1"

    # Geocode was called only once (for 新店)
    mock_geocode.assert_called_once()
    assert mock_geocode.call_args[0][0] == "新店"


@pytest.mark.asyncio
@patch("sources.instagram.geocode_location", new_callable=AsyncMock)
@patch("sources.instagram.extract_locations", new_callable=AsyncMock)
async def test_fetch_dedup_by_address(mock_extract, mock_geocode, ig_source):
    """Two different names that resolve to the same address should be deduped."""
    ig_source._scrape = AsyncMock(
        return_value=[
            {
                "shortcode": "p1",
                "caption": "一蘭拉麵好吃",
                "timestamp": "2026-03-20T12:00:00+00:00",
                "location_name": "",
                "location_lat": None,
                "location_lng": None,
            },
            {
                "shortcode": "p2",
                "caption": "一蘭拉面 台北",
                "timestamp": "2026-03-19T12:00:00+00:00",
                "location_name": "",
                "location_lat": None,
                "location_lng": None,
            },
        ]
    )
    mock_extract.return_value = [
        {"post_shortcode": "p1", "name": "一蘭拉麵", "area": "信義區"},
        {"post_shortcode": "p2", "name": "一蘭拉面 台北", "area": ""},
    ]
    # Both names resolve to the same address via Google Places
    mock_geocode.side_effect = [
        {
            "name": "一蘭拉麵",
            "address": "台北市信義區松仁路8號",
            "lat": 25.0336,
            "lng": 121.5678,
            "category": "restaurant",
            "note": "",
        },
        {
            "name": "一蘭拉面 台北",
            "address": "台北市信義區松仁路8號",
            "lat": 25.0336,
            "lng": 121.5678,
            "category": "restaurant",
            "note": "",
        },
    ]

    await ig_source.check({})
    items, _ = await ig_source.fetch()

    # Same address → deduped to 1 item
    assert len(items) == 1
    assert items[0]["address"] == "台北市信義區松仁路8號"
