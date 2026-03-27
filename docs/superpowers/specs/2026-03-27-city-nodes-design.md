# City Nodes — 城市節點地圖資料管線

## 概述

自動化抓取政府開放資料（及未來的爬蟲等來源），更新 Google Sheet，讓使用者在 Google My Maps 上手動重新匯入即可看到最新標記。

**目標：**
- 個人使用 + 可分享固定連結給朋友
- 留在 Google Maps 生態系內（app + web 都能開）
- 半自動更新：GitHub Actions 偵測新版本 → 更新 Google Sheet → 開 Issue 通知 → 手動在 My Maps 點「重新匯入並合併」

## 架構

### Design Pattern：Strategy Pattern

每個資料來源是一個 Strategy，實作相同介面。共用 pipeline 負責 diff 偵測、Sheet 更新、通知。來源之間平行執行，互不影響。

### 資料流

```
GitHub Actions (每週一 cron / 手動觸發)
│
├─ main.py
│  ├─ 讀 config.yaml → 找到所有 enabled sources
│  ├─ asyncio.gather 平行跑每個 source:
│  │   ├─ check()        → 讀 state/*.json + 探測來源，判斷有無更新
│  │   │   └─ 沒更新 → log + 跳過
│  │   ├─ fetch()        → 下載 + 正規化為 list[SourceItem]
│  │   ├─ diff()         → 比對新舊資料，產出變更摘要
│  │   ├─ sheet.update() → 全量覆蓋 Google Sheet
│  │   ├─ notify()       → 開 GitHub Issue 通知
│  │   └─ state 更新     → 寫入 state/*.json
│  └─ 完成
│
├─ git commit + push state/ 變更（bot 帳號）
│
▼ 使用者收到 GitHub Issue 通知
▼ 到 Google My Maps 點「重新匯入並合併」
▼ 完成
```

## 專案結構

```
city-nodes/
├── sources/                     # 資料來源模組
│   ├── __init__.py
│   ├── base.py                  # DataSource Protocol + SourceItem 定義
│   └── trash_bins.py            # 清潔桶（台北市政府開放資料）
├── pipeline/                    # 共用 pipeline
│   ├── __init__.py
│   ├── diff.py                  # 變更偵測 + 產出摘要
│   ├── sheet.py                 # Google Sheets 全量覆蓋
│   └── notify.py                # GitHub Issue 通知
├── state/                       # 來源狀態（git tracked）
│   └── trash_bins.json          # {"last_modified": "...", "data_hash": "..."}
├── config.yaml                  # 來源設定（Sheet ID、啟用/停用）
├── main.py                      # 進入點
├── pyproject.toml               # uv 管理依賴 + 專案設定
├── uv.lock                      # 鎖定版本（git tracked）
├── .python-version              # 固定 Python 版本
├── .env                         # 本地環境變數（gitignore）
├── .gitignore
├── .github/
│   └── workflows/
│       └── update.yml           # GitHub Actions cron
└── README.md
```

## 介面定義

### DataSource Protocol

```python
# sources/base.py
from typing import Protocol, TypedDict

class SourceItem(TypedDict):
    name: str        # 標記名稱
    address: str     # 地址
    lat: float       # 緯度
    lng: float       # 經度
    category: str    # 類別（"trash_bin", "toilet" 等）
    note: str        # 備註

class DataSource(Protocol):
    name: str

    async def check(self) -> bool:
        """輕量探測，回傳 True 表示有更新"""
        ...

    async def fetch(self) -> list[SourceItem]:
        """完整抓取 + 正規化為統一格式"""
        ...
```

> 使用 async 介面搭配 httpx 的 AsyncClient，讓 asyncio.gather 能真正平行執行多個 source 的 HTTP 請求。

### Check 策略

每個來源的 check() 可用不同策略偵測更新：

| 來源類型 | check 方式 | state 存什麼 |
|---------|-----------|-------------|
| 政府 CSV | HTTP HEAD 看 Last-Modified / Content-Length | last_modified, data_hash |
| 爬蟲 | 頁面上的更新時間戳 | last_updated, data_hash |
| 通用 fallback | 下載後算 hash 比對 | data_hash |

State 格式範例：
```json
{
  "last_modified": "2026-03-15T08:00:00Z",
  "data_hash": "a1b2c3d4e5f6..."
}
```

## 第一個資料來源：清潔桶

- **來源**：台北市行人專用清潔箱
- **資料頁**：https://data.gov.tw/dataset/121355
- **下載 URL**：https://data.taipei/api/dataset/a835f3ba-7f50-4b0d-91a6-9df128632d1c/resource/267d550f-c6ec-46e0-b8af-fd5a464eb098/download
- **格式**：CSV，Big5 編碼
- **欄位**：行政區, 地址, 經度, 緯度, 備註
- **資料量**：約 1506 筆
- **正規化映射**：
  - `name` ← 地址
  - `address` ← 行政區 + 地址
  - `lat` ← 緯度
  - `lng` ← 經度
  - `category` ← "trash_bin"
  - `note` ← 備註

## Pipeline 模組

### diff.py

比對新舊資料，產出 DiffResult：
- 新增數量
- 刪除數量
- 變更數量（地址或座標改變）
- 變更摘要文字（給 notify 用）

比對方式：以 `(lat, lng)` 為 key 做 set difference。

### sheet.py

使用 gspread 全量覆蓋 Google Sheet：
1. 清空現有資料
2. 寫入 header row
3. 寫入所有資料列

全量覆蓋而非增量 — 資料量小（< 數千筆），簡單且不易出錯。

### notify.py

開 GitHub Issue 通知使用者：
- 標題：`[city-nodes] {source_name} 資料更新`
- 內容：變更摘要（新增/刪除/修改數量）
- 行為：有 GITHUB_TOKEN 時開 Issue，沒有時只 log

## 設定

### config.yaml

```yaml
sources:
  trash_bins:
    enabled: true
    sheet_id: "your-google-sheet-id"
    sheet_name: "工作表1"
```

### 環境變數（pydantic-settings）

```python
class Settings(BaseSettings):
    google_service_account_key: str  # Google Service Account JSON
    github_token: str = ""           # 本地可不填

    class Config:
        env_file = ".env"
```

| 環境 | 來源 |
|------|------|
| 本地開發 | `.env` 檔 |
| GitHub Actions | repo secrets → env |

### Google Sheets 認證

1. Google Cloud Console 建立 Service Account
2. 下載 JSON 金鑰，內容存入 `GOOGLE_SERVICE_ACCOUNT_KEY` 環境變數
3. Google Sheet 共用給 Service Account email

## GitHub Actions Workflow

```yaml
name: Update city nodes

on:
  schedule:
    - cron: '0 0 * * 1'   # 每週一 UTC 00:00
  workflow_dispatch:        # 手動觸發

env:
  GOOGLE_SERVICE_ACCOUNT_KEY: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_KEY }}
  GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5

      - run: uv run main.py

      - name: Commit state changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add state/
          git diff --staged --quiet || git commit -m "chore: update source states" && git push
```

## 依賴

| 套件 | 用途 |
|------|------|
| gspread | Google Sheets 操作 |
| httpx | HTTP 請求（支援 async） |
| pydantic-settings | 環境變數管理 + 驗證 |
| pyyaml | 讀 config.yaml |

## 擴充方式

新增資料來源只需：
1. 在 `sources/` 新增一個模組，實作 `DataSource` Protocol（check + fetch）
2. 在 `config.yaml` 加一筆設定
3. 在 `main.py` 註冊新 source

Pipeline（diff、sheet、notify）完全不用動。

## 限制與已知問題

- **Google My Maps 不支援自動同步 Google Sheet** — 使用者收到通知後需手動在 My Maps 點「重新匯入並合併」→「重新匯入」
- **政府資料編碼為 Big5** — fetch 時需轉換為 UTF-8
- **Google Sheets API quota** — 每 100 秒 100 次請求，1506 筆全量覆蓋完全在限制內
