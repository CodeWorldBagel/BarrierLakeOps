"""Tool 0 — list_lakes:列出可查詢堰塞湖清單(catalog + data.moa,警戒中→觀察中→已解除,同狀態內依風險,再排 formed_at 新→舊)。"""

from __future__ import annotations

from ..adapters import AdapterError
from ..adapters.moa import DATA_SOURCE as MOA_SOURCE
from ..adapters.moa import fetch_moa_lakes
from ..catalog import load_catalog_async
from ..schemas import AlertLevel, LakeSummary, ListLakesOutput
from . import ALERT_RANK, alert_from_headroom, compute_headroom
from .get_lake_status import CATALOG_SOURCE


async def list_lakes(status_filter: str = "all") -> ListLakesOutput:
    summaries: list[LakeSummary] = []
    catalog_names: set[str] = set()
    moa_names: set[str] = set()

    # 1) DB-first（DB 空則 fallback YAML），由 load_catalog_async 統一處理
    cat = await load_catalog_async()
    for lake in cat.lakes:
        headroom = compute_headroom(lake)
        alert = alert_from_headroom(headroom, lake.threshold)
        summaries.append(
            LakeSummary(
                id=lake.id,
                name=lake.name_zh,
                status=lake.status if lake.status in ("monitoring", "archived") else "monitoring",
                alert_level=alert,
                formed_at=lake.formed_at,
                lat=lake.location.lat,
                lon=lake.location.lon,
                headroom_m=headroom,
            )
        )
        catalog_names.add(lake.name_zh)

    # 2) data.moa 25 筆(真實清單)
    sources = [CATALOG_SOURCE, MOA_SOURCE]
    try:
        for ml in await fetch_moa_lakes():
            # 與 catalog 同一座湖(可能命名略異)→ 模糊去重
            if any(ml.name in n or n in ml.name for n in catalog_names):
                continue
            # data.moa 內部 → 精確去重
            if ml.name in moa_names:
                continue
            moa_names.add(ml.name)
            summaries.append(
                LakeSummary(
                    id=ml.id,
                    name=ml.name,
                    status=ml.status,
                    alert_level=AlertLevel.unknown,
                    formed_at=ml.formed_at,
                    lat=ml.lat,
                    lon=ml.lon,
                    headroom_m=None,
                )
            )
    except AdapterError:
        # data.moa 不可用 → 只回 catalog,並在來源標註降級(不捏造)
        sources = [CATALOG_SOURCE]

    # 3) status_filter
    if status_filter != "all":
        summaries = [s for s in summaries if s.status == status_filter]

    # 4) 主排：警戒中(alert非unknown) > 觀察中 > 已解除；次排：formed_at 新→舊
    def _sort_key(s):
        is_alert = s.alert_level and s.alert_level.value == "red"
        group = 2 if is_alert else (1 if s.status == "monitoring" else 0)
        return (-group, [-(ord(c)) for c in (s.formed_at or "")])
    summaries.sort(key=_sort_key)

    return ListLakesOutput(lakes=summaries, total=len(summaries), data_sources=sources)
