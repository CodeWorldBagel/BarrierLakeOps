"""將歷史堰塞湖案例 xlsx 同步進 lake_catalog.yaml（只新增，不覆蓋）。

用法:
    uv run python scripts/sync_from_xlsx.py <path/to/清冊.xlsx> [--dry-run]

去重邏輯（雙層）:
  1. id 比對: "{county_slug}-{name_slug}-{year}" 對比 yaml 現有 id
  2. 地域指紋: (year, county, town) 相同視為同一筆（名稱拼字不同也去重）
  以上任一命中即跳過。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from barrier_lake_ops.importers.xlsx import load_historical_cases
from barrier_lake_ops.schemas import HistoricalLakeCase, LandslideDAMStatus

_COUNTY_SLUG: dict[str, str] = {
    "臺北市": "taipei",  "台北市": "taipei",
    "新北市": "xinbei",  "基隆市": "keelung",
    "桃園市": "taoyuan", "新竹市": "xinzhu",  "新竹縣": "xinzhu",
    "苗栗縣": "miaoli",  "臺中市": "taichung","台中市": "taichung",
    "彰化縣": "changhua","南投縣": "nantou",
    "雲林縣": "yunlin",  "嘉義市": "chiayi",  "嘉義縣": "chiayi",
    "臺南市": "tainan",  "台南市": "tainan",
    "高雄市": "kaohsiung","屏東縣": "pingdong",
    "宜蘭縣": "yilan",   "花蓮縣": "hualian", "臺東縣": "taitung", "台東縣": "taitung",
    "澎湖縣": "penghu",  "金門縣": "kinmen",  "連江縣": "lienchiang",
}

_SLUG_RE = re.compile(r"[^\w]+")


def _slugify(s: str) -> str:
    s = s.strip().lower()
    return _SLUG_RE.sub("-", s).strip("-")


def _county_slug(county: str) -> str:
    return _COUNTY_SLUG.get(county, _slugify(county))


def _make_id(case: HistoricalLakeCase) -> str:
    return f"{_county_slug(case.county)}-{_slugify(case.name)}-{case.year}"


_COORD_PRECISION = 2  # 0.01° ≈ 1 km，足以去重同一座湖


def _round_coord(v: float | None) -> float | None:
    return round(v, _COORD_PRECISION) if v is not None else None


def _region_fingerprint(case: HistoricalLakeCase) -> tuple | None:
    """(year, lon, lat) — 座標取壩址，無壩址取崩塌源；均無則回 None（不納入指紋去重）。"""
    lon = _round_coord(case.dam_lon) or _round_coord(case.collapse_lon)
    lat = _round_coord(case.dam_lat) or _round_coord(case.collapse_lat)
    if lon is None or lat is None:
        return None
    return (case.year, lon, lat)


def _existing_fingerprints(catalog: dict) -> set[tuple]:
    """從現有 yaml centroid + formed_at 抽取 (year, lon, lat) 指紋。"""
    fps: set[tuple] = set()
    year_re = re.compile(r"(\d{4})")
    for lake in catalog.get("lakes", []):
        formed = lake.get("formed_at", "")
        year_m = year_re.search(str(formed))
        if not year_m:
            continue
        year = int(year_m.group(1))
        centroid = lake.get("location", {}).get("centroid")
        if centroid and len(centroid) == 2:
            lon = round(centroid[0], _COORD_PRECISION)
            lat = round(centroid[1], _COORD_PRECISION)
            fps.add((year, lon, lat))
    return fps


_STATUS_MAP: dict[str, str] = {
    LandslideDAMStatus.disappeared: "archived",
    LandslideDAMStatus.stable:      "archived",
    LandslideDAMStatus.monitoring:  "monitoring",
    LandslideDAMStatus.unknown:     "archived",
}


def _case_to_entry(case: HistoricalLakeCase, lake_id: str) -> dict:
    entry: dict = {
        "id":      lake_id,
        "name_zh": case.name,
        "status":  _STATUS_MAP.get(case.status, "archived"),
    }

    formed = case.formed_at.strip() if case.formed_at else ""
    if re.match(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", formed):
        entry["formed_at"] = formed.replace("/", "-")
    elif case.year:
        entry["formed_at"] = f"{case.year}-01-01"

    if case.dam_lon is not None and case.dam_lat is not None:
        entry["location"] = {"centroid": [round(case.dam_lon, 6), round(case.dam_lat, 6)]}
    elif case.collapse_lon is not None and case.collapse_lat is not None:
        entry["location"] = {"centroid": [round(case.collapse_lon, 6), round(case.collapse_lat, 6)]}

    if case.storage_10k_m3 is not None:
        entry["reference_state"] = {
            "storage_million_m3": round(case.storage_10k_m3 / 100, 4),
            "note": "歷史清冊蓄水量欄位換算自萬立方公尺，非即時監測值。",
        }

    note_parts: list[str] = []
    for label, val in [
        ("縣市", case.county),
        ("鄉鎮", case.town),
        ("村里", case.village),
        ("地標", case.landmark),
        ("誘因", "" if case.trigger.value == "unknown" else case.trigger.value),
        ("事件", case.event_name),
        ("持續時間(日)", case.duration_days),
        ("潰決時間", case.breached_at),
        ("潰決原因", case.breach_cause),
        ("坐落區位", "" if case.location_type.value == "unknown" else case.location_type.value),
        ("原始項次", str(case.seq)),
    ]:
        if val:
            note_parts.append(f"{label}: {val}")
    entry["note"] = "; ".join(note_parts)

    return entry


def _append_entries(catalog_path: Path, entries: list[dict]) -> None:
    """Append new entries as properly-indented YAML blocks."""
    block = ""
    for entry in entries:
        entry_yaml = yaml.dump(
            entry, allow_unicode=True, sort_keys=False, default_flow_style=False
        )
        lines = entry_yaml.splitlines()
        block += f"\n  - {lines[0]}\n"
        for line in lines[1:]:
            block += f"    {line}\n"

    with catalog_path.open("a", encoding="utf-8") as f:
        f.write(block)


_DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
_XLSX_PATTERN = "歷史堰塞湖案例清冊-*.xlsx"


def _find_latest_xlsx() -> Path:
    """docs/ 下找最新的 歷史堰塞湖案例清冊-*.xlsx（依檔名時間戳排序取最新）。"""
    matches = sorted(_DOCS_DIR.glob(_XLSX_PATTERN))
    if not matches:
        raise FileNotFoundError(
            f"在 {_DOCS_DIR} 找不到 {_XLSX_PATTERN}，請先將清冊放進 docs/ 目錄"
        )
    return matches[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync xlsx → lake_catalog.yaml")
    parser.add_argument(
        "xlsx", nargs="?", default=None,
        help="歷史清冊 xlsx 路徑（省略時自動找 docs/歷史堰塞湖案例清冊-*.xlsx 最新版）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只印結果，不寫入")
    parser.add_argument(
        "--catalog",
        default=str(Path(__file__).parent.parent / "lake_catalog.yaml"),
        help="lake_catalog.yaml 路徑（預設 backend/lake_catalog.yaml）",
    )
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx) if args.xlsx else _find_latest_xlsx()
    print(f"[xlsx] 使用檔案：{xlsx_path.name}")
    result = load_historical_cases(xlsx_path)
    print(f"[xlsx] 解析完成：{result.total} 筆，跳過 {result.skipped} 筆")

    catalog_path = Path(args.catalog)
    with catalog_path.open(encoding="utf-8") as f:
        catalog = yaml.safe_load(f.read())

    existing_ids: set[str]                    = {lake["id"] for lake in catalog.get("lakes", [])}
    existing_fps: set[tuple[int, str, str]]   = _existing_fingerprints(catalog)
    print(f"[catalog] 現有 {len(existing_ids)} 筆，地域指紋 {len(existing_fps)} 筆")

    new_entries: list[dict] = []
    seen_fps: set[tuple[int, str, str]] = set()
    skipped_id  = 0
    skipped_fp  = 0

    for case in result.cases:
        lake_id = _make_id(case)
        fp      = _region_fingerprint(case)

        if lake_id in existing_ids:
            skipped_id += 1
            continue
        if fp is not None and (fp in existing_fps or fp in seen_fps):
            skipped_fp += 1
            continue

        new_entries.append(_case_to_entry(case, lake_id))
        existing_ids.add(lake_id)
        if fp is not None:
            seen_fps.add(fp)

    print(
        f"[sync] 新增 {len(new_entries)} 筆 | "
        f"跳過(id重複) {skipped_id} 筆 | "
        f"跳過(地域+年份重複) {skipped_fp} 筆"
    )

    if not new_entries:
        print("無新資料，結束。")
        return

    if args.dry_run:
        print("\n--- dry-run: 待新增項目 ---")
        print(yaml.dump(new_entries, allow_unicode=True, sort_keys=False))
        return

    _append_entries(catalog_path, new_entries)
    print(f"[done] 已寫入 {catalog_path}")


if __name__ == "__main__":
    main()
