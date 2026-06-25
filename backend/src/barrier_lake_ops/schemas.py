"""6 個 Tool 的 I/O Pydantic models(MCP 與 REST 共用同一份 schema)。

對齊 docs/submission.md §二「Tool 規格」。所有對外輸出皆含 ``data_sources``。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 共用
# --------------------------------------------------------------------------- #
class AlertLevel(str, Enum):
    green = "green"
    yellow = "yellow"
    orange = "orange"
    red = "red"
    unknown = "unknown"


class DataSource(BaseModel):
    """每筆輸出的資料來源揭露(來源 / 授權 / attribution)。"""

    source: str = Field(..., description="資料源名稱")
    license: str = Field(..., description="授權條款,如『政府資料開放授權條款 1.0』")
    attribution: str = Field("", description="標註文字")
    url: str = Field("", description="資料源連結")
    retrieved_at: str | None = Field(None, description="取得時間 RFC3339")


class Freshness(str, Enum):
    fresh = "fresh"
    stale = "stale"
    unavailable = "unavailable"


# --------------------------------------------------------------------------- #
# Tool 0 — list_lakes
# --------------------------------------------------------------------------- #
class LakeSummary(BaseModel):
    id: str
    name: str
    status: Literal["active", "monitoring", "archived"] = "monitoring"
    alert_level: AlertLevel = AlertLevel.unknown
    formed_at: str | None = None
    lat: float | None = None
    lon: float | None = None
    headroom_m: float | None = None


class ListLakesInput(BaseModel):
    status_filter: Literal["active", "monitoring", "all"] = "all"


class ListLakesOutput(BaseModel):
    lakes: list[LakeSummary]
    total: int
    data_sources: list[DataSource]


# --------------------------------------------------------------------------- #
# Tool 1 — get_lake_status
# --------------------------------------------------------------------------- #
class LakeStatusOutput(BaseModel):
    lake_id: str
    name: str
    water_level_m: float | None = None
    storage_million_m3: float | None = None
    overflow_threshold_m: float | None = None
    headroom_m: float | None = None
    alert_level: AlertLevel = AlertLevel.unknown
    last_updated: str | None = None
    data_freshness_minutes: int | None = None
    freshness: Freshness = Freshness.fresh
    note: str | None = None
    data_sources: list[DataSource] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Tool 2 — get_upstream_weather
# --------------------------------------------------------------------------- #
class RainStation(BaseModel):
    station_id: str
    name: str
    rainfall_1h_mm: float | None = None
    rainfall_3h_mm: float | None = None
    rainfall_24h_mm: float | None = None
    obs_time: str | None = None


class UpstreamWeatherInput(BaseModel):
    hours_back: int = 24
    hours_forward: int = 24


class UpstreamWeatherOutput(BaseModel):
    lake_id: str
    stations: list[RainStation]
    forecast_24h_mm_max: float | None = None
    alert_level: AlertLevel = AlertLevel.unknown
    rationale: str = ""
    freshness: Freshness = Freshness.fresh
    data_sources: list[DataSource] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Tool 3 — estimate_inundation
# --------------------------------------------------------------------------- #
class StageResultModel(BaseModel):
    """一個推估步驟的結構化輸出,供 LLM 逐步解說。"""
    name: str
    summary: str
    key_values: dict[str, Any] = Field(default_factory=dict)
    detail: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class InundationInput(BaseModel):
    breach_scenario: Literal["partial", "full"] = "full"
    breach_volume_million_m3: float | None = None
    model_variant: Literal["mvp", "dem_screening"] = "mvp" # "directional", "impact_area", "seed_fill"


class InundationOutput(BaseModel):
    lake_id: str
    inundation_polygon: dict[str, Any] = Field(
        ..., description="GeoJSON Feature/FeatureCollection"
    )
    max_depth_m_estimate: float | None = None
    leading_edge_arrival_minutes: int | None = None
    model_used: str
    disclaimer: str
    data_sources: list[DataSource] = Field(default_factory=list)
    # 進階模型新增欄位(向下相容,mvp 時為 None)
    steps: list[StageResultModel] | None = None
    envelope_polygon: dict[str, Any] | None = None
    volume_placed_million_m3: float | None = None


# --------------------------------------------------------------------------- #
# Tool 4 — get_affected_population
# --------------------------------------------------------------------------- #
class AffectedVillage(BaseModel):
    village_code: str | None = None
    county: str | None = None
    town: str | None = None
    village: str | None = None
    households: int | None = None
    population: int | None = None
    affected_area_ratio: float | None = None
    population_estimate_ratio: float | None = None


class VulnerableEstimate(BaseModel):
    elderly_65plus: int | None = None
    children_under6: int | None = None


class PopulationInput(BaseModel):
    polygon: dict[str, Any] = Field(..., description="GeoJSON(通常為 Tool 3 輸出)")


class PopulationOutput(BaseModel):
    affected_villages: list[AffectedVillage]
    total_households: int
    total_population: int
    vulnerable_estimate: VulnerableEstimate
    data_sources: list[DataSource] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Tool 5 — compose_briefing
# --------------------------------------------------------------------------- #
class BriefingAudience(str, Enum):
    command_center = "command_center"  # 指揮官
    public = "public"  # 民眾
    media = "media"  # 媒體
    multi_lake_overview = "multi_lake_overview"  # 多湖概覽


class ComposeBriefingInput(BaseModel):
    context: dict[str, Any] = Field(..., description="Tool 0–4 的回傳集合")
    audience: BriefingAudience = BriefingAudience.command_center
    lake_id: str | None = None


class BriefingOutput(BaseModel):
    status_color: AlertLevel = AlertLevel.unknown
    headline: str
    key_facts: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    natural_language: str = ""
    ai_confidence: float = Field(0.0, ge=0.0, le=1.0)
    data_sources_used: list[DataSource] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Chat(reference client agent)
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    message: str
    lake_id: str | None = None
    session_id: str | None = None
