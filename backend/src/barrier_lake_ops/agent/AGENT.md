# Reference Client Chat Agent — 設計揭露

> 對應 submission.md §(三) AI 使用說明:reference client 內建 Agent 之完整設計公開揭露,
> 確保 AI 應用可被審查、重現與改寫。

## 角色定位

服務災害應變中心人員的「堰塞湖跨部會態勢」作戰助手。本身不是資料源,而是在受限 system prompt 下
**僅調用本元件的 6 個 Tool** 完成多步驟盤點,並以自然語言彙整研判。

## System Prompt(摘要)

- 只能透過工具取得資料(列出堰塞湖、查狀態、查上游雨量、估淹水、估影響人口、生成摘要)。
- 不得使用工具以外的知識編造數字,**不得進行通用網路搜尋**或第三方資料串接。
- 淹水為 **MVP 簡化模型**,需註明;水位若為情境基準快照需說明非即時。
- **只提供研判與建議**,不得宣稱已發送撤離簡訊、致電消防或觸發警報——對外通知由人類執行。
- **撤離決策保留給人類指揮官**。
- 繁體中文,先呈現關鍵數據再給建議。

完整 prompt 見 [`chat_agent.py`](./chat_agent.py) 的 `SYSTEM` 常數。

## 多步調用策略

採 OpenAI function-calling 迴圈(上限 8 輪):模型自主規劃工具順序、處理工具間資料依賴
(如先 `estimate_inundation` 再 `get_affected_population`),最後彙整回應。

對 LLM 暴露的工具為 6 個 Tool 的**精簡包裝**:
- 大型 GeoJSON(淹水範圍)不回傳給 LLM,避免 context 膨脹與誤用;
- `get_affected_population` / `compose_briefing` 以 `lake_id` 為入參,後端內部串接淹水範圍。

## 工具使用守則 / 降級規則

- 任一外部資料源不可用 → 工具回傳明確錯誤狀態(stale/unavailable),Agent **如實告知缺漏,不捏造**。
- 僅支援 Lake Catalog 與 data.moa 已登錄的堰塞湖;未登錄者明確告知。
- 對話與每次工具調用、每份生成簡報皆寫入 Postgres(可追溯)。

## 不做什麼(AI 界線)

- 不自動下達撤離指令、不直接觸發警報、不串接 PWS/LINE/Email 發送通道。
- 不接收外部社群媒體文本作為輸入,避免成為假訊息放大器。
