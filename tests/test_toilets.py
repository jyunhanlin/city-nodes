import httpx
import pytest
import respx

from sources.toilets import ToiletSource, CSV_URL, METADATA_URL, parse_csv


def test_parse_csv_returns_source_items(sample_toilet_csv: bytes):
    items = parse_csv(sample_toilet_csv)
    assert len(items) == 3

    first = items[0]
    assert first["name"] == "捷運劍潭站(淡水信義線)"
    assert first["address"] == "臺北市士林區中山北路五段65號"
    assert first["lat"] == 25.084873
    assert first["lng"] == 121.525078
    assert first["category"] == "toilet"
    assert first["note"] == "交通 / 5座 / 特優5"

    second = items[1]
    assert second["note"] == "公園綠地 / 8座 / 優等3 普通5"

    third = items[2]
    assert third["note"] == "加油站 / 3座"


def test_parse_csv_skips_rows_with_bad_coordinates():
    bad_csv = (
        "\ufeff行政區,公廁類別,公廁名稱,公廁地址,經度,緯度,管理單位,座數,特優級,優等級,普通級,改善級 ,無障礙廁座數,親子廁座數\n"
        "中正區,交通,某站,某地址,not_a_number,25.0,管理單位,3,0,0,0,0,0,0\n"
    ).encode("utf-8")
    items = parse_csv(bad_csv)
    assert len(items) == 0
