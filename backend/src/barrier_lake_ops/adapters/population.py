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


@lru_cache
def _load_villages():
    d = get_settings().data_dir / "villages"
    gj = json.loads((d / "villages.geojson").read_text(encoding="utf-8"))
    pop = json.loads((d / "population.json").read_text(encoding="utf-8"))
    villages = []
    for feat in gj["features"]:
        try:
            geom = shape(feat["geometry"])
        except Exception:  # noqa: BLE001
            continue
        villages.append((feat["properties"], geom))
    return villages, pop


@lru_cache
def _load_village_spatial_index():
    villages, pop = _load_villages()
    geoms = [geom for _props, geom in villages]
    tree = STRtree(geoms) if geoms else None
    index_by_geometry_id = {id(geom): idx for idx, geom in enumerate(geoms)}
    return villages, pop, index_by_geometry_id, tree


def clear_population_cache() -> None:
    load_cache_clear = getattr(_load_villages, "cache_clear", None)
    if load_cache_clear is not None:
        load_cache_clear()
    _load_village_spatial_index.cache_clear()


def _candidate_villages(query_geom):
    villages, _pop, index_by_geometry_id, tree = _load_village_spatial_index()
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


def _population_by_code():
    _villages, pop, _index_by_geometry_id, _tree = _load_village_spatial_index()
    return pop


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
    for props, vgeom in _candidate_villages(point):
        if not vgeom.is_valid:
            vgeom = vgeom.buffer(0)
        if vgeom.is_empty:
            continue
        if vgeom.contains(point) or vgeom.touches(point):
            return {
                "village_code": props.get("villcode"),
                "county": props.get("county"),
                "town": props.get("town"),
                "village": props.get("village"),
            }
    return None


def intersect_population(polygon_geojson: dict) -> dict:
    """回傳受影響村里(與輸入 polygon 相交)及人口統計。"""
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

    pop = _population_by_code()
    affected = []
    tot_house = tot_pop = tot_eld = tot_chi = 0
    for props, vgeom in _candidate_villages(flood):
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

        code = props.get("villcode")
        p = pop.get(code, {})
        source_house = int(p.get("households", 0) or 0)
        source_population = int(p.get("population", 0) or 0)
        source_eld = int(p.get("elderly_65plus", 0) or 0)
        source_chi = int(p.get("children_under6", 0) or 0)
        house = int(round(source_house * population_estimate_ratio))
        population = int(round(source_population * population_estimate_ratio))
        eld = int(round(source_eld * population_estimate_ratio))
        chi = int(round(source_chi * population_estimate_ratio))
        affected.append(
            {
                "village_code": code,
                "county": props.get("county"),
                "town": props.get("town"),
                "village": props.get("village"),
                "households": house,
                "population": population,
                "affected_area_ratio": round(affected_area_ratio, 4),
                "population_estimate_ratio": round(population_estimate_ratio, 4),
            }
        )
        tot_house += house
        tot_pop += population
        tot_eld += eld
        tot_chi += chi

    affected.sort(key=lambda v: v["population"], reverse=True)
    return {
        "affected_villages": affected,
        "total_households": tot_house,
        "total_population": tot_pop,
        "elderly_65plus": tot_eld,
        "children_under6": tot_chi,
    }
