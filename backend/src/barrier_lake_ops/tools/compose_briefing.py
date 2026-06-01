"""Tool 5 — compose_briefing:LLM 態勢摘要生成(OpenAI)。

消化 Tool 0–4 的回傳,依受眾產出結構化摘要。
不接收外部社群文本;不自動下達撤離指令(AI 界線)。data_sources_used 由輸入彙整,確保可追溯。
"""

from __future__ import annotations

import json

from ..schemas import AlertLevel, BriefingOutput, DataSource
from ..agent.openai_client import get_client, get_model

AUDIENCE_GUIDE = {
    "command_center": "對象為災害應變指揮官。用語精確、條列關鍵數據與建議行動,聚焦決策。",
    "public": "對象為一般民眾。用語平實、避免術語,清楚說明風險與自保行動。",
    "media": "對象為媒體。提供可引用的事實與數據,語氣中性。",
    "multi_lake_overview": "對象為應變中心,提供全台多湖風險概覽與排序。",
}

SYSTEM = (
    "你是台灣防災跨部會態勢研判助手。只能依據使用者提供的『工具回傳資料』撰寫摘要,"
    "不得加入未提供的數字或臆測。明確區分觀測值與模型估算(淹水為 MVP 簡化模型)。"
    "不下達或建議自動撤離指令;撤離決策保留給人類指揮官,你僅提供研判輔助。"
    "若資料缺漏或標示為 stale/unavailable,需如實指出。輸出使用繁體中文。"
)

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status_color": {"type": "string", "enum": ["green", "yellow", "orange", "red", "unknown"]},
        "headline": {"type": "string"},
        "key_facts": {"type": "array", "items": {"type": "string"}},
        "recommended_actions": {"type": "array", "items": {"type": "string"}},
        "natural_language": {"type": "string"},
        "ai_confidence": {"type": "number"},
    },
    "required": [
        "status_color",
        "headline",
        "key_facts",
        "recommended_actions",
        "natural_language",
        "ai_confidence",
    ],
}


def _collect_sources(obj, acc: dict[str, DataSource]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "data_sources" and isinstance(v, list):
                for ds in v:
                    if isinstance(ds, dict) and ds.get("source"):
                        acc.setdefault(ds["source"], DataSource(**{
                            kk: ds.get(kk, "") for kk in ("source", "license", "attribution", "url")
                        }))
            else:
                _collect_sources(v, acc)
    elif isinstance(obj, list):
        for item in obj:
            _collect_sources(item, acc)


def _fallback(context: dict, audience: str, sources: list[DataSource]) -> BriefingOutput:
    """無 LLM 時的確定性降級摘要(不捏造,僅轉述輸入)。"""
    status = context.get("status", {})
    color = status.get("alert_level", "unknown")
    name = status.get("name", "")
    facts = []
    if status:
        facts.append(
            f"{name} 水位 {status.get('water_level_m')} m,headroom {status.get('headroom_m')} m,警戒 {color}。"
        )
    w = context.get("weather", {})
    if w:
        facts.append(f"上游雨量警戒 {w.get('alert_level')}。{w.get('rationale','')}")
    pop = context.get("population", {})
    if pop:
        facts.append(
            f"潰壩影響約 {pop.get('total_households')} 戶、{pop.get('total_population')} 人。"
        )
    return BriefingOutput(
        status_color=AlertLevel(color) if color in AlertLevel._value2member_map_ else AlertLevel.unknown,
        headline=f"{name} 態勢摘要(系統降級:未串接 LLM)",
        key_facts=facts,
        recommended_actions=["請人工研判;LLM 未啟用時本摘要僅轉述工具資料。"],
        natural_language=";".join(facts),
        ai_confidence=0.0,
        data_sources_used=sources,
    )


async def compose_briefing(
    context: dict, audience: str = "command_center", lake_id: str | None = None
) -> BriefingOutput:
    acc: dict[str, DataSource] = {}
    _collect_sources(context, acc)
    sources = list(acc.values())

    client = get_client()
    if client is None:
        return _fallback(context, audience, sources)

    guide = AUDIENCE_GUIDE.get(audience, AUDIENCE_GUIDE["command_center"])
    user = (
        f"受眾:{audience}。{guide}\n\n"
        f"以下為工具回傳資料(JSON),請據此撰寫態勢摘要:\n"
        f"```json\n{json.dumps(context, ensure_ascii=False, default=str)[:12000]}\n```"
    )
    try:
        resp = await client.chat.completions.create(
            model=get_model(),
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "briefing", "schema": _SCHEMA, "strict": True},
            },
            temperature=0.3,
        )
        data = json.loads(resp.choices[0].message.content)
        color = data.get("status_color", "unknown")
        return BriefingOutput(
            status_color=AlertLevel(color) if color in AlertLevel._value2member_map_ else AlertLevel.unknown,
            headline=data["headline"],
            key_facts=data.get("key_facts", []),
            recommended_actions=data.get("recommended_actions", []),
            natural_language=data.get("natural_language", ""),
            ai_confidence=float(data.get("ai_confidence", 0.5)),
            data_sources_used=sources,
        )
    except Exception:  # noqa: BLE001
        return _fallback(context, audience, sources)
