"""Tool 3: estimate dam-breach inundation polygons from DEM models."""

from __future__ import annotations

from ..adapters.dem import SOURCE as DEM_SOURCE
from ..adapters.dem import estimate_flood, has_dem
from ..catalog import load_catalog
from ..schemas import InundationOutput
from .explain_flood_cell import explain_flood_cell
from .inundation_runtime import clear_inundation_runtime_cache
from .inundation_runtime import estimate_flood_dem_screening_runtime
from .inundation_runtime import resolve_breach_volume_million_m3

MODEL = "BarrierLakeOps MVP bathtub-fill v0.1 (SRTM 30m, 容量守恆 + 連通域)"
MODEL_DEM_SCREENING = "BarrierLakeOps DEM screening v0.1 (SRTM 30m, DEM 下游流路 + 谷地約束 + 體積守恆)"
DISCLAIMER = (
    "本淹水範圍為 MVP 簡化模型估算(以 SRTM 30m DEM 容量守恆淹沒推估),"
    "僅供緊急研判輔助,非工程級水文模型;生產應用建議改用國土測繪中心 20m DEM "
    "並採專業水動力模型。"
)


def _model_used(model_variant: str) -> str:
    return MODEL_DEM_SCREENING if model_variant == "dem_screening" else MODEL


def _empty_output(lake_id: str, model_variant: str) -> InundationOutput:
    return InundationOutput(
        lake_id=lake_id,
        inundation_polygon={"type": "FeatureCollection", "features": []},
        max_depth_m_estimate=None,
        leading_edge_arrival_minutes=None,
        model_used=_model_used(model_variant),
        disclaimer=DISCLAIMER + " (此湖未建立下游 DEM,無法推估,不以虛構資料填補。)",
        data_sources=[DEM_SOURCE],
    )


def _dem_screening_output(
    lake_id: str,
    breach_scenario: str,
    vol_million: float,
    res: dict,
) -> InundationOutput:
    warnings = " ".join(res.get("warnings", []))
    envelope_note = (
        "主圖層採保守可達影響包絡線,"
        if res.get("used_envelope_as_polygon")
        else ""
    )
    width_basis = (
        "DEM 地形谷寬"
        if res.get("corridor_width_basis") == "dem_valley_p90"
        else "水量公式回退"
    )
    expand_note = (
        f"corridor 已由 {res.get('base_corridor_width_m', 0):.0f}m "
        f"自動擴展至 {res.get('corridor_width_m', 0):.0f}m,"
        if res.get("expanded_corridor")
        else ""
    )
    return InundationOutput(
        lake_id=lake_id,
        inundation_polygon=res["polygon"],
        envelope_polygon=res["envelope"],
        max_depth_m_estimate=res["max_depth_m"],
        leading_edge_arrival_minutes=res["arrival_minutes"],
        model_used=MODEL_DEM_SCREENING,
        disclaimer=(
            DISCLAIMER
            + f" 模型:dem-screening,情境:{breach_scenario},釋出體積約 {vol_million:.0f} 百萬 m³,"
            + f"DEM 推估流路長約 {res.get('path_length_m', 0) / 1000:.1f} km,"
            + envelope_note
            + expand_note
            + f"谷地 corridor 約 {res.get('corridor_width_m', 0):.0f} m({width_basis}),"
            + f"實際填入 {res.get('volume_placed_m3', 0) / 1_000_000:.1f} 百萬 m³。"
            + (f" {warnings}" if warnings else "")
        ),
        volume_placed_million_m3=round(res.get("volume_placed_m3", 0) / 1_000_000, 3),
        data_sources=[DEM_SOURCE],
    )


def _mvp_output(
    lake_id: str,
    breach_scenario: str,
    vol_million: float,
    res: dict,
) -> InundationOutput:
    return InundationOutput(
        lake_id=lake_id,
        inundation_polygon=res["polygon"],
        max_depth_m_estimate=res["max_depth_m"],
        leading_edge_arrival_minutes=res["arrival_minutes"],
        model_used=MODEL,
        disclaimer=(
            DISCLAIMER
            + f" 模型:mvp,情境:{breach_scenario},釋出體積約 {vol_million:.0f} 百萬 m³,"
            + f"淹水水位約 {res['level_m']} m。"
        ),
        data_sources=[DEM_SOURCE],
    )


async def estimate_inundation(
    lake_id: str,
    breach_scenario: str = "full",
    breach_volume_million_m3: float | None = None,
    model_variant: str = "mvp",
) -> InundationOutput:
    cat = load_catalog()
    lake = cat.get(lake_id)
    if lake is None or not has_dem(lake_id):
        return _empty_output(lake_id, model_variant)

    vol_million = resolve_breach_volume_million_m3(
        lake,
        breach_scenario,
        breach_volume_million_m3,
    )
    volume_m3 = vol_million * 1_000_000
    centroid = (lake.location.lon, lake.location.lat)

    if model_variant == "dem_screening":
        res = estimate_flood_dem_screening_runtime(lake_id, volume_m3, centroid)
        return _dem_screening_output(lake_id, breach_scenario, vol_million, res)

    res = estimate_flood(lake_id, volume_m3, centroid)
    return _mvp_output(lake_id, breach_scenario, vol_million, res)
