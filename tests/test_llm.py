import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pipeline.llm import (
    _parse_json_response,
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
