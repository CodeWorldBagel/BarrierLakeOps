# BarrierLakeOps — frontend

堰湖態勢跨部會研判元件的 **Reference Client**(Nuxt 3 / Vue 3)。
示範 web 端如何消費 backend 的 6 個 Tool:湖清單 + 地圖視覺化 + Chat UI。

> README 早期版本稱本目錄為 `web_demo/`,現統一命名為 `frontend/`。

## 頁面

| 路由 | 頁面 | 說明 |
|---|---|---|
| `/` | 全台主控台 | 地圖 + 風險排序湖清單 + 概覽摘要 |
| `/lakes/[id]` | 單湖作戰室 | 三欄:狀態面板 / 地圖+淹水 / Chat UI |
| `/about` | 關於與資料來源 | 問題、6 Tool、資料授權、AI 界線、MCP 掛載 |

## 快速開始

```bash
cd frontend
cp .env.example .env           # 設定 NUXT_PUBLIC_API_BASE 指向 backend
npm install
npm run dev                    # http://localhost:3000
```

頁面匡線圖與完整規劃見 [`docs/EXECUTION_PLAN.md`](../docs/EXECUTION_PLAN.md)。
