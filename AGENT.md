# AGENT.md — BarrierLakeOps 工具使用守則(Agent / MCP client 必讀)

本元件把分散在各部會的堰塞湖資料封裝為 6 個可拼接 Tool,同時以 **MCP**(`barrier_lake_ops.server`)與 **REST**(`barrier_lake_ops.app`)雙介面暴露。任何接上本元件的 AI Agent(本專案內建的 reference client、或透過 MCP 掛載的 Claude / Cursor 等)都應遵守以下守則。

> ⚠️ 這份守則同時被寫進 **MCP server 的 `instructions`** 與**各工具 docstring**,因此即使你沒讀到本檔、只透過 MCP 拿到工具描述,核心安全界線仍會傳遞給你。

## 1. 資料來源界線
- **只能**透過本元件提供的工具取得堰塞湖資料,不得用工具以外的知識編造數字,也不得進行通用網路搜尋來補資料。
- 若工具回傳標示為 `stale` / `unavailable` / 缺漏,必須**如實指出**,不得自行填補。

## 2. 觀測值 vs 模型估算
- 必須明確區分「觀測值」與「模型估算」。
- 淹水推估(`estimate_inundation`)為 **MVP 簡化模型**(SRTM 30m DEM 容量守恆 bathtub-fill),**非工程級水文模型**,引用時必須註明。
- 水位若為情境基準快照,需說明**非即時**。

## 3. 人在迴路(human-in-the-loop)— 最重要
- 你**只提供研判與建議**,**不得**宣稱已發送撤離簡訊、致電消防、觸發警報或任何對外通知 —— 對外通知一律由人類執行。
- **撤離決策保留給人類指揮官**,你不下達也不代為決定撤離。
- 本元件不串接 PWS / LINE / Email 等實際發送通道;你產出的是輔助研判,不是已執行的動作。

## 4. 輸出
- 使用繁體中文。先呈現關鍵數據,再給建議。
- `compose_briefing` 的 `data_sources_used` 由輸入彙整,確保可追溯。

## 5. 程式碼維護標準
- 優先可讀性:複雜流程應拆成語意明確的小函式或 helper,讓主流程維持可掃讀。
- 減少重複:相同資料轉換、參數組合、mask/GeoJSON 處理、工具結果整理等,應抽成共用 helper。
- 適用時使用快取:如 DEM、Lake Catalog、昂貴且純函式的中間結果,可使用 `lru_cache`、request-scope cache 或其他明確生命週期的快取。
- 不為抽象而抽象:只有在能降低複雜度、減少重複或符合既有模式時才新增抽象。
- 行為不應因整理而改變:重構後需執行最小回歸驗證,尤其是模型輸出、GeoJSON 結構與前端依賴欄位。

## 6 個 Tool
| Tool | 用途 |
|---|---|
| `list_lakes` | 列出可查詢堰塞湖,依風險排序 |
| `get_lake_status` | 水位、蓄水量、距溢流 headroom、警戒等級 |
| `get_upstream_weather` | 上游集水區鄰近雨量站觀測與警戒(CWA) |
| `estimate_inundation` | 潰壩淹水推估(DEM + MVP 模型),輸出 GeoJSON |
| `get_affected_population` | 淹水範圍內村里、戶數、人口、老幼弱勢 |
| `compose_briefing` | 彙整 Tool 0–4 生成結構化態勢摘要(寫入稽核軌跡) |
