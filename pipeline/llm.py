from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

EXTRACT_BATCH_SIZE = 20
EXTRACT_MODEL = "claude-haiku-4-5-20251001"
DEDUP_MODEL = "claude-haiku-4-5-20251001"


def _parse_json_response(text: str) -> Any:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # Remove opening ```json or ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


async def extract_locations(
    posts: list[dict[str, str]],
    *,
    api_key: str,
) -> list[dict[str, str]]:
    """Extract location names from Instagram post captions using Claude API.

    Args:
        posts: List of dicts with 'shortcode' and 'caption' keys.
        api_key: Anthropic API key.

    Returns:
        List of dicts with 'post_shortcode', 'name', and 'area' keys.
    """
    client = anthropic.AsyncAnthropic(api_key=api_key)
    all_results: list[dict[str, str]] = []

    for i in range(0, len(posts), EXTRACT_BATCH_SIZE):
        batch = posts[i : i + EXTRACT_BATCH_SIZE]
        captions_text = "\n---\n".join(
            f"[{p['shortcode']}]\n{p['caption']}" for p in batch
        )

        response = await client.messages.create(
            model=EXTRACT_MODEL,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "從以下 Instagram 貼文中提取地點資訊。\n"
                        "每篇貼文可能提到 0 到多個地點。回傳 JSON array。\n\n"
                        f"貼文：\n{captions_text}\n\n"
                        "回傳格式：\n"
                        '[{"post_shortcode": "...", "name": "店名", "area": "區域"}]\n\n'
                        "規則：\n"
                        "- 只提取明確的店名/地點，不要猜測\n"
                        "- 如果貼文沒有提到任何地點，跳過該篇\n"
                        "- area 填寫行政區或商圈名稱（如 caption 有提到），沒有則為空字串"
                    ),
                }
            ],
        )

        try:
            results = _parse_json_response(response.content[0].text)
            all_results.extend(results)
        except (json.JSONDecodeError, IndexError, KeyError) as exc:
            logger.warning(f"Failed to parse LLM extract response for batch {i}: {exc}")

    return all_results


async def deduplicate_locations(
    locations: list[dict[str, Any]],
    *,
    api_key: str,
) -> list[dict[str, Any]]:
    """Group duplicate location names using Claude API.

    Args:
        locations: List of dicts with 'name', 'area', and 'source_posts' keys.
        api_key: Anthropic API key.

    Returns:
        List of dicts with 'canonical_name', 'area', and 'source_posts' keys.
    """
    if not locations:
        return []

    client = anthropic.AsyncAnthropic(api_key=api_key)

    names_text = "\n".join(
        f"- {loc['name']} (area: {loc['area']}, posts: {','.join(loc['source_posts'])})"
        for loc in locations
    )

    response = await client.messages.create(
        model=DEDUP_MODEL,
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": (
                    "以下是從 Instagram 提取的地點名稱列表，\n"
                    "請將指向同一個地點的名稱分為同一組，\n"
                    "每組選出一個最正式的名稱作為代表。\n\n"
                    f"{names_text}\n\n"
                    "回傳 JSON array:\n"
                    '[{"canonical_name": "正式名稱", "area": "區域", '
                    '"source_posts": ["shortcode1", "shortcode2"]}]\n\n'
                    "規則：\n"
                    "- 合併同一地點的所有 source_posts\n"
                    "- area 取最具體的那個\n"
                    "- canonical_name 選最正式、最完整的名稱"
                ),
            }
        ],
    )

    try:
        return _parse_json_response(response.content[0].text)
    except (json.JSONDecodeError, IndexError, KeyError) as exc:
        logger.warning(f"Failed to parse dedup response: {exc}")
        return [
            {
                "canonical_name": loc["name"],
                "area": loc["area"],
                "source_posts": loc["source_posts"],
            }
            for loc in locations
        ]
