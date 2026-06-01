"""Tool 2 — get_upstream_weather:上游集水區雨量與警戒。

主資料源:CWA O-A0002-001(即時觀測)。選取湖中心鄰近雨量站。
警戒採中央氣象署大雨/豪雨分級;forecast(F-D0047 PoP)為 best-effort 補強。
"""

from __future__ import annotations

from ..adapters import AdapterError
from ..adapters.cwa import (
    SOURCE_FC,
    SOURCE_OBS,
    fetch_rain_obs,
    fetch_town_pop_max,
    nearest_stations,
)
from ..catalog import load_catalog
from ..schemas import AlertLevel, Freshness, RainStation, UpstreamWeatherOutput


def _alert_from_rain(max_24h: float | None, max_1h: float | None) -> AlertLevel:
    """中央氣象署雨量分級:大雨/豪雨/大豪雨/超大豪雨。"""
    h24 = max_24h or 0.0
    h1 = max_1h or 0.0
    if h24 >= 350 or h1 >= 100:
        return AlertLevel.red  # 大豪雨以上
    if h24 >= 200:
        return AlertLevel.orange  # 豪雨
    if h24 >= 80 or h1 >= 40:
        return AlertLevel.yellow  # 大雨
    if h24 > 0 or h1 > 0:
        return AlertLevel.green
    return AlertLevel.green


async def get_upstream_weather(
    lake_id: str, hours_back: int = 24, hours_forward: int = 24
) -> UpstreamWeatherOutput:
    cat = load_catalog()
    lake = cat.get(lake_id)
    if lake is None:
        return UpstreamWeatherOutput(
            lake_id=lake_id,
            stations=[],
            alert_level=AlertLevel.unknown,
            rationale="查無此堰塞湖(不在 Lake Catalog)。",
            freshness=Freshness.unavailable,
            data_sources=[],
        )

    try:
        all_obs = await fetch_rain_obs()
    except AdapterError as exc:
        return UpstreamWeatherOutput(
            lake_id=lake_id,
            stations=[],
            alert_level=AlertLevel.unknown,
            rationale=f"CWA 觀測資料暫時不可用({exc});不以虛構資料填補。",
            freshness=Freshness.unavailable,
            data_sources=[SOURCE_OBS],
        )

    # 優先採 catalog 指定站(若其 id 存在於實際資料),否則取鄰近站
    wanted = set(lake.upstream_weather.cwa_stations)
    selected = [o for o in all_obs if o.id in wanted]
    if not selected:
        selected = nearest_stations(
            lake.location.lon, lake.location.lat, all_obs, k=5, max_km=25.0
        )

    stations = [
        RainStation(
            station_id=o.id,
            name=o.name,
            rainfall_1h_mm=o.r1h,
            rainfall_3h_mm=o.r3h,
            rainfall_24h_mm=o.r24h,
            obs_time=o.obs_time,
        )
        for o in selected
    ]

    max_24h = max((o.r24h for o in selected if o.r24h is not None), default=None)
    max_1h = max((o.r1h for o in selected if o.r1h is not None), default=None)
    alert = _alert_from_rain(max_24h, max_1h)

    # forecast best-effort
    pop = None
    ref = selected[0] if selected else None
    if ref is not None:
        pop = await fetch_town_pop_max(ref.county, ref.town)

    rationale = (
        f"選取湖中心鄰近 {len(selected)} 站;"
        f"觀測過去24h最大累積 {max_24h if max_24h is not None else 'n/a'} mm、"
        f"1h最大 {max_1h if max_1h is not None else 'n/a'} mm,"
        f"依中央氣象署雨量分級研判為 {alert.value}。"
    )
    sources = [SOURCE_OBS]
    if pop is not None:
        rationale += f" 鄰近鄉鎮未來約24h最大12h降雨機率 {pop:.0f}%。"
        sources.append(SOURCE_FC)

    return UpstreamWeatherOutput(
        lake_id=lake_id,
        stations=stations,
        forecast_24h_mm_max=None,  # QPF(mm) 未開放於 F-D0047;以 PoP 於 rationale 補充
        alert_level=alert,
        rationale=rationale,
        freshness=Freshness.fresh,
        data_sources=sources,
    )
