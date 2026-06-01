# BarrierLakeOps — 執行計劃(Execution Plan)

> 本文件是 `backend/`(FastAPI + MCP)與 `frontend/`(Nuxt 3)的落地施工藍圖。
> 設計依據為 [`../README.md`](../README.md) 與 [`./submission.md`](./submission.md),
> 目標:**今日**完成可運作 MVP、串接真實政府開放資料、推上 GitHub、部署至 Zeabur。

---

## 0. Context — 為什麼做這份計劃

README 與 submission 已把產品「要做什麼」說清楚(6 個 Tool、雙介面、Lake Catalog、AI 界線),
但兩份文件把後端稱為 `mcp_server/`、前端稱為 `web_demo/`,且**程式碼尚未存在**(均標註「🚧 規劃中」)。

本計劃要解決三件事:

1. **把抽象規格變成可施工的目錄與檔案結構**,並統一命名為 `backend/` 與 `frontend/`。
2. **替前端每個頁面定義匡線圖(wireframe)**,讓 UI 實作有依據。
3. **定義今日可達成的最小可運作範圍**:真實 API 串接 + 部署,並標明哪些運算在一天內以「真實資料 + 簡化模型」交付、哪些列為降級。

### 本次已確認的範圍決策(來自 nick)

| 項目 | 決策 |
|---|---|
| 今日範圍 | 完整可運作 MVP **+ 部署到 Zeabur** |
| 資料來源 | **全部串真實政府開放資料**(Tool 3 淹水為真實 DEM + MVP 簡化模型) |
| Chat LLM | **OpenAI**(金鑰由 nick 於需要時提供) |
| 環境變數 | `backend/.env` 與 `frontend/.env` **各自獨立**,不共用 |
| 部署方式 | frontend/backend 用 **Zeabur 原生建置**(不打包 container);DB 才用 container |
| 資料庫 | **Postgres**:持久化 `briefings`(稽核)+ `chat` 歷史。Zeabur template 部署、本機 docker-compose |
| Zeabur 專案 | 已建立空專案 `project-6a1beb20f9a5b4afba15d962`,三 service 都建在此 |
| 命名 | `backend/`(原 `mcp_server/`)、`frontend/`(原 `web_demo/`) |

---

## 1. 系統架構

```
                 ┌──────────────────────────┐
   AI Agent ───► │  backend (Python 3.11+)  │
   (MCP)         │  ┌────────────────────┐  │
                 │  │ FastMCP  (MCP/HTTP)│  │   6 Tools 共用同一份
   frontend ───► │  │ FastAPI  (REST/SSE)│  │   Pydantic schema + 邏輯
   (REST+SSE)    │  └─────────┬──────────┘  │
                 │            │ adapters     │
                 │   data.moa │ CWA │ DEM │ 戶政 │ OpenAI
                 └────────────┴──────────────┘
                              ▲
                     Lake Catalog (YAML)
```

- **一份邏輯、兩個介面**:`tools/` 為純函式;FastMCP 與 FastAPI 各自做薄包裝。
- **Adapter 介面**:每個外部資料源一個 adapter,失敗時回傳明確錯誤而非捏造資料(對應 AI 界線 §A4「失效降級」)。
- **Lake Catalog**:`lake_catalog.yaml` 驅動;新增堰塞湖只加設定不改 code。

---

## 2. 目錄結構

```
repo/
├── backend/
│   ├── .env.example / .env            # 獨立環境變數
│   ├── pyproject.toml                 # 依賴(fastapi fastmcp httpx shapely numpy pyshp openai pydantic sqlalchemy asyncpg alembic)— 無 GDAL,可原生部署
│   ├── zbpack.json / Procfile         # Zeabur 原生建置:啟動 uvicorn --host 0.0.0.0 --port $PORT(不打包 container)
│   ├── lake_catalog.yaml              # 堰塞湖設定(馬太鞍為主案例 + data.moa 25 筆)
│   ├── scripts/prep_geo.py            # 前處理:DEM→.npy、村里界 shapefile→GeoJSON(避免執行期依賴 GDAL)
│   ├── data/                          # 內建地理資料(前處理後 DEM .npy + 村里界 GeoJSON)
│   └── src/barrier_lake_ops/
│       ├── app.py                     # FastAPI app(掛 REST routes + /chat SSE)
│       ├── server.py                  # FastMCP server 進入點(MCP)
│       ├── config.py                  # pydantic-settings 讀 .env
│       ├── schemas.py                 # 6 Tool 的 I/O Pydantic models
│       ├── catalog.py                 # 載入 / 驗證 lake_catalog.yaml
│       ├── db/                        # Postgres 持久化層
│       │   ├── engine.py              # SQLAlchemy async engine(讀 DATABASE_URL)
│       │   ├── models.py              # briefings / chat_sessions / chat_messages
│       │   ├── repository.py          # save_briefing() / list_briefings() / chat CRUD
│       │   └── migrations/            # Alembic;啟動時自動 upgrade head
│       ├── tools/                     # ★ 純邏輯,MCP 與 REST 共用
│       │   ├── list_lakes.py
│       │   ├── get_lake_status.py
│       │   ├── get_upstream_weather.py
│       │   ├── estimate_inundation.py
│       │   ├── get_affected_population.py
│       │   └── compose_briefing.py
│       ├── adapters/                  # 外部資料源
│       │   ├── moa.py                 # data.moa 國有林堰塞湖
│       │   ├── cwa.py                 # 中央氣象署 O-A0002 / F-D0047
│       │   ├── qlake.py               # 林保署 Qlake 即時補強
│       │   ├── dem.py                 # NLSC 20m DEM 讀取
│       │   └── population.py          # 村里界 + 人口
│       └── agent/
│           ├── chat_agent.py          # OpenAI function-calling，串 6 Tool
│           └── AGENT.md               # 公開揭露 system prompt 與守則(submission 要求)
├── frontend/
│   ├── .env.example / .env
│   ├── package.json / nuxt.config.ts  # Zeabur 原生偵測 Nuxt,自動 build SSR(不打包 container)
│   ├── app.vue
│   ├── pages/
│   │   ├── index.vue                  # /            全台主控台
│   │   ├── lakes/[id].vue             # /lakes/:id   單湖作戰室
│   │   └── about.vue                  # /about       關於與資料來源
│   ├── components/
│   │   ├── LakeListPanel.vue          # 風險排序湖清單
│   │   ├── LakeMap.vue                # Leaflet 地圖 + marker + 淹水 polygon
│   │   ├── StatusCards.vue            # 水位 / headroom / 警戒卡片
│   │   ├── WeatherPanel.vue           # 上游雨量與預報
│   │   ├── PopulationTable.vue        # 影響村里 / 戶數 / 老幼
│   │   ├── BriefingCard.vue           # compose_briefing 結果
│   │   ├── BriefingHistory.vue        # 歷史簡報清單(GET /lakes/{id}/briefings)
│   │   ├── ChatPanel.vue              # Chat UI + SSE 工具調用流
│   │   └── AlertBadge.vue             # 警戒等級色票
│   ├── composables/
│   │   ├── useApi.ts                  # 包 $fetch，base = NUXT_PUBLIC_API_BASE
│   │   └── useChatStream.ts           # 消費 /chat 的 SSE
│   └── server/ (Nitro，可選代理)
├── docs/                              # 本計劃 + submission
├── docker-compose.yml                 # 僅本機測試用:起資料庫(若採用);app 本身不進 container
└── README.md / LICENSE / .gitignore
```

---

## 3. Backend 施工計劃

### 3.1 6 個 Tool(I/O 依 submission §二 對齊)

| # | Tool | 真實資料源 | 今日交付 |
|---|---|---|---|
| 0 | `list_lakes` | Lake Catalog + data.moa 國有林堰塞湖 | ✅ 真實 |
| 1 | `get_lake_status` | data.moa(主)+ Qlake(即時補強) | ✅ 真實;Qlake 不可用時降級為 catalog 靜態值 |
| 2 | `get_upstream_weather` | CWA O-A0002-001(觀測)+ F-D0047(預報) | ✅ 真實(需 `CWA_API_KEY`) |
| 3 | `estimate_inundation` | NLSC 20m DEM(內建)+ MVP 簡化淹沒模型 | ✅ 真實 DEM;模型標 `disclaimer` |
| 4 | `get_affected_population` | 村里界 shapefile + 單一年齡人口(內建) | ✅ 真實 shapely 相交運算 |
| 5 | `compose_briefing` | OpenAI(消化 Tool 0–4 回傳) | ✅ 真實(需 `OPENAI_API_KEY`) |

每個 Tool 輸出皆含 `data_sources[]`(來源、授權、attribution),對應 submission §二「標準化格式」。

### 3.2 雙介面

- **REST**:`GET /lakes`、`GET /lakes/{id}/status`、`GET /lakes/{id}/weather`、`POST /lakes/{id}/inundation`、`POST /population`、`POST /briefing`,自動產生 `/docs`(Swagger)。
- **持久化查詢**:`GET /lakes/{id}/briefings`(歷史簡報清單)、`GET /briefings/{id}`(重播單份 + 輸入快照)、`GET /chat/sessions/{id}`(對話歷史)。
- **MCP**:`server.py` 用 FastMCP 把同一批純函式註冊為 tool,支援 stdio 與 HTTP transport。
- **Chat(SSE)**:`POST /chat` → `chat_agent.py` 以 OpenAI function-calling 多步調用 6 Tool,逐步 `text/event-stream` 推送「工具調用 → 結果 → 最終摘要」;每輪對話與每份生成簡報寫入 Postgres。

### 3.3 失效降級(AI 界線)

外部 API 逾時或錯誤 → 回傳 `{ error, data_freshness: "stale|unavailable" }`,**不捏造數值**;Agent 在最終回應如實揭露缺漏。

### 3.4 資料庫 schema(Postgres,持久化 briefings + chat)

`compose_briefing` 每次生成都寫一列 `briefings`,**同時存輸出與驅動它的輸入快照**,提供可追溯稽核;Chat 對話寫入 `chat_sessions` / `chat_messages`。

```sql
-- 每份態勢簡報 = 一筆可追溯稽核紀錄
briefings(
  id uuid pk, lake_id text, audience text,
  status_color text, headline text,
  key_facts jsonb, recommended_actions jsonb, natural_language text,
  ai_confidence real, data_sources_used jsonb,
  input_context jsonb,          -- Tool 0–4 回傳快照(驅動此簡報的原始資料)
  model_used text, created_at timestamptz default now())

chat_sessions(id uuid pk, lake_id text, created_at timestamptz default now())

chat_messages(
  id uuid pk, session_id uuid fk→chat_sessions,
  role text,                    -- user | assistant | tool
  content text,
  tool_name text, tool_args jsonb, tool_result jsonb,
  created_at timestamptz default now())
```

- 遷移用 **Alembic**;backend 啟動時 `upgrade head`(Zeabur 首次部署即建表)。
- 連線只寫在 `backend/.env` 的 `DATABASE_URL`;frontend 不碰 DB,只透過 REST 取歷史。

---

## 4. Frontend 施工計劃 + 頁面匡線圖

設計語彙:左側湖清單 / 中央地圖 / 右側 Chat(README 情境 C)。整體採應變中心深色儀表板風格,警戒色票:🟢 綠 / 🟡 黃 / 🟠 橙 / 🔴 紅。

### 4.1 頁面 `/` — 全台主控台(Dashboard)

用途:對應**情境 A**(全台概覽、風險排序)。落地後第一眼看到的頁面。

```
┌──────────────────────────────────────────────────────────────────────┐
│  BarrierLakeOps  堰湖態勢跨部會研判              [關於]  [API 文件↗]   │  ← Header
├───────────────────────────────┬──────────────────────────────────────┤
│  監測中堰塞湖 (依風險排序)     │                                      │
│  ┌─────────────────────────┐  │            台灣地圖 (Leaflet)         │
│  │🔴 馬太鞍溪堰塞湖         │  │      ● 紅  ● 橙  ● 黃  ● 綠 marker   │
│  │   headroom 12m · 紅色   │  │                                      │
│  ├─────────────────────────┤  │         (點 marker → 飛到該湖,       │
│  │🟠 ○○溪堰塞湖            │  │          底部彈出迷你狀態卡)         │
│  │   headroom 28m · 橙色   │  │                                      │
│  ├─────────────────────────┤  │   ┌───────────────────────────┐      │
│  │🟡 ××溪堰塞湖            │  │   │ 馬太鞍溪 · 水位 248m       │      │
│  │   ...                   │  │   │ headroom 12m → 進入作戰室→ │      │
│  │  (data.moa 25 筆)       │  │   └───────────────────────────┘      │
│  └─────────────────────────┘  │                                      │
│  [全部] [active] [monitoring] │  圖例 / © OpenStreetMap              │
├───────────────────────────────┴──────────────────────────────────────┤
│  全台概覽摘要 (compose_briefing · multi_lake_overview)                 │
│  「目前 N 座監測中,1 座紅色警戒(馬太鞍溪)...」  資料來源: data.moa │
└──────────────────────────────────────────────────────────────────────┘
```
元件:`LakeListPanel` · `LakeMap` · `BriefingCard`(multi_lake_overview)。
資料:`GET /lakes` → 每湖 `GET /lakes/{id}/status` → `POST /briefing`。

### 4.2 頁面 `/lakes/[id]` — 單湖作戰室(三欄)

用途:對應**情境 B**(單湖深入分析)+ 情境 C(Chat)。本專案核心畫面。

```
┌──────────────────────────────────────────────────────────────────────┐
│  ← 返回   馬太鞍溪堰塞湖   🔴 紅色警戒   更新於 14:05 (data 8 分鐘前)  │
├──────────────────┬─────────────────────────────┬─────────────────────┤
│ 狀態面板         │   地圖 + 淹水範圍           │  Chat 作戰助手      │
│ ┌──────────────┐ │ ┌─────────────────────────┐ │ ┌─────────────────┐ │
│ │水位 248.0 m  │ │ │   Leaflet               │ │ │ 你:光復鄉今晚   │ │
│ │溢流 250.0 m  │ │ │   ● 湖位置 marker       │ │ │     要不要撤?   │ │
│ │headroom 12m🔴│ │ │   ▓ 淹水 polygon(藍)   │ │ ├─────────────────┤ │
│ └──────────────┘ │ │   ~ OSM 河道中心線      │ │ │ ⚙ 呼叫           │ │
│ ┌──────────────┐ │ │                         │ │ │  get_lake_status │ │
│ │上游雨量 (24h)│ │ │ [情境▼ 潰壩 50%/100%]   │ │ │ ✓ headroom 12m   │ │
│ │ ▁▂▅▇█ 88mm   │ │ │ [重新推估淹水]          │ │ │ ⚙ get_upstream…  │ │
│ │ 預報 橙色     │ │ └─────────────────────────┘ │ │ ✓ 預報 120mm     │ │
│ └──────────────┘ │  最大深度 3.2m · 抵達 35min │ │ ⚙ estimate_inun… │ │
│ ┌──────────────┐ │  ⚠ MVP 簡化模型,非工程級  │ │ ✓ 3 村里 / 1,837 │ │
│ │影響人口       │ │─────────────────────────────│ │                 │ │
│ │村里 3 · 戶1837│ │  態勢摘要 (BriefingCard)    │ │ 🤖 建議:光復鄉   │ │
│ │老 412 幼 156  │ │  headline / 建議行動 /      │ │  3 村里建議預警… │ │
│ └──────────────┘ │  ai_confidence / 來源       │ │ [輸入訊息…] [送]│ │
│ 資料來源 ▾       │                             │ │ ⚠ 僅產生建議,不 │ │
│                  │                             │ │  自動發送通知    │ │
└──────────────────┴─────────────────────────────┴─────────────────────┘
```
元件:`StatusCards` · `WeatherPanel` · `LakeMap`(含淹水)· `PopulationTable` · `BriefingCard` · `BriefingHistory` · `ChatPanel`(SSE)。
資料流:`status` / `weather` 先載 → 使用者選潰壩情境 → `inundation` → `population` → `briefing`;Chat 走 `POST /chat`(SSE)。
持久化:`BriefingCard` 下方「歷史簡報 ▾」摺疊區呼叫 `GET /lakes/{id}/briefings`,點任一筆 → `GET /briefings/{id}` 重播當時摘要與輸入快照;Chat 開啟既有 session 時載 `GET /chat/sessions/{id}`。
AI 界線提示常駐:Chat 底部標「僅產生建議,不自動發送通知」(對應 §A4)。

### 4.3 頁面 `/about` — 關於與資料來源

用途:競賽評審與其他單位理解元件、資料授權、AI 界線、如何掛載 MCP。

```
┌──────────────────────────────────────────────────────────────────────┐
│  關於 BarrierLakeOps                                                    │
├──────────────────────────────────────────────────────────────────────┤
│  問題 → 解法 (六段式摘要,連到 README)                                  │
│  ┌────────┬────────┬────────┬────────┬────────┬────────┐               │
│  │list_   │get_lake│get_up… │estimate│get_aff…│compose │  6 Tool 卡片  │
│  │lakes   │_status │weather │_inund. │_pop.   │_brief. │  (I/O 速覽)   │
│  └────────┴────────┴────────┴────────┴────────┴────────┘               │
│                                                                        │
│  資料來源與授權 (表格: 來源 / 用途 / 授權條款)                          │
│   data.moa · CWA · NLSC DEM · OSM(ODbL)· 內政部人口 ...                │
│                                                                        │
│  AI 應用界線 (不自動撤離 / 不收社群文本 / 模型透明 / 隱私 / 失效降級)  │
│                                                                        │
│  如何掛載 MCP (claude_desktop_config.json 範例)   [GitHub↗] [Swagger↗] │
└──────────────────────────────────────────────────────────────────────┘
```
元件:純靜態內容,資料取自 README / submission;無需後端。

### 4.4 響應式

- ≥1280px:作戰室三欄並列。
- <1024px:三欄改為**分頁標籤**(狀態 / 地圖 / Chat)堆疊;主控台地圖移到清單上方。

---

## 5. 環境變數分離

兩端各一份 `.env`(已建立 `.env.example`),互不共用:

- `backend/.env`:`CWA_API_KEY`、`OPENAI_API_KEY`、`OPENAI_MODEL`、`DATABASE_URL`、`CORS_ORIGINS`、`PORT`、`DATA_DIR`。
- `frontend/.env`:`NUXT_PUBLIC_API_BASE`、`NUXT_PUBLIC_MAP_TILE_URL`、`PORT`。

根目錄既有的 `.env` 保留給舊 MCP 設定;新程式碼一律讀各自目錄的 `.env`。三者都已被 `.gitignore` 排除。

---

## 6. 部署到 Zeabur(原生建置,app 不進 container)

`frontend` 與 `backend` 皆用 **Zeabur 原生建置(Nixpacks/zbpack)**,不自行打包 Docker image。
backend 因此維持**執行期無 GDAL**(見 §2:DEM→.npy、村里界→GeoJSON 前處理,執行期只用 shapely + numpy)。

> **目標 Zeabur 專案(已建立、空的)**:`project-6a1beb20f9a5b4afba15d962`
> 三個 service 都建在此專案內,不需另開新專案。

此專案內開**三個 service**(app 原生建置,DB 用 template):

| Service | 建置方式 | 設定 |
|---|---|---|
| `postgres` | Zeabur **template 部署 Postgres** | 自動產生連線字串,注入 `backend` 的 `DATABASE_URL` |
| `backend` | 原生偵測 Python;`Procfile`/`zbpack.json` 指定 `uvicorn barrier_lake_ops.app:app --host 0.0.0.0 --port $PORT` | env: `CWA_API_KEY`、`OPENAI_API_KEY`、`DATABASE_URL`(引用 postgres service)、`CORS_ORIGINS=https://<frontend>.zeabur.app` |
| `frontend` | 原生偵測 Nuxt;自動 `npm run build` + SSR start | env: `NUXT_PUBLIC_API_BASE=https://<backend>.zeabur.app` |

步驟:
1. 部署 `postgres`(template)。
2. 部署 `backend`,以變數引用 postgres 連線字串;啟動時 Alembic `upgrade head` 自動建表;取得 backend 公開網域。
3. 把 backend 網域填入 `frontend` 的 `NUXT_PUBLIC_API_BASE`,並回填 `backend` 的 `CORS_ORIGINS`。
4. 部署 `frontend`,驗證可呼叫 backend、簡報能寫入並查回。
5. health check:`backend /health`(含 DB 連線)、`frontend /`。

> 採 Zeabur CLI(本機已有 `zeabur` skill)直接 deploy 本地程式碼,或 Git 連動;實作階段確認。
> **本機測試**:`docker-compose.yml` 只起 Postgres container,frontend/backend 直接在本機跑(不進 container)。
> 大型 geo 資料:前處理後的 `.npy`/GeoJSON 若仍偏大,於 build/啟動階段從外部下載到 `DATA_DIR`,避免塞進 repo。

---

## 7. 上傳 GitHub

- Remote 已設定:`git@github.com:CodeWorldBagel/BarrierLakeOps.git`(branch `main`)。
- 確認 `.gitignore` 已涵蓋 `backend/.env`、`frontend/.env`、`node_modules/`、`.cache/`、`data/` 大檔(必要時用 Git LFS 或外部下載腳本)。
- 在 `main` 之外開工作分支提交,完成後合併或直接推送(依 nick 指示)。
- 更新根 `README.md` 的 A2 倉庫結構:`mcp_server/`→`backend/`、`web_demo/`→`frontend/`、狀態由「🚧 規劃中」改「✅ 已上線」。

---

## 8. 今日時程(建議順序)

1. **Backend 骨架**:`pyproject.toml`、`config.py`、`schemas.py`、`catalog.py` + `lake_catalog.yaml`(馬太鞍 + data.moa)。
2. **DB 層**:`docker-compose` 起本機 Postgres;`db/models.py` + Alembic 初始 migration(briefings / chat)。
3. **Tool 0/1**:接 data.moa + Qlake → REST `/lakes`、`/lakes/{id}/status`。
4. **Tool 2**:接 CWA(需金鑰)→ `/weather`。
5. **Tool 3/4**:`prep_geo.py` 前處理 → DEM 簡化淹水 + 村里相交 → `/inundation`、`/population`。
6. **Tool 5 + Chat**:OpenAI(需金鑰)→ `/briefing`、`/chat`(SSE);生成即寫入 Postgres;`GET /briefings`、`/chat/sessions/{id}`。
7. **Frontend 骨架**:Nuxt + 三頁路由 + `useApi` + `useChatStream`。
8. **頁面**:`/` 主控台 → `/lakes/[id]` 作戰室(含歷史簡報)→ `/about`。
9. **MCP 介面**:`server.py` 包裝同批工具。
10. **本機端到端驗證**(app 本機跑、DB 在 container)。
11. **Push GitHub → 部署 Zeabur(postgres → backend → frontend)→ 線上驗證**。

> 🔑 **需 nick 提供**:`CWA_API_KEY`(步驟 3 前)、`OPENAI_API_KEY`(步驟 5 前)。
> 取得前,該 Tool 先以介面打通、回傳明確「待金鑰」降級狀態,不阻塞其他步驟。

---

## 9. 風險與降級

| 風險 | 緩解 |
|---|---|
| DEM/shapefile 檔案大(>100MB) | `prep_geo.py` 前處理只留各湖 bbox 的小檔;必要時啟動階段從外部下載到 `DATA_DIR` |
| GDAL 在原生(非 container)建置難裝 | 執行期**不依賴 GDAL**:DEM→.npy、shapefile→GeoJSON,只用 shapely(GEOS wheel)+ numpy |
| Postgres 連線/建表失敗 | 啟動 Alembic `upgrade head`;`/health` 檢查 DB 連線;Zeabur 用變數引用 postgres service |
| CWA/data.moa 限流或欄位變動 | adapter 加快取(`CACHE_DIR`)+ 失效降級回傳 stale |
| 一天內無法做到工程級水文 | Tool 3 明確標 `disclaimer`,符合 submission 之 MVP 定位 |
| OpenAI 金鑰未到位 | Chat / briefing 先回 stub,介面與 SSE 通道先打通 |

---

## 10. 驗證(Verification)

- **Backend 單元**:每個 Tool 對固定輸入回傳符合 `schemas.py` 的結構;adapter 失效時回傳降級而非例外。
- **Backend 端到端**:`curl /lakes`、`/lakes/mataian-2025/status`、`/docs` 可開;`/chat` 能 SSE 串出工具調用。
- **持久化**:呼叫 `/briefing` 後 `GET /lakes/{id}/briefings` 能查到該筆;`GET /briefings/{id}` 回得出 `input_context` 快照;`/health` 顯示 DB 連線正常。
- **MCP**:用 MCP inspector 或 Claude Desktop 掛 `server.py`,跑情境 A、B。
- **Frontend**:`/` 顯示真實湖清單與地圖;`/lakes/[id]` 三欄載入真實狀態、可重估淹水、Chat 串流;`/about` 內容正確。
- **線上**:Zeabur 三 service(postgres / backend / frontend)部署成功,frontend 能透過公開網域呼叫 backend,簡報寫得進 DB,無 CORS 錯誤。
- 可用 `/browse` 或 `/qa` skill 對部署後的前端做煙霧測試。
