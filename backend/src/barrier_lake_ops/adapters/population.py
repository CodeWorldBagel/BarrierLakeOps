"""人口 adapter — 讀前處理的村里界 GeoJSON + 村里人口,做空間相交。

資料源:內政部村里界(政府資料開放授權條款 1.0)、內政部 村里戶數/單一年齡人口。
前處理見 scripts/prep_geo.py。執行期只用 shapely(無 GDAL)。
"""

from __future__ import annotations

import json
from functools import lru_cache

from shapely.geometry import shape

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


def intersect_population(polygon_geojson: dict) -> dict:
    """回傳受影響村里(與輸入 polygon 相交)及人口統計。"""
    geom = polygon_geojson.get("geometry", polygon_geojson)
    try:
        flood = shape(geom)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"無效的 GeoJSON polygon: {exc}") from exc
    if not flood.is_valid:
        flood = flood.buffer(0)

    villages, pop = _load_villages()
    affected = []
    tot_house = tot_pop = tot_eld = tot_chi = 0
    for props, vgeom in villages:
        if not flood.intersects(vgeom):
            continue
        code = props.get("villcode")
        p = pop.get(code, {})
        house = int(p.get("households", 0) or 0)
        population = int(p.get("population", 0) or 0)
        eld = int(p.get("elderly_65plus", 0) or 0)
        chi = int(p.get("children_under6", 0) or 0)
        affected.append(
            {
                "village_code": code,
                "county": props.get("county"),
                "town": props.get("town"),
                "village": props.get("village"),
                "households": house,
                "population": population,
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
