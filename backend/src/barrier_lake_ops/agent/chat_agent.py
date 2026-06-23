"""Reference Client 內建 Chat Agent — OpenAI function-calling 串本元件 6 個 Tool。

設計守則公開於 AGENT.md。Agent 僅調用本元件工具,不開啟通用網路搜尋;
僅產出建議,不串接 PWS/LINE/Email 等實際發送通道。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator

from ..db.engine import SessionLocal
from ..db.repository import add_chat_message, create_chat_session
from .openai_client import get_client, get_model
from ..tools.compose_briefing import compose_briefing
from ..tools.estimate_inundation import estimate_inundation
from ..tools.get_affected_population import get_affected_population
from ..tools.get_lake_status import get_lake_status
from ..tools.get_upstream_weather import get_upstream_weather
from ..tools.list_lakes import list_lakes

SYSTEM = (
    "你是台灣『堰塞湖跨部會態勢』作戰助手,服務災害應變中心人員。"
    "你只能透過提供的工具取得資料(列出堰塞湖、查狀態、查上游雨量、估淹水、估影響人口、生成摘要),"
    "不得使用工具以外的知識編造數字,也不得進行通用網路搜尋。"
    "淹水為 MVP 簡化模型,需註明;水位若為情境基準快照需說明非即時。"
    "你只提供研判與建議,不得宣稱已發送撤離簡訊、致電消防或觸發警報——對外通知由人類執行。"
    "撤離決策保留給人類指揮官。請用繁體中文,以對話口語精簡作答:"
    "先給一句結論,再視需要補最多 3~5 點重點;數據點到即可,不要逐筆重述或逐一列舉"
    "(例如受影響村里只給總數與最關鍵的幾項)。不要重複工具已附的免責聲明,"
    "不要寫成多段式正式報告。可用簡短條列或小表格輔助,但務求簡短好讀。"
)

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "list_lakes",
            "description": "列出可查詢的堰塞湖(可依狀態過濾),回傳含警戒與風險排序。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status_filter": {"type": "string", "enum": ["all", "active", "monitoring"]}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lake_status",
            "description": "取得指定堰塞湖水位、蓄水量、距溢流 headroom、警戒等級。",
            "parameters": {
                "type": "object",
                "properties": {"lake_id": {"type": "string"}},
                "required": ["lake_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_upstream_weather",
            "description": "取得堰塞湖上游集水區鄰近雨量站觀測與警戒。",
            "parameters": {
                "type": "object",
                "properties": {"lake_id": {"type": "string"}},
                "required": ["lake_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_inundation",
            "description": "推估潰壩淹水(深度、抵達時間)。breach_scenario: full 或 partial。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lake_id": {"type": "string"},
                    "breach_scenario": {"type": "string", "enum": ["full", "partial"]},
                },
                "required": ["lake_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_affected_population",
            "description": "估算潰壩淹水範圍內受影響村里、戶數、人口與老幼弱勢(內部會先算淹水範圍)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lake_id": {"type": "string"},
                    "breach_scenario": {"type": "string", "enum": ["full", "partial"]},
                },
                "required": ["lake_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compose_briefing",
            "description": "彙整某湖的狀態/雨量/淹水/人口,生成結構化態勢摘要。audience 預設 command_center。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lake_id": {"type": "string"},
                    "audience": {
                        "type": "string",
                        "enum": ["command_center", "public", "media", "multi_lake_overview"],
                    },
                },
                "required": ["lake_id"],
            },
        },
    },
]


async def _assemble_context(lake_id: str, scenario: str = "full") -> dict:
    st = await get_lake_status(lake_id)
    w = await get_upstream_weather(lake_id)
    inu = await estimate_inundation(lake_id, scenario)
    pop = await get_affected_population(inu.inundation_polygon)
    return {
        "status": st.model_dump(),
        "weather": w.model_dump(),
        "inundation": {k: v for k, v in inu.model_dump().items() if k != "inundation_polygon"},
        "population": pop.model_dump(),
    }


async def _execute(name: str, args: dict) -> dict:
    """執行工具,回傳給 LLM 的精簡結果(不含大型 GeoJSON)。"""
    if name == "list_lakes":
        out = await list_lakes(args.get("status_filter", "all"))
        return {
            "total": out.total,
            "lakes": [
                {"id": s.id, "name": s.name, "alert_level": s.alert_level.value,
                 "status": s.status, "headroom_m": s.headroom_m}
                for s in out.lakes
            ],
        }
    if name == "get_lake_status":
        return (await get_lake_status(args["lake_id"])).model_dump()
    if name == "get_upstream_weather":
        return (await get_upstream_weather(args["lake_id"])).model_dump()
    if name == "estimate_inundation":
        inu = await estimate_inundation(args["lake_id"], args.get("breach_scenario", "full"))
        # 保留完整 polygon 給前端畫地圖;餵 LLM 前才在 run_chat 裡剝除(裁切只在呈現/LLM 邊界)。
        return inu.model_dump()
    if name == "get_affected_population":
        inu = await estimate_inundation(args["lake_id"], args.get("breach_scenario", "full"))
        pop = await get_affected_population(inu.inundation_polygon)
        return pop.model_dump()
    if name == "compose_briefing":
        ctx = await _assemble_context(args["lake_id"])
        b = await compose_briefing(ctx, args.get("audience", "command_center"), args["lake_id"])
        return b.model_dump()
    return {"error": f"unknown tool {name}"}


def sse(event: dict) -> dict:
    return {"event": event.get("type", "message"), "data": json.dumps(event, ensure_ascii=False, default=str)}


async def run_chat(
    message: str, lake_id: str | None = None, session_id: str | None = None
) -> AsyncGenerator[dict, None]:
    """SSE 事件產生器:tool_call / tool_result / final / error。"""
    client = get_client()
    # 建立 / 沿用 chat session
    sid: uuid.UUID | None = None
    try:
        async with SessionLocal() as db:
            if session_id:
                try:
                    sid = uuid.UUID(session_id)
                except ValueError:
                    sid = None
            if sid is None:
                row = await create_chat_session(db, lake_id=lake_id)
                sid = row.id
            await add_chat_message(db, session_id=sid, role="user", content=message)
    except Exception:  # noqa: BLE001
        sid = None  # DB 不可用 → 持久化降級,不阻擋對話

    yield sse({"type": "session", "session_id": str(sid) if sid else None})

    if client is None:
        yield sse({"type": "final", "content": "（系統未設定 OPENAI_API_KEY,Chat 暫不可用。其他工具與儀表板仍可使用。）"})
        return

    hint = f"（目前聚焦堰塞湖 lake_id={lake_id}）" if lake_id else ""
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": message + ("\n" + hint if hint else "")},
    ]

    try:
        for _ in range(8):  # 最多 8 輪工具調用
            resp = await client.chat.completions.create(
                model=get_model(), messages=messages, tools=TOOL_SPECS, temperature=0.3
            )
            msg = resp.choices[0].message
            if not msg.tool_calls:
                content = msg.content or ""
                if sid:
                    async with SessionLocal() as db:
                        await add_chat_message(db, session_id=sid, role="assistant", content=content)
                yield sse({"type": "final", "content": content})
                return

            messages.append(
                {"role": "assistant", "content": msg.content,
                 "tool_calls": [tc.model_dump() for tc in msg.tool_calls]}
            )
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield sse({"type": "tool_call", "name": name, "args": args})
                result = await _execute(name, args)
                # 前端拿完整結果(含 polygon)畫卡片與地圖;LLM 與稽核只留精簡(剝除大型 GeoJSON)。
                lean = {k: v for k, v in result.items() if k != "inundation_polygon"}
                yield sse({"type": "tool_result", "name": name, "result": result})
                if sid:
                    async with SessionLocal() as db:
                        await add_chat_message(
                            db, session_id=sid, role="tool", tool_name=name,
                            tool_args=args, tool_result=lean,
                        )
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id,
                     "content": json.dumps(lean, ensure_ascii=False, default=str)[:8000]}
                )
        yield sse({"type": "final", "content": "（已達工具調用上限,請縮小問題範圍再試。）"})
    except Exception as exc:  # noqa: BLE001
        yield sse({"type": "error", "message": f"Chat 發生錯誤:{exc}"})
