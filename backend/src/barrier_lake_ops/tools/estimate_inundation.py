"""Tool 3 — estimate_inundation:潰壩淹水範圍推估(真實 DEM + MVP 簡化模型)。"""

from __future__ import annotations

from ..adapters.dem import (
    SOURCE as DEM_SOURCE,
    estimate_flood,
    estimate_flood_directional,
    estimate_flood_impact_area,
    has_dem,
)
from ..catalog import load_catalog
from ..schemas import InundationOutput

MODEL = "BarrierLakeOps MVP bathtub-fill v0.1 (SRTM 30m, 容量守恆 + 連通域)"
MODEL_DIRECTIONAL = "BarrierLakeOps experimental directional valley-fill v0.1 (SRTM 30m, 方向剖面推進)"
MODEL_IMPACT_AREA = "BarrierLakeOps experimental impact-area v0.1 (SRTM 30m, 下游可能影響範圍)"
DISCLAIMER = (
    "本淹水範圍為 MVP 簡化模型估算(以 SRTM 30m DEM 容量守恆淹沒推估),"
    "僅供緊急研判輔助,非工程級水文模型;生產應用建議改用國土測繪中心 20m DEM "
    "並採專業水動力模型。"
)


async def estimate_inundation(
    lake_id: str,
    breach_scenario: str = "full",
    breach_volume_million_m3: float | None = None,
    model_variant: str = "mvp",
) -> InundationOutput:
    cat = load_catalog()
    lake = cat.get(lake_id)
    empty = {"type": "FeatureCollection", "features": []}
    if model_variant == "directional":
        model_used = MODEL_DIRECTIONAL
    elif model_variant == "impact_area":
        model_used = MODEL_IMPACT_AREA
    else:
        model_used = MODEL

    if lake is None or not lake.downstream_dem_bbox or not has_dem(lake_id):
        return InundationOutput(
            lake_id=lake_id,
            inundation_polygon=empty,
            max_depth_m_estimate=None,
            leading_edge_arrival_minutes=None,
            model_used=model_used,
            disclaimer=DISCLAIMER + " (此湖未建立下游 DEM,無法推估,不以虛構資料填補。)",
            data_sources=[DEM_SOURCE],
        )

    # 潰壩釋出體積
    if breach_volume_million_m3 is not None:
        vol_million = breach_volume_million_m3
    else:
        storage = (lake.reference_state.storage_million_m3 if lake.reference_state else None) or 20.0
        vol_million = storage if breach_scenario == "full" else storage * 0.5
    volume_m3 = vol_million * 1_000_000

    if model_variant == "directional":
        res = estimate_flood_directional(
            lake_id, volume_m3, (lake.location.lon, lake.location.lat)
        )
        model_used = MODEL_DIRECTIONAL
        model_note = "模型:directional-auto,"
    elif model_variant == "impact_area":
        res = estimate_flood_impact_area(
            lake_id, volume_m3, (lake.location.lon, lake.location.lat)
        )
        model_used = MODEL_IMPACT_AREA
        model_note = "模型:impact-area,"
    else:
        res = estimate_flood(
            lake_id, volume_m3, (lake.location.lon, lake.location.lat)
        )
        model_used = MODEL
        model_note = "模型:mvp,"

    return InundationOutput(
        lake_id=lake_id,
        inundation_polygon=res["polygon"],
        max_depth_m_estimate=res["max_depth_m"],
        leading_edge_arrival_minutes=res["arrival_minutes"],
        model_used=model_used,
        disclaimer=(
            DISCLAIMER
            + f" {model_note}情境:{breach_scenario},釋出體積約 {vol_million:.0f} 百萬 m³,"
            + f"淹水水位約 {res['level_m']} m。"
        ),
        data_sources=[DEM_SOURCE],
    )
