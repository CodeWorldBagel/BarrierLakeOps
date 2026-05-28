# BarrierLakeOps

> **堰湖態勢:跨部會即時研判元件**
> 一個以 Model Context Protocol(MCP)與 HTTP REST 雙重介面交付的工具集,協助應變單位整合堰塞湖跨部會資料、降低資料盤點負擔。隨附 Nuxt 3 reference client 示範 web 端消費方式。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP](https://img.shields.io/badge/MCP-Server-blue.svg)](https://modelcontextprotocol.io/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/Status-MVP-orange.svg)](#)
[![Team](https://img.shields.io/badge/Team-扣握貝果%20CodeWorldBagel-brightgreen.svg)](https://github.com/CodeWorldBagel)

**2026 數位發展部「防災積木元件創新賽:公民科技拼出韌性臺灣」參賽作品**
**參賽隊伍:扣握貝果(CodeWorldBagel)**

---

## 目錄

依官方建議的六段式說明結構:

1. [問題](#1-問題) — 為什麼這件事該被解決
2. [解法](#2-解法) — 我們怎麼解
3. [元件設計](#3-元件設計) — 元件長什麼樣、怎麼組
4. [使用情境](#4-使用情境) — 誰會在什麼時候用
5. [預期效益](#5-預期效益) — 用了之後會發生什麼
6. [延伸可能](#6-延伸可能) — 之後還能長成什麼

附錄:[技術選型](#a1-技術選型) · [倉庫結構](#a2-倉庫結構) · [快速開始](#a3-快速開始) · [AI 應用界線](#a4-ai-應用界線) · [資料來源與授權](#a5-資料來源與授權) · [授權](#a6-授權) · [致謝](#a7-致謝) · [競賽資訊](#a8-競賽資訊)

---

## 1. 問題

2025 年 9 月 23 日,花蓮馬太鞍溪堰塞湖溢流潰壩,造成 19 人死亡、5 人失聯、157 人受傷,1,837 戶受影響。事後檢討揭露此次災害的關鍵失靈點之一是「**跨部會資料無法即時匯流**」:

- 堰塞湖蓄水位在林業及自然保育署相關系統
- 上游雨量在中央氣象署
- 下游淹水預測在水利署
- 撤離名冊在縣府 EMIC

**沒有任何一處能一次看完全貌**。台大模擬的疏散範圍從約 700 人擴大到 1,800 戶,距災害發生僅剩約 2 天。

而**馬太鞍不是孤例**。2024 年花蓮強震後,中央山脈大範圍山體鬆動,陸續形成多處堰塞湖;農業部林業及自然保育署目前已開放 25 筆「國有林堰塞湖」資訊。每出現一個新堰塞湖,應變單位就要重做一次跨部會盤點工作。

### Persona

> **王大明,42 歲,花蓮縣府災害應變中心輪值人員**
>
> 颱風期間,他在中心同時要看多套系統:CWA 雨量、水利署水位、堰塞湖蓄水監測、農村署土石流警戒、縣府自家災情系統。每個系統登入方式不同、欄位不一致,須靠 LINE 群組請各局處同仁協助回報數據才能拼出全貌。當紅色警戒發布、需於有限時間內向指揮官提報「潰壩可能影響哪些村里、多少人」時,這種以人腦串接的工作方式極易在夜班疲勞情境下漏接關鍵資料。

---

## 2. 解法

BarrierLakeOps 是一個遵循 **Model Context Protocol(MCP)** 標準的工具伺服器,把堰塞湖態勢研判所需的跨部會資料封裝為**可被 AI Agent 多步驟調用的標準工具集**。

**核心設計理念**:

1. **不重新發明資料**,而是把分散的官方開放資料以一致介面對外暴露
2. **不取代人類決策**,而是把資料盤點這件機械工作交給機器
3. **不綁定單一事件**,以 Lake Catalog 設定檔驅動,新增堰塞湖只需加一筆設定
4. **不綁定單一介面**,以 MCP 與 HTTP REST 雙介面交付,讓 AI 助理、web app、CLI 皆可消費同一組 Tool 邏輯

**為什麼用 MCP?**

> 把 MCP 想成「**AI 助理的 USB-C**」 — 任何支援 MCP 的 AI Agent(Claude Desktop、Cursor、未來的政府智慧助手)都能直接掛上 BarrierLakeOps,以自然語言詢問就能取得跨部會態勢資料,無須各自重寫整合 code。

---

## 3. 元件設計

### 3.1 架構總覽

```
┌─────────────────────┐   ┌────────────────────┐
│  AI Agent           │   │  Nuxt 3 前端       │
│ (Claude Desktop /   │   │  (Reference Client)│
│  Cursor / 政府AI)   │   │  儀表板 + Chat UI  │
└──────────┬──────────┘   └─────────┬──────────┘
           │ MCP (stdio/HTTP)       │ REST + SSE
           │                        │
           ▼                        ▼
┌───────────────────────────────────────────────────┐
│         BarrierLakeOps(MCP + REST 雙介面)        │
│  ┌─────────────────────────────────────────┐      │
│  │  Tool 0: list_lakes                     │      │
│  │  Tool 1: get_lake_status                │      │
│  │  Tool 2: get_upstream_weather           │      │
│  │  Tool 3: estimate_inundation            │      │
│  │  Tool 4: get_affected_population        │      │
│  │  Tool 5: compose_briefing               │      │
│  └─────────────────────────────────────────┘      │
│              ▲                                    │
│   ┌──────────┴───────────────┐                    │
│   │  Lake Catalog (YAML)     │                    │
│   │  Adapter 介面(可擴展):    │                    │
│   │  ├─ data.moa adapter     │                    │
│   │  ├─ Qlake adapter        │                    │
│   │  └─ NCDR adapter (預留)  │                    │
│   └──────────────────────────┘                    │
└────┬──────┬──────┬──────┬──────┬──────────────────┘
     │      │      │      │      │
     ▼      ▼      ▼      ▼      ▼
  data.moa CWA   NLSC DEM 戶政    LLM
          雨量  + OSM   村里    (摘要)
```

### 3.2 Tool 規格速覽

| Tool | 功能 | 主要輸入 | 主要輸出 |
|---|---|---|---|
| `list_lakes` | 列出所有可查詢堰塞湖 | `status_filter` | 湖清單 |
| `get_lake_status` | 取得指定堰塞湖即時狀態 | `lake_id` | 水位、蓄水量、距溢流距離 |
| `get_upstream_weather` | 上游集水區雨量與預報 | `lake_id`, 時間窗 | 雨量站、預報、警戒等級 |
| `estimate_inundation` | 潰壩淹水範圍推估 | `lake_id`, 情境 | GeoJSON Polygon + 屬性 |
| `get_affected_population` | 影響人口與弱勢分布 | 淹水 polygon | 村里、戶數、老幼比例 |
| `compose_briefing` | LLM 態勢摘要生成 | 前述工具回傳 | 結構化摘要 |

完整 I/O JSON Schema 將於後續版本提供 OpenAPI(Swagger)文件。

### 3.3 關鍵設計:Lake Catalog + Adapter 介面

**Lake Catalog**(YAML)描述每個堰塞湖的 id、座標、流域、警戒值、對應上游雨量站、下游 DEM 範圍。新增堰塞湖只需加一筆設定,**不需修改任何程式碼**。

**Adapter 介面**確保資料源層可隨時擴展。MVP 階段接入 `data.moa` 與 `Qlake`;架構保留 NCDR Datahub 等延伸選項可於未來啟用。

```yaml
# lake_catalog.yaml(範例)
lakes:
  - id: "mataian-2025"
    name_zh: "馬太鞍溪堰塞湖"
    formed_at: "2025-07-22"
    location:
      centroid: [121.4567, 23.6789]
    threshold:
      overflow_elevation_m: 250.0
      red_alert_headroom_m: 30.0
    upstream_weather:
      cwa_stations: ["C0Z100", "C0T9A0"]
    downstream_dem_bbox: [121.40, 23.60, 121.50, 23.70]
```

> 技術選型細節整理於 [附錄 A1](#a1-技術選型)。

---

## 4. 使用情境

### 情境 A:全台堰塞湖風險概覽

應變中心輪值人員在 Claude Desktop 詢問:

> 「請列出目前監測中的堰塞湖,並按風險等級排序。」

Agent 自動規劃並執行:

1. `list_lakes(status_filter="active")` — 取得所有監測中堰塞湖
2. 對每個湖呼叫 `get_lake_status(lake_id)` — 取得即時狀態
3. `compose_briefing(audience="multi_lake_overview")` — 生成風險排序矩陣

### 情境 B:單一堰塞湖深入分析

緊隨情境 A 之後,詢問:

> 「請針對馬太鞍溪堰塞湖深入分析,假設今天是 2025/9/22 早上紅色警戒。」

Agent 自動:

1. `get_lake_status` → 取得水位與溢流距離
2. `get_upstream_weather` → 取得降雨預報
3. (條件式)若 headroom 偏低且預報雨量偏高 → `estimate_inundation` → `get_affected_population`
4. `compose_briefing(audience="command_center")` → 生成指揮官態勢摘要

### 情境 C:web 儀表板與 Chat UI

對未掛載 MCP 的單位(如不便部署 Claude Desktop 的縣府人員),`web_demo/` 提供一個 Reference Client 範例:

* **左側**:目前監測中的堰塞湖清單,標示警戒等級
* **中央**:地圖視圖,顯示堰塞湖位置 marker、點選後渲染淹水範圍 polygon
* **右側**:Chat UI,使用者輸入自然語言問題(如「光復鄉今晚要不要撤?」);後端 Agent 透過 LLM 串接同一組 6 個 Tool,以 SSE 即時顯示工具調用過程與結果

此 reference client 與情境 A、B **共用同一份 Tool 邏輯**,僅介面型態不同;原始碼公開於 `web_demo/`,供其他單位參考改寫成自家 UI。

---

## 5. 預期效益

* **降低跨部會盤點負擔**:應變中心人員不需切換多套系統、手動拼湊資料
* **提供可追溯的研判依據**:每筆摘要含 `data_sources` 欄位,可逐項回查原始資料
* **建立可重複使用的防災基礎建設**:不為單一事件而做,未來新堰塞湖出現只需加 catalog 設定
* **降低 AI 接入防災資料的進入門檻**:任何支援 MCP 的 Agent 都能直接使用,不需各自重寫整合 code
* **完整資料授權合規**:所有輸出皆揭露來源與授權,確保下游可開源、可商用、可衍生

---

## 6. 延伸可能

* **延伸至其他資料源**:Adapter 介面預留 NCDR Datahub 接點,可擴展至非國有林堰塞湖
* **延伸至其他災害類型**:同一架構(Catalog + Adapter + Tool)可推廣到土石流潛勢溪流、淹水潛勢區、土砂災害
* **整合 PWS 細胞廣播**:在指揮官確認後,觸發官方 PWS 推播(本元件不自動執行,僅提供決策輔助)
* **替換 Tool 3 為專業水文模型**:目前為 MVP 簡化模型,介面已標準化,未來可無痛替換為水保局或學術研究等級之專業模型
* **多語化輸出**:Tool 5 摘要可擴展為英文、印尼文、越南文等,協助外籍移工取得即時撤離資訊

---

# 附錄

## A1. 技術選型

> 本表為 MVP 階段技術棧規劃。狀態欄位:✅ 已採用(現階段已落地)、🚧 規劃中(MVP 開發期間實作)、🔮 預留(未來版本擴充)。

| 層 | 選擇 | 說明 | 狀態 |
|---|---|---|---|
| 語言 | Python 3.11+ | 與 AI/LLM 生態最密切 | 🚧 規劃中 |
| MCP 框架 | [FastMCP](https://github.com/modelcontextprotocol/python-sdk) | 官方 Python SDK | 🚧 規劃中 |
| HTTP Client | `httpx` | 支援同步/非同步呼叫外部 API | 🚧 規劃中 |
| 地理運算 | `shapely`、`geopandas` | polygon、村里界相交運算 | 🚧 規劃中 |
| 設定檔 | YAML + [Pydantic](https://docs.pydantic.dev/) schema 驗證 | Lake Catalog 可由非工程師維護 | 🚧 規劃中 |
| 本地 cache | SQLite + 內建 DEM/村里界檔案 | MVP 階段不依賴外部 DB | 🚧 規劃中 |
| LLM(Tool 5) | Anthropic Claude API(可替換 OpenAI) | 態勢摘要生成 | 🚧 規劃中 |
| 文件 | OpenAPI(Swagger)+ Markdown | 供其他系統以 HTTP 方式整合 | 🚧 規劃中 |
| HTTP API | FastAPI(與 FastMCP 共用 Pydantic schema) | 同元件以 REST 形式同時暴露,供 web 前端消費 | 🚧 規劃中 |
| 前端框架 | Nuxt 3(Vue 3) | Reference Client,示範 web 端消費 MCP 元件 | 🚧 規劃中 |
| 地圖視覺化 | Leaflet + OpenStreetMap tile | GeoJSON polygon、堰塞湖位置 marker | 🚧 規劃中 |
| Chat 串流 | Server-Sent Events(SSE) | LLM Agent 工具調用過程即時顯示 | 🚧 規劃中 |
| 部署 | Docker + `docker-compose.yml`(雙服務) | 機關內網或雲端皆可獨立部署 | 🚧 規劃中 |
| 版控 | [GitHub 公開 repo](https://github.com/CodeWorldBagel/BarrierLakeOps),MIT 授權 | 符合競賽簡章 §8(三)開源規範 | ✅ 已採用 |

---

## A2. 倉庫結構

下列資料夾名稱皆連結至 GitHub 上對應路徑;標註「規劃中」者為 MVP 開發中,目錄尚未上線。

```
BarrierLakeOps/
├── README.md / LICENSE / .gitignore / .env.example
├── docs/                 ← 競賽提案原文與設計文件
├── mcp_server/           ← Python:6 Tools 核心 + FastMCP + FastAPI(規劃中)
│   ├── pyproject.toml
│   ├── src/barrier_lake_ops/
│   ├── tests/
│   └── Dockerfile
├── web_demo/             ← Nuxt 3 前端(Reference Client)(規劃中)
│   ├── package.json
│   ├── nuxt.config.ts
│   ├── pages/
│   ├── components/
│   └── Dockerfile
└── docker-compose.yml    ← 同時啟動 MCP/REST 服務與前端(規劃中)
```

| 路徑 | 狀態 | GitHub |
|---|---|---|
| `docs/` | ✅ 已上線 | [CodeWorldBagel/BarrierLakeOps · docs](https://github.com/CodeWorldBagel/BarrierLakeOps/tree/main/docs) |
| `mcp_server/` | 🚧 規劃中 | _MVP 開發中,將上線於 `main` branch_ |
| `web_demo/` | 🚧 規劃中 | _MVP 開發中,將上線於 `main` branch_ |
| `docker-compose.yml` | 🚧 規劃中 | _MVP 開發中_ |

---

## A3. 快速開始

> 🚧 MVP 開發中,以下為預期使用流程,實際指令將於後續版本提供。

### 環境準備

```bash
git clone git@github.com:CodeWorldBagel/BarrierLakeOps.git
cd BarrierLakeOps
cp .env.example .env  # 填入 CWA_API_KEY 等
```

### 在 Claude Desktop 中掛載

```json
// ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "barrier-lake-ops": {
      "command": "python",
      "args": ["-m", "barrier_lake_ops.server"],
      "env": { "CWA_API_KEY": "..." }
    }
  }
}
```

### 透過 Docker 部署

```bash
docker compose up -d
```

---

## A4. AI 應用界線

本元件設計時即明確劃定 AI 的使用界線,**避免過度信任**:

* **不自動下達撤離指令** — 決策權保留給人類指揮官
* **不接受外部社群媒體文本作為輸入** — 避免成為假訊息放大器
* **模型限制透明化** — Tool 3 為 MVP 簡化模型,明確標註 `model_used`、`disclaimer`
* **LLM 輸出可追溯** — Tool 5 含 `ai_confidence` 與 `data_sources_used` 完整清單
* **隱私邊界** — 人口資料採村里為最小粒度,不揭露個人資訊
* **失效降級** — 外部 API 不可用時回傳錯誤狀態,不填補虛構資料
* **Chat UI 不直接觸發行動** — 即使使用者透過聊天輸入「發撤離簡訊」「致電消防」這類請求,元件僅產出建議內容,不串接 PWS、LINE、Email 等實際發送通道;對外通知仍由人類執行
* **Chat UI 範圍限定** — 後端 Agent 之 system prompt 明確限定僅調用本元件之 6 個 Tool,不開啟通用網路搜尋或第三方資料串接,避免引入未經授權或未經驗證的資訊

---

## A5. 資料來源與授權

**MVP 主要資料源**

| 資料源 | 用途 | 授權條款 |
|---|---|---|
| [農業資料開放平臺 — 國有林堰塞湖資訊](https://data.moa.gov.tw/open_search.aspx?id=a89) | Tool 0、1 主資料源 | 政府資料開放授權條款 1.0 |
| [中央氣象署 Opendata(O-A0002、F-D0047)](https://opendata.cwa.gov.tw/) | Tool 2 主資料源 | 政府資料開放授權條款 1.0 |
| [農村水保署 246 警戒系統](https://246.ardswc.gov.tw/Services/OpenData) | Tool 2 補強 | 政府資料開放授權條款 1.0 |
| [國土測繪中心 20m DEM](https://data.gov.tw/dataset/35430) | Tool 3 主資料源 | 政府資料開放授權條款 1.0 |
| [OpenStreetMap](https://www.openstreetmap.org/) | Tool 3 河道 | ODbL,© OpenStreetMap contributors |
| [內政部 — 村里戶數、單一年齡人口](https://data.gov.tw/dataset/77132) | Tool 4 主資料源 | 政府資料開放授權條款 1.0 |
| 內政部 — 村里界 shapefile(data.gov.tw) | Tool 4 內建檔案 | 政府資料開放授權條款 1.0 |

**選用補強與延伸選項**

| 資料源 | 用途 | 啟用方式 | 授權條款 |
|---|---|---|---|
| 林業及自然保育署 Qlake 監測端點 | Tool 1 即時補強 | MVP 即啟用(註明為非官方文件端點) | — |
| [SEGIS 銀髮安居資料](https://segis.moi.gov.tw/) | Tool 4 弱勢分布加值 | 設定檔啟用 | 政府資料開放授權條款 1.0 |
| [NCDR Datahub](https://datahub.ncdr.nat.gov.tw/) | 擴展非國有林堰塞湖 | 需向 NCDR 申請 Token | 允許商用與衍生 |
| [TGOS Map API](https://api.tgos.tw/) | 底圖與圖徵展示 | Lite 版可直接使用 | 個別審核 |

所有 Tool 之 JSON 輸出皆包含 `data_sources` 欄位,標註每筆資料的來源、授權條款與 attribution 文字,確保下游使用可追溯且合規。

---

## A6. 授權

本專案以 [MIT License](LICENSE) 釋出。

依競賽簡章 §8(三)規定,得獎作品將以開源方式上架至主辦單位指定平臺,並遵循相關授權及資安規範。

---

## A7. 致謝

* 數位發展部「防災積木元件創新賽:公民科技拼出韌性臺灣」主辦方提供本作品之設計動機與情境框架
* 中央氣象署、農業部林業及自然保育署、農村水保署、國土測繪中心、內政部統計處持續開放相關防災資料
* [Model Context Protocol](https://modelcontextprotocol.io/) 提供本元件之介面標準
* OpenStreetMap 社群提供河道與道路圖層

---

## A8. 競賽資訊

| | |
|---|---|
| 競賽名稱 | 防災積木元件創新賽:公民科技拼出韌性臺灣 |
| 主辦單位 | 數位發展部 |
| 報名期限 | 中華民國 115/6/1(一)12:00 |
| 初選公告 | 115/6/5(五)17:00 |
| 最終發表 | 115/7/3(五)13:30~17:30 |
| 競賽官網 | https://civictech.moda.gov.tw/ |
| 參賽隊伍 | **扣握貝果(CodeWorldBagel)** |
| GitHub 組織 | [@CodeWorldBagel](https://github.com/CodeWorldBagel) |
| 本作品代表 | nick(@CodeWorldBagel) |

---

> *本 README 為 MVP 階段版本,將隨開發進度持續更新。*
