"""前處理:把大型 geo 原始資料轉成執行期可用的小檔(避免執行期依賴 GDAL / 大檔)。

產出(committed,供 Zeabur 原生部署直接使用):
  data/villages/villages.geojson   ← 各湖下游範圍的村里界(WGS84 lon/lat)
  data/villages/population.json     ← 對應村里的戶數/人口/老幼(內政部)
  data/dem/<lake_id>.npy / .json    ← 各湖下游 SRTM 高程格點(NASA 公有領域)

原始檔(data/raw/,gitignore):
  VILLAGE_NLSC_*.shp/.dbf  ← 內政部村里界(TWD97 經緯度)
  village_population.csv    ← 內政部 村里戶數、單一年齡人口

用法:
  uv run python scripts/prep_geo.py            # 全部
  uv run python scripts/prep_geo.py --no-dem   # 跳過 DEM(免網路)
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import httpx
import shapefile  # pyshp

BACKEND = Path(__file__).resolve().parents[1]
RAW = BACKEND / "data" / "raw"
VILL_DIR = BACKEND / "data" / "villages"
DEM_DIR = BACKEND / "data" / "dem"
SHP = RAW / "VILLAGE_NLSC_1150511.shp"
POP_CSV = RAW / "village_population.csv"

MARGIN_DEG = 0.06  # 下游 bbox 外擴(約 6.5km),確保涵蓋可能淹水範圍


def _lake_bboxes() -> list[tuple[str, list[float]]]:
    sys.path.insert(0, str(BACKEND / "src"))
    from barrier_lake_ops.catalog import load_catalog

    out = []
    for lk in load_catalog().lakes:
        if lk.downstream_dem_bbox:
            out.append((lk.id, lk.downstream_dem_bbox))
    return out


def _expanded(bbox: list[float]) -> tuple[float, float, float, float]:
    return (
        bbox[0] - MARGIN_DEG,
        bbox[1] - MARGIN_DEG,
        bbox[2] + MARGIN_DEG,
        bbox[3] + MARGIN_DEG,
    )


def _bbox_intersect(a, b) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def process_villages() -> set[str]:
    bboxes = [_expanded(bb) for _, bb in _lake_bboxes()]
    r = shapefile.Reader(str(SHP), encoding="utf-8")
    fields = [f[0] for f in r.fields[1:]]
    features = []
    kept_codes: set[str] = set()
    for sr in r.iterShapeRecords():
        sbb = sr.shape.bbox  # (minx,miny,maxx,maxy)
        if not any(_bbox_intersect(sbb, b) for b in bboxes):
            continue
        rec = dict(zip(fields, list(sr.record)))
        code = str(rec.get("VILLCODE", "")).strip()
        kept_codes.add(code)
        features.append(
            {
                "type": "Feature",
                "geometry": sr.shape.__geo_interface__,
                "properties": {
                    "villcode": code,
                    "county": rec.get("COUNTYNAME"),
                    "town": rec.get("TOWNNAME"),
                    "village": rec.get("VILLNAME"),
                },
            }
        )
    VILL_DIR.mkdir(parents=True, exist_ok=True)
    (VILL_DIR / "villages.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[villages] kept {len(features)} 村里(下游範圍內)")
    return kept_codes


def process_population(kept_codes: set[str]) -> None:
    pop: dict[str, dict] = {}
    with open(POP_CSV, encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        for row in rd:
            code = (row.get("區域別代碼") or "").strip()
            if code not in kept_codes:
                continue
            children = elderly = 0
            for col, val in row.items():
                if not val or "歲" not in col:
                    continue
                try:
                    n = int(val)
                except ValueError:
                    continue
                age_txt = col.split("歲")[0]
                if "100" in col and "以上" in col:
                    elderly += n
                    continue
                try:
                    age = int(age_txt)
                except ValueError:
                    continue
                if age <= 5:
                    children += n
                elif age >= 65:
                    elderly += n
            pop[code] = {
                "households": int(row.get("戶數") or 0),
                "population": int(row.get("人口數") or 0),
                "elderly_65plus": elderly,
                "children_under6": children,
            }
    (VILL_DIR / "population.json").write_text(
        json.dumps(pop, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[population] matched {len(pop)} 村里人口")


def fetch_dem(grid: int = 40) -> None:
    DEM_DIR.mkdir(parents=True, exist_ok=True)
    for lake_id, bbox in _lake_bboxes():
        minlon, minlat, maxlon, maxlat = bbox
        lons = [minlon + (maxlon - minlon) * i / (grid - 1) for i in range(grid)]
        lats = [minlat + (maxlat - minlat) * j / (grid - 1) for j in range(grid)]
        # 由北到南(row 0 = maxlat),配合影像座標
        lats = list(reversed(lats))
        elev = [[None] * grid for _ in range(grid)]
        points = [(j, i, lats[j], lons[i]) for j in range(grid) for i in range(grid)]
        with httpx.Client(timeout=30) as client:
            for k in range(0, len(points), 100):
                batch = points[k : k + 100]
                locs = "|".join(f"{p[2]:.6f},{p[3]:.6f}" for p in batch)
                resp = client.get(
                    "https://api.opentopodata.org/v1/srtm30m",
                    params={"locations": locs},
                )
                resp.raise_for_status()
                results = resp.json()["results"]
                for p, res in zip(batch, results):
                    elev[p[0]][p[1]] = res.get("elevation")
                time.sleep(1.1)  # opentopodata 限速 1 req/sec
        import numpy as np

        arr = np.array(
            [[(v if v is not None else np.nan) for v in row] for row in elev],
            dtype="float32",
        )
        np.save(DEM_DIR / f"{lake_id}.npy", arr)
        (DEM_DIR / f"{lake_id}.json").write_text(
            json.dumps(
                {
                    "bbox": bbox,  # [minlon,minlat,maxlon,maxlat]
                    "shape": [grid, grid],
                    "row0": "north",
                    "source": "SRTM 30m (NASA, public domain) via opentopodata",
                }
            ),
            encoding="utf-8",
        )
        print(f"[dem] {lake_id}: {grid}x{grid} grid saved")


def main() -> None:
    do_dem = "--no-dem" not in sys.argv
    kept = process_villages()
    process_population(kept)
    if do_dem:
        fetch_dem()
    print("prep_geo done.")


if __name__ == "__main__":
    main()
