from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

import instaloader

from pipeline.geocode import geocode_location
from pipeline.llm import deduplicate_locations, extract_locations
from sources.base import SourceItem

logger = logging.getLogger(__name__)

DEFAULT_STATE_DIR = Path("state")


class RawPost(TypedDict):
    shortcode: str
    caption: str
    timestamp: str
    location_name: str
    location_lat: float | None
    location_lng: float | None


class ExtractedLocation(TypedDict):
    name: str
    area: str
    source_posts: list[str]


class InstagramSource:
    def __init__(
        self,
        *,
        name: str,
        target: str,
        category: str = "",
        settings: Any = None,
        state_dir: Path = DEFAULT_STATE_DIR,
    ) -> None:
        self.name = name
        self.target = target
        self.category = category
        self._api_key = settings.anthropic_api_key if settings else ""
        self._places_key = settings.google_places_api_key if settings else ""
        self._state_dir = state_dir
        self._state: dict = {}

    async def check(self, state: dict) -> bool:
        self._state = state
        return True

    async def fetch(self) -> tuple[list[SourceItem], dict]:
        state = self._state

        # Step 1: Scrape new posts and merge with cached
        cached_posts = self._read_cache("posts") or []
        new_posts = await self._scrape(state)
        all_posts = new_posts + cached_posts
        if new_posts:
            self._write_cache("posts", all_posts)

        # Step 2: Extract locations from unprocessed posts
        cached_extracted: list[ExtractedLocation] = self._read_cache("extracted") or []
        processed = {sc for loc in cached_extracted for sc in loc["source_posts"]}
        unprocessed = [p for p in all_posts if p["shortcode"] not in processed]

        if unprocessed:
            new_extracted = await self._extract(unprocessed)
            all_extracted = self._merge_extracted(cached_extracted, new_extracted)
            self._write_cache("extracted", all_extracted)
        else:
            all_extracted = cached_extracted

        # Step 3: Deduplicate
        deduped = await self._deduplicate(all_extracted)
        deduped_names = {d["canonical_name"] for d in deduped}

        # Step 4: Geocode new locations (filter stale cache entries)
        geocode_cache: dict[str, SourceItem] = {
            item["name"]: item
            for item in (self._read_cache("geocoded") or [])
            if item["name"] in deduped_names
        }
        new_locs = [d for d in deduped if d["canonical_name"] not in geocode_cache]

        if new_locs:
            new_items = await self._geocode(new_locs)
            for item in new_items:
                geocode_cache[item["name"]] = item

        self._write_cache("geocoded", list(geocode_cache.values()))
        items = list(geocode_cache.values())

        # Build new state
        new_state: dict[str, str] = {}
        if all_posts:
            new_state["last_post_timestamp"] = max(
                p["timestamp"] for p in all_posts
            )

        return items, new_state

    async def _scrape(self, state: dict) -> list[RawPost]:
        """Scrape Instagram posts using Instaloader."""
        last_ts = state.get("last_post_timestamp", "")
        last_dt = datetime.fromisoformat(last_ts) if last_ts else None

        def _do_scrape() -> list[RawPost]:
            loader = instaloader.Instaloader(
                download_pictures=False,
                download_videos=False,
                download_video_thumbnails=False,
                download_comments=False,
                save_metadata=False,
            )

            if self.target.startswith("#"):
                hashtag = instaloader.Hashtag.from_name(
                    loader.context, self.target[1:]
                )
                post_iter = hashtag.get_posts()
            else:
                profile = instaloader.Profile.from_username(
                    loader.context, self.target
                )
                post_iter = profile.get_posts()

            posts: list[RawPost] = []
            for post in post_iter:
                post_dt = post.date_utc.replace(tzinfo=timezone.utc)
                if last_dt and post_dt <= last_dt:
                    break
                posts.append(
                    {
                        "shortcode": post.shortcode,
                        "caption": post.caption or "",
                        "timestamp": post_dt.isoformat(),
                        "location_name": (
                            post.location.name if post.location else ""
                        ),
                        "location_lat": (
                            post.location.lat if post.location else None
                        ),
                        "location_lng": (
                            post.location.lng if post.location else None
                        ),
                    }
                )
            return posts

        return await asyncio.to_thread(_do_scrape)

    async def _extract(self, posts: list[RawPost]) -> list[ExtractedLocation]:
        """Extract locations from post captions using LLM."""
        raw_results = await extract_locations(
            [{"shortcode": p["shortcode"], "caption": p["caption"]} for p in posts],
            api_key=self._api_key,
        )

        groups: dict[tuple[str, str], list[str]] = {}
        for r in raw_results:
            key = (r["name"], r.get("area", ""))
            groups.setdefault(key, []).append(r["post_shortcode"])

        return [
            {"name": name, "area": area, "source_posts": shortcodes}
            for (name, area), shortcodes in groups.items()
        ]

    def _merge_extracted(
        self,
        existing: list[ExtractedLocation],
        new: list[ExtractedLocation],
    ) -> list[ExtractedLocation]:
        """Merge new extracted locations into existing list."""
        merged: dict[tuple[str, str], list[str]] = {}
        for loc in existing:
            key = (loc["name"], loc["area"])
            merged.setdefault(key, []).extend(loc["source_posts"])
        for loc in new:
            key = (loc["name"], loc["area"])
            merged.setdefault(key, []).extend(loc["source_posts"])
        return [
            {"name": name, "area": area, "source_posts": sorted(set(shortcodes))}
            for (name, area), shortcodes in merged.items()
        ]

    async def _deduplicate(
        self, locations: list[ExtractedLocation]
    ) -> list[dict[str, Any]]:
        """Deduplicate locations using LLM fuzzy matching."""
        return await deduplicate_locations(locations, api_key=self._api_key)

    async def _geocode(self, locations: list[dict[str, Any]]) -> list[SourceItem]:
        """Geocode locations using Google Places API."""
        items: list[SourceItem] = []
        for loc in locations:
            name = loc["canonical_name"]
            area = loc.get("area", "")
            result = await geocode_location(
                name, area, api_key=self._places_key, category=self.category
            )
            if result:
                items.append(result)
            else:
                logger.warning(f"[{self.name}] Could not geocode: {name}")
        return items

    def _read_cache(self, suffix: str) -> list[dict] | None:
        path = self._state_dir / f"{self.name}_{suffix}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_cache(self, suffix: str, data: list[dict]) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        path = self._state_dir / f"{self.name}_{suffix}.json"
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
