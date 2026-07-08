"""即時下載政府開放資料(村里界 + 人口)→ 過濾各湖下游村里 → 供收集器寫 DB。

來源:
- 村里界:data.gov.tw 7438 → tgos.tw ZIP(含全國 shapefile,約 22MB)。
- 人口:data.gov.tw 77132 → moi.gov.tw 多期「全國月報」CSV,取最新一期。

過濾邏輯與 ``scripts/prep_geo.py`` 一致(下游 bbox 外擴 + 相交)。全部為同步阻塞 I/O,
呼叫端請以 ``asyncio.to_thread`` 包起來;失敗時拋例外,由收集器 fallback 本機預處理檔。
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import shapefile  # pyshp

from .catalog import load_catalog
from .config import get_settings

logger = logging.getLogger("barrier_lake_ops.live_sources")

MARGIN_DEG = 0.06  # 下游 bbox 外擴(約 6.5km),與 prep_geo 一致
# 村里界 ZIP(tgos.tw)對非台灣 IP 會 403 地理封鎖;界線屬靜態(年才變),
# 故 fetch_village_rows 改用本機 committed 村里界 + 只 live 下載人口(月變)。
VILLAGE_ZIP_URL = (
    "https://www.tgos.tw/tgos/VirtualDir/Product/"
    "a04697c8-64db-450a-a105-3eb471c45abd/村(里)界(TWD97經緯度)1150511.zip"
)
POP_DATASET_API = "https://data.gov.tw/api/v2/rest/dataset/77132"
# 部分政府站對預設 python UA 會擋,帶瀏覽器 UA 降低 403 風險
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def _safe_extract_zip(fileobj, dest: str) -> None:
    """解壓 ZIP,逐一驗證每個 entry 目標仍落在 dest 內,阻擋 zip-slip(路徑穿越覆寫)。"""
    dest_root = Path(dest).resolve()
    with zipfile.ZipFile(fileobj) as zf:
        for member in zf.namelist():
            target = (dest_root / member).resolve()
            if target != dest_root and dest_root not in target.parents:
                raise RuntimeError(f"ZIP entry 逸出解壓目錄,已拒絕: {member!r}")
        zf.extractall(dest_root)


def _lake_bboxes() -> list[tuple[float, float, float, float]]:
    out = []
    for lk in load_catalog().lakes:
        b = lk.downstream_dem_bbox
        if b:
            out.append((b[0] - MARGIN_DEG, b[1] - MARGIN_DEG, b[2] + MARGIN_DEG, b[3] + MARGIN_DEG))
    return out


def _bbox_intersect(a, b) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def download_villages(timeout: float = 180) -> tuple[list[dict], set[str]]:
    """下載全國村里界 ZIP → 過濾下游村里。回傳 (features, kept_codes)。"""
    bboxes = _lake_bboxes()
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=_HEADERS) as client:
        resp = client.get(VILLAGE_ZIP_URL)
        resp.raise_for_status()
        blob = resp.content
    feats: list[dict] = []
    kept: set[str] = set()
    with TemporaryDirectory() as td:
        _safe_extract_zip(io.BytesIO(blob), td)
        shps = sorted(Path(td).rglob("*.shp"))
        if not shps:
            raise RuntimeError("ZIP 內無 .shp")
        # ZIP 含多個 shapefile;取全國檔 VILLAGE_NLSC_*(否則取最大者)
        shp_path = next(
            (p for p in shps if "VILLAGE_NLSC" in p.name.upper()),
            max(shps, key=lambda p: p.stat().st_size),
        )
        reader = shapefile.Reader(str(shp_path), encoding="utf-8")
        fields = [f[0] for f in reader.fields[1:]]
        for sr in reader.iterShapeRecords():
            if not any(_bbox_intersect(sr.shape.bbox, b) for b in bboxes):
                continue
            rec = dict(zip(fields, list(sr.record)))
            code = str(rec.get("VILLCODE", "")).strip()
            kept.add(code)
            feats.append(
                {
                    "villcode": code,
                    "county": rec.get("COUNTYNAME"),
                    "town": rec.get("TOWNNAME"),
                    "village": rec.get("VILLNAME"),
                    "geometry": sr.shape.__geo_interface__,
                }
            )
    return feats, kept


def _latest_pop_csv_url(timeout: float = 30) -> tuple[str, str]:
    """挑 77132 中最新一期(resourceDescription 開頭民國年月最大)的 CSV。"""
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=_HEADERS) as client:
        resp = client.get(POP_DATASET_API)
        resp.raise_for_status()
        dists = [
            x for x in resp.json().get("result", {}).get("distribution", [])
            if x.get("resourceFormat") == "CSV"
        ]
    if not dists:
        raise RuntimeError("77132 無 CSV distribution")

    def ym(x) -> int:
        m = re.match(r"(\d{5,6})", x.get("resourceDescription", "") or "")
        return int(m.group(1)) if m else -1

    best = max(dists, key=ym)
    return best["resourceDownloadUrl"], str(ym(best))


def download_population(kept_codes: set[str], timeout: float = 120) -> tuple[dict, str]:
    """下載最新一期全國人口 CSV → 過濾 kept_codes。回傳 (pop_by_code, 期別)。"""
    url, period = _latest_pop_csv_url()
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=_HEADERS) as client:
        resp = client.get(url)
        resp.raise_for_status()
        text = resp.content.decode("utf-8-sig", errors="replace")
    pop: dict[str, dict] = {}
    for row in csv.DictReader(io.StringIO(text)):
        code = (row.get("區域別代碼") or "").strip()
        if code not in kept_codes:
            continue
        children = elderly = 0
        for col, val in row.items():
            if not val or "歲" not in col:
                continue
            try:
                n = int(val)
            except (ValueError, TypeError):
                continue
            if "100" in col and "以上" in col:
                elderly += n
                continue
            try:
                age = int(col.split("歲")[0])
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
    return pop, period


def fetch_village_rows() -> tuple[list[dict], str]:
    """合併村里界(本機 committed,靜態,避開 tgos.tw 地理封鎖)+ 人口(live 下載,月變)。

    回傳 (rows, 來源描述)。人口下載失敗時拋例外,由收集器 fallback 純本機檔。
    """
    d = get_settings().data_dir / "villages"
    gj = json.loads((d / "villages.geojson").read_text(encoding="utf-8"))
    boundaries: list[tuple[str, dict, dict]] = []
    kept: set[str] = set()
    for f in gj.get("features", []):
        p = f.get("properties", {})
        code = str(p.get("villcode") or "").strip()
        if not code:
            continue
        kept.add(code)
        boundaries.append((code, p, f.get("geometry")))

    pop, period = download_population(kept)
    rows = []
    for code, p, geom in boundaries:
        pp = pop.get(code, {})
        rows.append(
            {
                "village_code": code,
                "county": p.get("county"),
                "town": p.get("town"),
                "village": p.get("village"),
                "geometry": geom,
                "households": int(pp.get("households", 0) or 0),
                "population": int(pp.get("population", 0) or 0),
                "elderly_65plus": int(pp.get("elderly_65plus", 0) or 0),
                "children_under6": int(pp.get("children_under6", 0) or 0),
            }
        )
    return rows, f"村里界:本機靜態 + 人口:data.gov.tw 即時(期別 {period})"
