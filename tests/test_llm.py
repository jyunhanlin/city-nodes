import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pipeline.llm import (
    _parse_json_response,
    deduplicate_locations,
    extract_locations,
)


def test_parse_json_response_plain():
    assert _parse_json_response('[{"a": 1}]') == [{"a": 1}]


def test_parse_json_response_code_block():
    text = '```json\n[{"a": 1}]\n```'
    assert _parse_json_response(text) == [{"a": 1}]


def test_parse_json_response_code_block_no_lang():
    text = '```\n[{"a": 1}]\n```'
    assert _parse_json_response(text) == [{"a": 1}]


@pytest.mark.asyncio
@patch("pipeline.llm.anthropic.AsyncAnthropic")
async def test_extract_locations_single_batch(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text=json.dumps(
                [
                    {"post_shortcode": "abc", "name": "一蘭拉麵", "area": "信義區"},
                    {"post_shortcode": "abc", "name": "鼎泰豐", "area": ""},
                ]
            )
        )
    ]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    posts = [{"shortcode": "abc", "caption": "今天吃一蘭拉麵跟鼎泰豐"}]
    results = await extract_locations(posts, api_key="test-key")

    assert len(results) == 2
    assert results[0]["name"] == "一蘭拉麵"
    assert results[1]["name"] == "鼎泰豐"
    mock_client.messages.create.assert_called_once()


@pytest.mark.asyncio
@patch("pipeline.llm.anthropic.AsyncAnthropic")
async def test_extract_locations_multiple_batches(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="[]")]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    # 25 posts → 2 batches (20 + 5) with EXTRACT_BATCH_SIZE=20
    posts = [{"shortcode": f"p{i}", "caption": f"post {i}"} for i in range(25)]
    await extract_locations(posts, api_key="test-key")

    assert mock_client.messages.create.call_count == 2


@pytest.mark.asyncio
@patch("pipeline.llm.anthropic.AsyncAnthropic")
async def test_extract_locations_handles_bad_json(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="not json at all")]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    posts = [{"shortcode": "abc", "caption": "test"}]
    results = await extract_locations(posts, api_key="test-key")

    assert results == []


@pytest.mark.asyncio
@patch("pipeline.llm.anthropic.AsyncAnthropic")
async def test_deduplicate_locations(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text=json.dumps(
                [
                    {
                        "canonical_name": "一蘭拉麵 台北本店",
                        "area": "信義區",
                        "source_posts": ["abc", "def"],
                    }
                ]
            )
        )
    ]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    locations = [
        {"name": "一蘭拉麵", "area": "信義區", "source_posts": ["abc"]},
        {"name": "一蘭拉面 台北", "area": "", "source_posts": ["def"]},
    ]
    results = await deduplicate_locations(locations, api_key="test-key")

    assert len(results) == 1
    assert results[0]["canonical_name"] == "一蘭拉麵 台北本店"
    assert set(results[0]["source_posts"]) == {"abc", "def"}


@pytest.mark.asyncio
async def test_deduplicate_locations_empty_input():
    results = await deduplicate_locations([], api_key="test-key")
    assert results == []


@pytest.mark.asyncio
@patch("pipeline.llm.anthropic.AsyncAnthropic")
async def test_deduplicate_locations_handles_bad_json(mock_cls):
    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="broken")]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    locations = [{"name": "A", "area": "", "source_posts": ["p1"]}]
    results = await deduplicate_locations(locations, api_key="test-key")

    # Falls back to passthrough
    assert len(results) == 1
    assert results[0]["canonical_name"] == "A"
