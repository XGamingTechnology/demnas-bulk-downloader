#!/usr/bin/env python3
"""Query OpenAltimetry ATL08 per beam for the Kuranji Stage-4 repeat-track pair.

Why this step exists
--------------------
The earlier all-beam JSON response did not expose beam names as dictionary keys,
so the series index must NOT be assumed to map to gt1l/gt1r/... .  This script
queries each beam explicitly using OpenAltimetry's `beamNames` parameter and then
performs positional preflight only.

ATL08 OpenAltimetry `lat_lon_elev_canopy` rows are treated as:
    [latitude, longitude, ground_height_candidate, canopy_height_candidate]
This convention is used by ICESat-2/OpenAltimetry community utilities.  We still
keep the raw JSON and series metadata for auditability.

NO delta-elevation is computed here.  A repeat-track pair must first demonstrate
same-beam spatial comparability.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import requests
from pyproj import Transformer
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data/work/kuranji/23_stage4_icesat2_per_beam"
RAW = OUT / "raw"
CSV = OUT / "csv"
for d in (OUT, RAW, CSV):
    d.mkdir(parents=True, exist_ok=True)

OA_URL = "https://openaltimetry.earthdatacloud.nasa.gov/data/api/icesat2/atl08"
BBOX = (100.338509965, -0.936554134, 100.564338684, -0.789776802)
TRACK_ID = 453
DATES = ["2025-10-14", "2026-01-13"]
BEAMS = ["gt1l", "gt1r", "gt2l", "gt2r", "gt3l", "gt3r"]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Kuranji-Stage4-ICESat2-PerBeam/1.0 research-use",
    "Accept": "application/json,*/*",
})

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32747", always_xy=True)


def finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def query(date: str, beam: str):
    # Current OpenAltimetry clients use `beamNames` for beam-restricted requests.
    params = {
        "date": date,
        "minx": BBOX[0],
        "miny": BBOX[1],
        "maxx": BBOX[2],
        "maxy": BBOX[3],
        "trackId": TRACK_ID,
        "beamNames": beam,
        "outputFormat": "json",
        "client": "portal",
    }
    r = SESSION.get(OA_URL, params=params, timeout=240)
    r.raise_for_status()
    return r.json(), r.url


def scalar_meta(series: Any):
    if not isinstance(series, dict):
        return {"series_type": type(series).__name__}
    meta = {}
    for k, v in series.items():
        if k == "lat_lon_elev_canopy":
            continue
        if v is None or isinstance(v, (str, int, float, bool)):
            meta[k] = v
        elif isinstance(v, list) and len(v) <= 10 and all(
            x is None or isinstance(x, (str, int, float, bool)) for x in v
        ):
            meta[k] = v
        elif isinstance(v, dict):
            small = {
                kk: vv for kk, vv in v.items()
                if vv is None or isinstance(vv, (str, int, float, bool))
            }
            if small:
                meta[k] = small
    return meta


def parse_rows(data: Any, requested_beam: str):
    out = []
    series_meta = []
    series_list = data.get("series", []) if isinstance(data, dict) else []
    if not isinstance(series_list, list):
        return out, series_meta

    for si, series in enumerate(series_list):
        series_meta.append({"series_index": si, "metadata": scalar_meta(series)})
        if not isinstance(series, dict):
            continue
        rows = series.get("lat_lon_elev_canopy", [])
        if not isinstance(rows, list):
            continue
        for ri, row in enumerate(rows):
            if not isinstance(row, list) or len(row) < 4:
                continue
            lat, lon, h, canopy = row[:4]
            if not (finite(lat) and finite(lon) and finite(h)):
                continue
            lat = float(lat)
            lon = float(lon)
            h = float(h)
            canopy = float(canopy) if finite(canopy) else float("nan")
            # Keep only coordinates that are actually inside the requested AOI.
            if not (BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]):
                continue
            x, y = TO_UTM.transform(lon, lat)
            out.append({
                "beam": requested_beam,
                "series_index": si,
                "row_index": ri,
                "lat": lat,
                "lon": lon,
                "x_utm47s": float(x),
                "y_utm47s": float(y),
                "h_ground_candidate": h,
                "canopy_candidate": canopy,
            })
    return out, series_meta


def summarize(rows: list[dict[str, Any]]):
    if not rows:
        return {"count": 0}
    lon = np.array([r["lon"] for r in rows], dtype=float)
    lat = np.array([r["lat"] for r in rows], dtype=float)
    h = np.array([r["h_ground_candidate"] for r in rows], dtype=float)
    canopy = np.array([r["canopy_candidate"] for r in rows], dtype=float)
    cvalid = canopy[np.isfinite(canopy)]
    return {
        "count": len(rows),
        "bbox": [float(lon.min()), float(lat.min()), float(lon.max()), float(lat.max())],
        "h_ground_candidate": {
            "min": float(np.min(h)),
            "median": float(np.median(h)),
            "max": float(np.max(h)),
        },
        "canopy_candidate": {
            "valid_count": int(cvalid.size),
            "min": float(np.min(cvalid)) if cvalid.size else None,
            "median": float(np.median(cvalid)) if cvalid.size else None,
            "max": float(np.max(cvalid)) if cvalid.size else None,
        },
        "series_indices": sorted({int(r["series_index"]) for r in rows}),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]):
    fields = [
        "date", "beam", "series_index", "row_index", "lat", "lon",
        "x_utm47s", "y_utm47s", "h_ground_candidate", "canopy_candidate",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def nearest_stats(pre_rows, post_rows):
    if not pre_rows or not post_rows:
        return {"comparable": False, "reason": "one_or_both_dates_have_no_points"}

    pre_xy = np.array([[r["x_utm47s"], r["y_utm47s"]] for r in pre_rows], dtype=float)
    post_xy = np.array([[r["x_utm47s"], r["y_utm47s"]] for r in post_rows], dtype=float)

    post_tree = cKDTree(post_xy)
    d_pre_to_post, _ = post_tree.query(pre_xy, k=1)
    pre_tree = cKDTree(pre_xy)
    d_post_to_pre, _ = pre_tree.query(post_xy, k=1)

    thresholds = [10, 20, 30, 50, 75, 100, 150, 200, 500]
    return {
        "comparable": True,
        "pre_count": len(pre_rows),
        "post_count": len(post_rows),
        "pre_to_post_nearest_m": {
            "min": float(np.min(d_pre_to_post)),
            "median": float(np.median(d_pre_to_post)),
            "p95": float(np.percentile(d_pre_to_post, 95)),
            "max": float(np.max(d_pre_to_post)),
            "within_pct": {str(t): float(np.mean(d_pre_to_post <= t) * 100.0) for t in thresholds},
        },
        "post_to_pre_nearest_m": {
            "min": float(np.min(d_post_to_pre)),
            "median": float(np.median(d_post_to_pre)),
            "p95": float(np.percentile(d_post_to_pre, 95)),
            "max": float(np.max(d_post_to_pre)),
            "within_pct": {str(t): float(np.mean(d_post_to_pre <= t) * 100.0) for t in thresholds},
        },
    }


def main():
    print("=== KURANJI STAGE 4 ICESAT-2 ATL08 PER-BEAM PREFLIGHT ===")
    results: dict[str, dict[str, Any]] = {}
    points_by_date_beam: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for date in DATES:
        results[date] = {}
        print(f"\n=== {date} ===")
        all_date_rows = []
        for beam in BEAMS:
            print(f"Query {beam} ...", end=" ", flush=True)
            try:
                data, url = query(date, beam)
                raw_path = RAW / f"ATL08_RGT0453_{date}_{beam}.json"
                raw_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

                rows, meta = parse_rows(data, beam)
                for r in rows:
                    r["date"] = date
                points_by_date_beam[(date, beam)] = rows
                all_date_rows.extend(rows)
                summary = summarize(rows)
                results[date][beam] = {
                    "query_url": url,
                    "raw_json": str(raw_path),
                    "response_top_keys": list(data.keys()) if isinstance(data, dict) else [],
                    "series_count": len(data.get("series", [])) if isinstance(data, dict) and isinstance(data.get("series"), list) else None,
                    "series_metadata": meta,
                    "summary": summary,
                }
                print(f"{summary['count']} points", end="")
                if summary["count"]:
                    print(f" bbox={summary['bbox']}")
                else:
                    print()
            except Exception as e:
                points_by_date_beam[(date, beam)] = []
                results[date][beam] = {"error": repr(e)}
                print("ERROR", e)

        write_csv(CSV / f"ATL08_RGT0453_{date}_all_beams.csv", all_date_rows)

    print("\n=== SAME-BEAM CROSS-DATE POSITIONAL PREFLIGHT ===")
    cross = {}
    for beam in BEAMS:
        pre = points_by_date_beam[(DATES[0], beam)]
        post = points_by_date_beam[(DATES[1], beam)]
        st = nearest_stats(pre, post)
        cross[beam] = st
        if not st.get("comparable"):
            print(f"{beam}: no comparable pair ({st.get('reason')})")
            continue
        a = st["pre_to_post_nearest_m"]
        b = st["post_to_pre_nearest_m"]
        print(
            f"{beam}: PRE={len(pre)} POST={len(post)} | "
            f"PRE→POST nearest median={a['median']:.1f} m p95={a['p95']:.1f} m | "
            f"POST→PRE median={b['median']:.1f} m p95={b['p95']:.1f} m | "
            f"PRE within50m={a['within_pct']['50']:.1f}% within100m={a['within_pct']['100']:.1f}%"
        )

    report = {
        "product": "ATL08",
        "track_id": TRACK_ID,
        "dates": DATES,
        "bbox": BBOX,
        "row_semantics_used_for_preflight": ["latitude", "longitude", "ground_height_candidate", "canopy_height_candidate"],
        "per_date_beam": results,
        "same_beam_positional_preflight": cross,
        "delta_elevation_computed": False,
        "next_gate": (
            "Only same-beam pairs with sufficiently small repeat-track offsets should proceed. "
            "Before delta elevation, inspect quality/segment identity availability and choose a defensible matching tolerance."
        ),
    }
    report_path = OUT / "ICESAT2_PER_BEAM_PREFLIGHT.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== DONE ===")
    print("Report:", report_path)
    print("CSV dir:", CSV)
    print("Raw per-beam JSON dir:", RAW)
    print("No delta elevation has been calculated yet.")


if __name__ == "__main__":
    main()
