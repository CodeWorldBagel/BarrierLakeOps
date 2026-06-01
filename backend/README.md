# BarrierLakeOps — backend

堰湖態勢跨部會研判元件的**後端**:同一份工具邏輯以雙介面交付。

- **MCP 介面**(FastMCP):供 Claude Desktop / Cursor 等 AI Agent 掛載
- **HTTP REST 介面**(FastAPI + OpenAPI/Swagger):供前端與其他系統整合

> README 早期版本稱本目錄為 `mcp_server/`,現統一命名為 `backend/`。

## 6 個 Tool

| Tool | 功能 |
|---|---|
| `list_lakes` | 列出可查詢堰塞湖 |
| `get_lake_status` | 堰塞湖即時狀態 |
| `get_upstream_weather` | 上游集水區雨量 |
| `estimate_inundation` | 潰壩淹水範圍推估 |
| `get_affected_population` | 影響人口與弱勢 |
| `compose_briefing` | LLM 態勢摘要生成 |

## 快速開始

```bash
docker compose up -d postgres # 在 repo 根目錄起本機 Postgres(app 不進 container)
cd backend
# 建立 backend/.env,至少填入:
#   CWA_API_KEY / OPENAI_API_KEY / DATABASE_URL
#   OPENAI_MODEL=gpt-4.1 ; CORS_ORIGINS=http://localhost:3000
uv sync                       # 安裝依賴(Python 3.12)
uvicorn barrier_lake_ops.app:app --reload --port 8000  # 啟動時自動建表
# REST 文件: http://localhost:8000/docs
```

> 持久化:`compose_briefing` 每次生成都寫入 `briefings`(含輸入快照,可追溯);Chat 對話寫入 `chat_sessions` / `chat_messages`。

完整開發與部署步驟見 [`docs/EXECUTION_PLAN.md`](../docs/EXECUTION_PLAN.md)。
