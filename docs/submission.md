# 競賽提案存檔

本檔為「**防災積木元件創新賽:公民科技拼出韌性臺灣**」報名表提交內容之原文存檔,供團隊開發與後續審查溯源使用。內容已同步精簡版至 [`README.md`](../README.md)。

| | |
|---|---|
| 競賽主辦 | 數位發展部 |
| 報名死線 | 中華民國 115/6/1(一)12:00 |
| GitHub Repo | https://github.com/CodeWorldBagel/BarrierLakeOps |
| 隊伍 | (待填) |
| 提交日期 | 2026/05/__ |

---

## (一)問題描述

> 對應簡章 §6(一);評分項目「問題貼近度與真實性」(20 分)

2025 年 9 月 23 日,花蓮馬太鞍溪堰塞湖溢流潰壩,造成 19 人死亡、5 人失聯、157 人受傷,1,837 戶受影響(資料來源:報導者 2025/10、天下雜誌 2025/10)。事後檢討揭露這次災害的關鍵失靈點之一是「跨部會資料無法即時匯流」:堰塞湖蓄水位在林業及自然保育署相關系統、上游雨量在中央氣象署、下游淹水預測在水利署、撤離名冊在縣府 EMIC,沒有任何一處能一次看完全貌。台大模擬的疏散範圍從約 700 人擴大到 1,800 戶,距災害發生僅剩約 2 天。

但馬太鞍不是孤例。2024 年花蓮強震後,中央山脈大範圍山體鬆動,陸續形成多處堰塞湖;農業部林業及自然保育署目前已開放 25 筆「國有林堰塞湖」資訊。每出現一個新堰塞湖,應變單位就要重做一次跨部會盤點工作;每一次盤點的痛點都會重演。

### 人物角色 Persona

> **王大明,42 歲,花蓮縣府災害應變中心輪值人員**
>
> 颱風期間,他在中心同時要看多套系統:CWA 雨量、水利署水位、堰塞湖蓄水監測、農村署土石流警戒、縣府自家災情系統。每個系統登入方式不同、欄位不一致,須靠 LINE 群組請各局處同仁協助回報數據才能拼出全貌。當紅色警戒發布、需於有限時間內向指揮官提報「潰壩可能影響哪些村里、多少人」時,這種以人腦串接的工作方式極易在夜班疲勞情境下漏接關鍵資料。而這套以人腦盤點的流程,在台灣每出現一個新堰塞湖時都要重新走一次。

### 現行作法的限制

1. **資料看不齊**:相關資料分散在六個以上系統。
2. **格式不一致**:CAP 1.2 標準雖存在,各機關欄位填法不統一;部分資料源僅以網頁地圖呈現,缺乏標準化介面。
3. **人力依賴**:跨系統盤點仰賴人腦,疲勞時容易漏接。
4. **AI 接不上**:目前所有 AI 助理(不論政府的 TAIDE 或民間的 Claude/GPT)皆無法直接呼叫這些系統,因此難以替應變中心提供決策輔助。
5. **缺乏可重複使用的基礎建設**:每出現新堰塞湖,應變單位都要重做一次工具整合。

### 本作品如何提供協助

我們設計一個遵循 Model Context Protocol(MCP)標準的工具伺服器,把堰塞湖態勢研判所需的跨部會資料封裝為可被 AI Agent 多步驟調用的工具集。元件不綁定單一事件,而是以 Lake Catalog 設定檔驅動 — 目前已可支援林業及自然保育署開放的 25 筆國有林堰塞湖。新堰塞湖出現時,只需在 catalog 中新增一筆設定即可納入支援,不需修改程式碼;架構同時保留 adapter 介面,可於後續啟用其他資料源(如 NCDR Datahub)以擴展涵蓋範圍。

馬太鞍溪堰塞湖為本作品的主要案例與發表 demo 場景;但同一元件可服務台灣所有已開放資訊的堰塞湖,避免每次新事件都要重做一次工具整合。應變中心人員以自然語言提問後,AI Agent 自主規劃並串接「列出湖況清單 → 查詢單湖狀態 → 查降雨 → 估淹水 → 估人口 → 寫摘要」等步驟,產出結構化態勢摘要,協助縮短資料整合時間、減輕第一線人員的認知負荷。

---

## (二)元件設計邏輯

> 對應簡章 §6(二);評分項目「可行性與完成度」(30 分)、「元件化與可拼接性」(30 分)

**元件名稱**:BarrierLakeOps(堰湖態勢跨部會研判元件)
**元件型態**:MCP(Model Context Protocol)Server + API 服務型元件(雙介面交付)

### 設計原則

本元件採「積木式設計」精神,由 6 個獨立 Tool 組成,每個 Tool 都有明確的 Input / Function / Output,可單獨被呼叫、亦可被 AI Agent 串接多步調用。新增堰塞湖只需在 Lake Catalog(YAML 設定檔)中加一筆設定,不需修改程式碼。資料源層採 Adapter 介面設計,目前接入 data.moa 與 Qlake,並預留 NCDR Datahub 等延伸選項可於未來啟用。

### 雙介面交付

同一份 Tool 邏輯以兩種介面同時暴露,符合競賽簡章 §7(三) 列出之多種元件型態:

1. **MCP 介面**(對應簡章 §7(三)6 MCP 伺服器型元件) — 供 Claude Desktop、Cursor 與未來政府智慧助手等 AI Agent 多步驟調用。
2. **HTTP REST 介面**(對應簡章 §7(三)2 API 服務型元件) — 以 FastAPI 包裝同一份 Pydantic schema,提供 OpenAPI(Swagger) 規格文件,供既有 web app 或機關系統以標準 HTTP 方式整合。

兩種介面共用同一份 Tool 實作,確保行為一致;版本更新不會出現「MCP 修了 / REST 沒修」的不對稱問題。本作品另附 Nuxt 3 reference client(位於 `web_demo/`),作為消費此元件之示範客戶端,並非主要交付。

### Tool 規格

#### Tool 0:`list_lakes` — 列出可查詢堰塞湖清單
- **Input**:`{ status_filter: "active" | "monitoring" | "all" }`
- **Function**:從 Lake Catalog 回傳所有可查詢堰塞湖
- **Output**:`{ lakes[], total, data_sources[] }`
- **資料源**:Lake Catalog(YAML)+ data.moa 國有林堰塞湖資訊

#### Tool 1:`get_lake_status` — 堰塞湖即時狀態
- **Input**:`{ lake_id: string }`
- **Function**:取得指定堰塞湖最新水位、蓄水量、距溢流高程、警戒等級
- **Output**:`{ lake_id, name, water_level_m, storage_million_m3, overflow_threshold_m, headroom_m, alert_level, last_updated, data_sources[], data_freshness_minutes }`
- **資料源(主)**:農業資料開放平臺 data.moa.gov.tw「國有林堰塞湖資訊」— 政府資料開放授權條款 1.0
- **資料源(即時補強)**:Qlake 端點(標註為非官方文件端點)
- **延伸選項**:架構保留 adapter 介面,可後續啟用 NCDR Datahub 涵蓋非國有林範圍

#### Tool 2:`get_upstream_weather` — 上游集水區雨量
- **Input**:`{ lake_id, hours_back, hours_forward }`
- **Function**:依 Lake Catalog 對應該湖上游雨量站,回傳過去與未來雨量與警戒
- **Output**:`{ stations[], forecast_24h_mm_max, alert_level, rationale, data_sources[] }`
- **資料源**:CWA Opendata O-A0002-001 + F-D0047 — 政府資料開放授權條款 1.0;農村水保署 246 警戒值 — 政府資料開放授權條款 1.0

#### Tool 3:`estimate_inundation` — 潰壩淹水範圍推估
- **Input**:`{ lake_id, breach_scenario, breach_volume_million_m3 }`
- **Function**:依 Lake Catalog 對應該湖下游 DEM 範圍,輸出淹水 polygon
- **Output**:`{ inundation_polygon: GeoJSON, max_depth_m_estimate, leading_edge_arrival_minutes, model_used, disclaimer, data_sources[] }`
- **資料源**:NLSC 20m DEM(data.gov.tw dataset/35430,政府資料開放授權條款 1.0,內建於容器);OSM 河道中心線(ODbL,輸出含 attribution)
- **備註**:MVP 採簡化動力學模型,輸出明確標註「僅供緊急研判輔助、非工程級水文模型」,未來可替換為水保局或學術級專業模型

#### Tool 4:`get_affected_population` — 影響人口與弱勢
- **Input**:`{ polygon: GeoJSON }`
- **Function**:計算淹水範圍內村里、戶數、人口(含老幼比例)
- **Output**:`{ affected_villages[], total_households, total_population, vulnerable_estimate: { elderly_65plus, children_under6 }, data_sources[] }`
- **資料源**:data.gov.tw「村里戶數、單一年齡人口」— 政府資料開放授權條款 1.0;村里界 shapefile(data.gov.tw 直接下載,內建於容器);可選補強:SEGIS 銀髮安居資料

#### Tool 5:`compose_briefing` — LLM 態勢摘要生成
- **Input**:`{ context: Tool0-4 之回傳, audience: 指揮官 | 民眾 | 媒體 | multi_lake_overview }`
- **Function**:將原始資料整合為結構化態勢摘要;支援單湖深入分析與多湖比較
- **Output**:`{ status_color, headline, key_facts[], recommended_actions[], natural_language, ai_confidence, data_sources_used[] }`

### Lake Catalog 與 Adapter 介面

每個堰塞湖在 catalog 中以 YAML 設定,包含 id、名稱、形成原因、座標、流域、警戒值、對應的上游 CWA 雨量站、下游 DEM 範圍等。新增堰塞湖時,只需在 catalog 中加一筆設定即可被全部 6 個 Tool 支援,不需修改程式碼。資料源層採 Adapter 介面,每個資料源以獨立 adapter 實作,可隨時啟用或停用。

### 標準化格式

所有 Tool 採 JSON Schema 嚴格定義 I/O;地理資料採 GeoJSON、時間採 RFC 3339;CAP feed 相容欄位採 OASIS CAP 1.2 命名。每個 Tool 輸出皆含 `data_sources` 欄位,揭露原始資料來源、授權條款與 attribution 文字,符合競賽簡章 §8 對資料來源揭露與下游可開源的要求。

### 可拼接性

本元件不綁定任何前端、AI 模型、單一機關系統或單一堰塞湖。提供:

1. **標準 MCP 介面**:任何支援 MCP 的 Agent 皆可掛載。
2. **HTTP REST 介面**(FastAPI + OpenAPI/Swagger):供 web app、行動 app 或其他後端系統以標準方式整合。
3. **Python Client Sample Code**:供既有後端服務以函式庫方式呼叫。
4. **Docker 部署檔**:可於機關內網或雲端環境獨立部署。
5. **Lake Catalog 設定檔**:可由非工程師維護,新增堰塞湖無須改 code。
6. **Adapter 介面**:可隨時啟用新資料源,無須改動 Tool 主邏輯。
7. **Reference Client**(Nuxt 3 web 儀表板 + Chat UI):示範 web 端消費方式,供其他單位參考改寫成自家 UI。其後端內建 Agent 之設計(角色、system prompt、多步調用策略、工具使用守則、降級規則)以 [`web_demo/AGENT.md`](../web_demo/AGENT.md) 公開揭露,確保 AI 應用可被審查與重現。

### 使用情境

- **A.** 應變中心輪值人員透過 Claude Desktop 自然語言詢問,AI Agent 自動多步調用 Tool 完成跨部會盤點。
- **B.** 縣府災害應變儀表板透過 REST 接入此元件,水位或降雨達警戒值時自動觸發摘要推送。
- **C.** 未掛載 MCP 的單位透過 web 儀表板與 Chat UI 直接使用 — 左側湖清單、中央地圖視覺化、右側 Chat 即時顯示 Agent 調用流程,原始碼公開以利其他單位參考改寫。

---

## (三)AI 使用說明

> 對應簡章 §6(三);評分項目「AI 加分項」(10 分)

### AI 在本作品中扮演的角色

本元件本身不是 AI 模型,而是「設計給 AI Agent 使用的工具集」。我們認為真正的 AI 公共價值不是把 LLM 塞進每個應用,而是把既有的政府開放資料標準化為 AI Agent 可調用的元件,讓 AI 能在防災情境中扮演「跨部會盤點助手」。

具體而言,AI 在本作品中以三種方式出現:

1. **外部 Agent 作為「使用者」**:本元件以 MCP 標準對外暴露 6 個 Tool,接收 AI Agent 的多步驟調用請求。Agent(如 Claude、GPT 或國產 TAIDE)依據自然語言問題自主規劃調用順序、處理工具間的資料依賴、整合結果回應使用者。
2. **內建 LLM 於 Tool 5**:`compose_briefing` 工具內部使用 LLM,把 Tool 0-4 的原始資料轉寫為態勢摘要,並依目標受眾(指揮官、民眾、媒體、多湖概覽)調整用語層次。
3. **Reference Client 內建 Agent**:web 端 reference client 之 Chat UI 後端另封裝一個 LLM Agent,使其在受限的 system prompt 下僅調用本元件的 6 個 Tool,供未部署 MCP 的單位透過瀏覽器直接使用同一組工具邏輯。此 Agent 之完整設計(角色定位、system prompt、多步調用策略、工具使用守則、拒答與降級規則)公開於 [`web_demo/AGENT.md`](../web_demo/AGENT.md)。

### AI 使用方式(多步驟任務處理)

本元件設計支援兩種典型 Agent 使用情境:

**情境 A:全台堰塞湖風險概覽(展現可重複使用性)**

```
Step 1: 呼叫 list_lakes(status_filter="active")
Step 2: 對每個湖呼叫 get_lake_status(lake_id)
Step 3: 呼叫 compose_briefing(audience="multi_lake_overview")
```

**情境 B:單一堰塞湖深入分析(以馬太鞍為主案例)**

```
Step 1: 呼叫 get_lake_status
Step 2: 呼叫 get_upstream_weather
Step 3: 條件判斷
        若 headroom 偏低且預報雨量偏高
        → Step 4: 呼叫 estimate_inundation
        → Step 5: 呼叫 get_affected_population
        否則:直接進入 Step 6
Step 6: 呼叫 compose_briefing
```

此設計直接對應競賽簡章加分項所述「Agent(代理人)特性的 AI 設計,使系統能依任務目標自主規劃並執行多步驟流程」與「與其他元件或資料來源互動」。

### AI 應用界線與潛在風險

我們明確劃定 AI 的使用界線,避免過度信任:

1. **模型限制透明化**:Tool 3(淹水推估)使用 MVP 簡化水文模型,輸出明確標註 `model_used`、`disclaimer` 欄位,提醒使用者「僅供緊急研判輔助、非工程級模型」。
2. **LLM 輸出可追溯**:Tool 5 摘要輸出含 `ai_confidence` 欄位與 `data_sources_used` 完整清單,使用者可逐項回查原始資料,避免黑箱。
3. **排除高風險自動決策**:本元件不設計「AI 自主下令撤離」「AI 直接觸發警報」這類用法。決策權保留給人類指揮官,元件只負責資訊整合。
4. **假訊息防護**:Tool 5 不接收外部 LINE/FB 文本作為 Input,僅消化 Tool 0-4 來自官方資料源的回傳,避免成為假訊息放大器。
5. **隱私邊界**:Tool 4 人口資料採村里為最小粒度,不揭露個人資訊。
6. **失效降級**:當任一外部 API 不可用時,元件回傳明確錯誤狀態,不填補虛構資料;Agent 收到錯誤後會在最終回應中如實告知缺漏。
7. **資料授權合規**:所有 Tool 輸出 JSON 含 `data_sources` 欄位,標註原始資料的來源、授權條款(政府資料開放授權條款 1.0、ODbL 等)與 attribution 文字,確保下游使用與再散布合法。
8. **通用化邊界**:本元件僅支援 Lake Catalog 中已登錄的堰塞湖。未登錄者 Agent 收到 `list_lakes` 結果後可明確告知使用者,避免錯誤判斷。
9. **Chat UI 不直接觸發行動**:即使使用者透過 reference client 之 Chat UI 輸入「請發撤離簡訊」「致電消防」這類請求,元件僅產出建議內容,不串接 PWS、LINE、Email 等實際發送通道;對外通知仍由人類執行。
10. **Chat UI 範圍限定**:reference client 之後端 Agent,其 system prompt 明確限定僅調用本元件之 6 個 Tool,不開啟通用網路搜尋或第三方資料串接,避免引入未經授權或未經驗證的資訊。
11. **AI 設計透明可審查**:Reference Client 內建 Agent 之 system prompt、多步調用策略、工具使用守則、拒答與降級規則皆以 [`web_demo/AGENT.md`](../web_demo/AGENT.md) 公開揭露,確保 AI 應用可被審查、重現與改寫。
