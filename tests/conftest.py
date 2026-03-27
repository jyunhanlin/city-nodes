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
