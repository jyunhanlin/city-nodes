import pytest

# Sample CSV matching the real government data format (Big5 encoded).
# Header: 行政區,地址,經度,緯度,備註,
# Note the trailing comma — the real data has it.
SAMPLE_CSV_UTF8 = (
    "行政區,地址,經度,緯度,備註,\n"
    "中正區,中山南路(西側)外交部,121.5172055,25.0384804,嚴禁投入家用垃圾，違者重罰新臺幣6000元,\n"
    "中正區,公園路中央氣象局,121.5150107,25.0380556,嚴禁投入家用垃圾，違者重罰新臺幣6000元,\n"
    "大安區,忠孝東路四段1號,121.5434,25.0418,嚴禁投入家用垃圾，違者重罰新臺幣6000元,\n"
)

SAMPLE_CSV_BIG5 = SAMPLE_CSV_UTF8.encode("big5")


@pytest.fixture
def sample_csv_big5() -> bytes:
    return SAMPLE_CSV_BIG5


# Sample toilet CSV (UTF-8 with BOM).
# Header has trailing space on 改善級 — matches the real data.
SAMPLE_TOILET_CSV_UTF8 = (
    "\ufeff行政區,公廁類別,公廁名稱,公廁地址,經度,緯度,管理單位,座數,特優級,優等級,普通級,改善級 ,無障礙廁座數,親子廁座數\n"
    "士林區,交通,捷運劍潭站(淡水信義線),臺北市士林區中山北路五段65號,121.525078,25.084873,捷運劍潭站(夜),5,5,0,0,0,0,1\n"
    "大安區,公園綠地,大安森林公園,臺北市大安區新生南路二段1號,121.535370,25.029867,大安森林公園,8,0,3,5,0,1,1\n"
    "中正區,加油站,台亞中正站,臺北市中正區重慶南路三段15號,121.510234,25.027654,台亞中正站,3,0,0,0,0,0,0\n"
)

SAMPLE_TOILET_CSV_BYTES = SAMPLE_TOILET_CSV_UTF8.encode("utf-8")


@pytest.fixture
def sample_toilet_csv() -> bytes:
    return SAMPLE_TOILET_CSV_BYTES
