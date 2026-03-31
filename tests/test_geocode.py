import httpx
import pytest
import respx

from pipeline.geocode import PLACES_TEXT_SEARCH_URL, geocode_location


@respx.mock
@pytest.mark.asyncio
async def test_geocode_location_returns_source_item():
    respx.post(PLACES_TEXT_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "places": [
                    {
                        "formattedAddress": "台北市信義區松仁路8號",
                        "location": {"latitude": 25.0336, "longitude": 121.5678},
                    }
                ]
            },
        )
    )

    result = await geocode_location(
        "一蘭拉麵", "信義區", api_key="test-key", category="restaurant"
    )

    assert result is not None
    assert result["name"] == "一蘭拉麵"
    assert result["address"] == "台北市信義區松仁路8號"
    assert result["lat"] == 25.0336
    assert result["lng"] == 121.5678
    assert result["category"] == "restaurant"
    assert result["note"] == ""


@respx.mock
@pytest.mark.asyncio
async def test_geocode_location_returns_none_when_no_results():
    respx.post(PLACES_TEXT_SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"places": []})
    )

    result = await geocode_location(
        "不存在的地方", "", api_key="test-key", category="restaurant"
    )

    assert result is None


@respx.mock
@pytest.mark.asyncio
async def test_geocode_location_builds_query_with_area():
    route = respx.post(PLACES_TEXT_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "places": [
                    {
                        "formattedAddress": "addr",
                        "location": {"latitude": 25.0, "longitude": 121.0},
                    }
                ]
            },
        )
    )

    await geocode_location("鼎泰豐", "大安區", api_key="k", category="restaurant")

    request_body = route.calls[0].request
    import json
    body = json.loads(request_body.content)
    assert body["textQuery"] == "鼎泰豐 大安區"
    assert body["languageCode"] == "zh-TW"
