"""人口 adapter — 讀前處理的村里界 GeoJSON + 村里人口,做空間相交。

資料源:內政部村里界(政府資料開放授權條款 1.0)、內政部 村里戶數/單一年齡人口。
前處理見 scripts/prep_geo.py。執行期只用 shapely(無 GDAL)。
"""

from __future__ import annotations

import json
from functools import lru_cache

from shapely.geometry import GeometryCollection, Point, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from ..config import get_settings
from ..schemas import DataSource

SOURCE_BOUNDARY = DataSource(
    source="內政部 村(里)界(TWD97 經緯度)",
    license="政府資料開放授權條款 1.0",
    attribution="資料來源:內政部國土測繪中心",
    url="https://data.gov.tw/dataset/7438",
)
SOURCE_POP = DataSource(
    source="內政部 村里戶數、單一年齡人口",
    license="政府資料開放授權條款 1.0",
    attribution="資料來源:內政部戶政司",
    url="https://data.gov.tw/dataset/77132",
)


# 統一村里記錄格式:(shapely 幾何, 欄位含人口)。檔案版與 DB 版都產出這個格式。
@lru_cache
def _load_villages_from_files() -> list[tuple]:
    d = get_settings().data_dir / "villages"
    gj = json.loads((d / "villages.geojson").read_text(encoding="utf-8"))
    pop = json.loads((d / "population.json").read_text(encoding="utf-8"))
    out: list[tuple] = []
    for feat in gj["features"]:
        try:
            geom = shape(feat["geometry"])
        except Exception:  # noqa: BLE001
            continue
        props = feat["properties"]
        pinfo = pop.get(props.get("villcode"), {})
        out.append(
            (
                geom,
                {
                    "village_code": props.get("villcode"),
                    "county": props.get("county"),
                    "town": props.get("town"),
                    "village": props.get("village"),
                    "households": int(pinfo.get("households", 0) or 0),
                    "population": int(pinfo.get("population", 0) or 0),
                    "elderly_65plus": int(pinfo.get("elderly_65plus", 0) or 0),
                    "children_under6": int(pinfo.get("children_under6", 0) or 0),
                },
            )
        )
    return out


def villages_from_db_rows(rows) -> list[tuple]:
    """把 DB Village ORM 列轉成統一村里記錄格式。"""
    out: list[tuple] = []
    for row in rows:
        if not row.geometry:
            continue
        try:
            geom = shape(row.geometry)
        except Exception:  # noqa: BLE001
            continue
        out.append(
            (
                geom,
                {
                    "village_code": row.village_code,
                    "county": row.county,
                    "town": row.town,
                    "village": row.village,
                    "households": row.households or 0,
                    "population": row.population or 0,
                    "elderly_65plus": row.elderly_65plus or 0,
                    "children_under6": row.children_under6 or 0,
                },
            )
        )
    return out


def _build_spatial_index(villages: list[tuple]):
    geoms = [geom for geom, _fields in villages]
    tree = STRtree(geoms) if geoms else None
    index_by_geometry_id = {id(geom): idx for idx, geom in enumerate(geoms)}
    return villages, index_by_geometry_id, tree


@lru_cache
def _load_village_spatial_index_from_files():
    return _build_spatial_index(_load_villages_from_files())


def clear_population_cache() -> None:
    _load_villages_from_files.cache_clear()
    _load_village_spatial_index_from_files.cache_clear()


def _candidate_villages(query_geom, spatial_index):
    villages, index_by_geometry_id, tree = spatial_index
    if tree is None:
        return []
    raw_matches = tree.query(query_geom)
    indexes: list[int] = []
    for match in raw_matches:
        try:
            idx = int(match)
        except (TypeError, ValueError):
            idx = index_by_geometry_id.get(id(match), -1)
        if 0 <= idx < len(villages):
            indexes.append(idx)
    return [villages[idx] for idx in sorted(set(indexes))]


def _empty_result() -> dict:
    return {
        "affected_villages": [],
        "total_households": 0,
        "total_population": 0,
        "elderly_65plus": 0,
        "children_under6": 0,
    }


def _shape_geojson(geojson: dict):
    if geojson.get("type") == "FeatureCollection":
        geoms = []
        for feat in geojson.get("features", []):
            geom = feat.get("geometry") if isinstance(feat, dict) else None
            if geom:
                geoms.append(shape(geom))
        return unary_union(geoms) if geoms else GeometryCollection()

    return shape(geojson.get("geometry", geojson))


def locate_point(lon: float, lat: float) -> dict | None:
    """Return village administrative properties containing a lon/lat point."""
    point = Point(lon, lat)
    for vgeom, fields in _candidate_villages(
        point, _load_village_spatial_index_from_files()
    ):
        if not vgeom.is_valid:
            vgeom = vgeom.buffer(0)
        if vgeom.is_empty:
            continue
        if vgeom.contains(point) or vgeom.touches(point):
            return {
                "village_code": fields.get("village_code"),
                "county": fields.get("county"),
                "town": fields.get("town"),
                "village": fields.get("village"),
            }
    return None


def intersect_population(polygon_geojson: dict, villages: list[tuple] | None = None) -> dict:
    """回傳受影響村里(與輸入 polygon 相交)及人口統計。

    villages 為統一村里記錄(DB 優先);None 則讀本機預處理檔。
    """
    try:
        flood = _shape_geojson(polygon_geojson)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"無效的 GeoJSON polygon: {exc}") from exc
    if flood.is_empty:
        return _empty_result()
    if not flood.is_valid:
        flood = flood.buffer(0)
    if flood.is_empty:
        return _empty_result()

    if villages is None:
        spatial_index = _load_village_spatial_index_from_files()
    else:
        spatial_index = _build_spatial_index(villages)

    affected = []
    tot_house = tot_pop = tot_eld = tot_chi = 0
    for vgeom, fields in _candidate_villages(flood, spatial_index):
        if not flood.intersects(vgeom):
            continue
        if not vgeom.is_valid:
            vgeom = vgeom.buffer(0)
        if vgeom.is_empty or vgeom.area <= 0:
            continue
        inter = flood.intersection(vgeom)
        if inter.is_empty or inter.area <= 0:
            continue
        affected_area_ratio = max(0.0, min(1.0, float(inter.area / vgeom.area)))
        population_estimate_ratio = min(1.0, affected_area_ratio * 1.30)

        households = int(round(int(fields["households"]) * population_estimate_ratio))
        population = int(round(int(fields["population"]) * population_estimate_ratio))
        elderly = int(round(int(fields["elderly_65plus"]) * population_estimate_ratio))
        children = int(round(int(fields["children_under6"]) * population_estimate_ratio))
        affected.append(
            {
                "village_code": fields["village_code"],
                "county": fields["county"],
                "town": fields["town"],
                "village": fields["village"],
                "households": households,
                "population": population,
                "affected_area_ratio": round(affected_area_ratio, 4),
                "population_estimate_ratio": round(population_estimate_ratio, 4),
            }
        )
        tot_house += households
        tot_pop += population
        tot_eld += elderly
        tot_chi += children

    affected.sort(key=lambda v: v["population"], reverse=True)
    return {
        "affected_villages": affected,
        "total_households": tot_house,
        "total_population": tot_pop,
        "elderly_65plus": tot_eld,
        "children_under6": tot_chi,
    }
