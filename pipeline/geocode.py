from __future__ import annotations

import logging

import httpx

from sources.base import SourceItem

logger = logging.getLogger(__name__)

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"


async def geocode_location(
    name: str,
    area: str,
    *,
    api_key: str,
    category: str = "",
) -> SourceItem | None:
    """Look up a location by name using Google Places Text Search API.

    Returns a SourceItem with address and coordinates, or None if not found.
    """
    query = f"{name} {area}" if area else name
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            PLACES_TEXT_SEARCH_URL,
            headers={
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "places.formattedAddress,places.location",
            },
            json={"textQuery": query, "languageCode": "zh-TW"},
        )
    resp.raise_for_status()
    places = resp.json().get("places", [])
    if not places:
        logger.warning(f"Geocode: no results for '{query}'")
        return None

    place = places[0]
    return {
        "name": name,
        "address": place["formattedAddress"],
        "lat": place["location"]["latitude"],
        "lng": place["location"]["longitude"],
        "category": category,
        "note": "",
    }
