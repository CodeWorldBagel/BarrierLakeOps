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
        p = pop.get(props.get("villcode"), {})
        out.append(
            (
                geom,
                {
                    "village_code": props.get("villcode"),
                    "county": props.get("county"),
                    "town": props.get("town"),
                    "village": props.get("village"),
                    "households": int(p.get("households", 0) or 0),
                    "population": int(p.get("population", 0) or 0),
                    "elderly_65plus": int(p.get("elderly_65plus", 0) or 0),
                    "children_under6": int(p.get("children_under6", 0) or 0),
                },
            )
        )
    return out


def villages_from_db_rows(rows) -> list[tuple]:
    """把 DB Village ORM 列轉成統一村里記錄格式。"""
    out: list[tuple] = []
    for r in rows:
        if not r.geometry:
            continue
        try:
            geom = shape(r.geometry)
        except Exception:  # noqa: BLE001
            continue
        out.append(
            (
                geom,
                {
                    "village_code": r.village_code, "county": r.county, "town": r.town,
                    "village": r.village, "households": r.households or 0,
                    "population": r.population or 0, "elderly_65plus": r.elderly_65plus or 0,
                    "children_under6": r.children_under6 or 0,
                },
            )
        )
    return out


def intersect_population(polygon_geojson: dict, villages: list[tuple] | None = None) -> dict:
    """回傳受影響村里(與輸入 polygon 相交)及人口統計。

    villages 為統一村里記錄(DB 優先);None 則讀本機預處理檔。
    """
    geom = polygon_geojson.get("geometry", polygon_geojson)
    try:
        flood = shape(geom)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"無效的 GeoJSON polygon: {exc}") from exc
    if not flood.is_valid:
        flood = flood.buffer(0)

    if villages is None:
        villages = _load_villages_from_files()
    affected = []
    tot_house = tot_pop = tot_eld = tot_chi = 0
    for vgeom, f in villages:
        if not flood.intersects(vgeom):
            continue
        affected.append(
            {
                "village_code": f["village_code"], "county": f["county"],
                "town": f["town"], "village": f["village"],
                "households": f["households"], "population": f["population"],
            }
        )
        tot_house += f["households"]
        tot_pop += f["population"]
        tot_eld += f["elderly_65plus"]
        tot_chi += f["children_under6"]

    affected.sort(key=lambda v: v["population"], reverse=True)
    return {
        "affected_villages": affected,
        "total_households": tot_house,
        "total_population": tot_pop,
        "elderly_65plus": tot_eld,
        "children_under6": tot_chi,
    }
