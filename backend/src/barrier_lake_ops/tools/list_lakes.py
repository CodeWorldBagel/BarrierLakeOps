"""Tool 0 — list_lakes:列出可查詢堰塞湖清單(catalog + data.moa,警戒中→觀察中→已解除,次排 formed_at 新→舊)。"""

from __future__ import annotations

from ..adapters import AdapterError
from ..adapters.moa import DATA_SOURCE as MOA_SOURCE
from ..adapters.moa import fetch_moa_lakes
from ..catalog import load_catalog
from ..schemas import AlertLevel, LakeSummary, ListLakesOutput
from . import ALERT_RANK, alert_from_headroom, compute_headroom
from .get_lake_status import CATALOG_SOURCE


async def list_lakes(status_filter: str = "all") -> ListLakesOutput:
    cat = load_catalog()
    summaries: list[LakeSummary] = []
    catalog_names: set[str] = set()  # 與 data.moa 做模糊去重(同一座湖兩種命名)
    moa_names: set[str] = set()  # data.moa 之間僅精確去重

    # 1) catalog 湖(含主案例,可算 headroom/alert)
    for lake in cat.lakes:
        headroom = compute_headroom(lake)
        alert = alert_from_headroom(headroom, lake.threshold)
        summaries.append(
            LakeSummary(
                id=lake.id,
                name=lake.name_zh,
                status=lake.status if lake.status in ("active", "monitoring", "archived") else "monitoring",
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

    # 4) 主排 status(警戒中→觀察中→已解除)；次排 formed_at 新→舊
    STATUS_RANK = {"active": 2, "monitoring": 1, "archived": 0}
    summaries.sort(
        key=lambda s: (
            -STATUS_RANK.get(s.status, 0),
            [-ord(c) for c in (s.formed_at or "")],
        )
    )

    return ListLakesOutput(lakes=summaries, total=len(summaries), data_sources=sources)
