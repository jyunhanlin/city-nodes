from pathlib import Path

from pipeline.state import read_state, write_state, read_data, write_data


def test_read_state_returns_empty_when_no_file(tmp_path):
    result = read_state("nonexistent", state_dir=tmp_path)
    assert result == {}


def test_write_and_read_state(tmp_path):
    state = {"etag": "abc:123", "data_hash": "sha256..."}
    write_state("trash_bins", state, state_dir=tmp_path)
    result = read_state("trash_bins", state_dir=tmp_path)
    assert result == state


def test_read_data_returns_empty_when_no_file(tmp_path):
    result = read_data("nonexistent", state_dir=tmp_path)
    assert result == []


def test_write_and_read_data(tmp_path):
    items = [
        {
            "name": "外交部",
            "address": "中正區中山南路外交部",
            "lat": 25.0384804,
            "lng": 121.5172055,
            "category": "trash_bin",
            "note": "備註",
        }
    ]
    write_data("trash_bins", items, state_dir=tmp_path)
    result = read_data("trash_bins", state_dir=tmp_path)
    assert result == items


def test_state_preserves_chinese_characters(tmp_path):
    state = {"memo": "測試中文"}
    write_state("test", state, state_dir=tmp_path)
    raw = (tmp_path / "test.json").read_text(encoding="utf-8")
    assert "測試中文" in raw  # not escaped as \u
