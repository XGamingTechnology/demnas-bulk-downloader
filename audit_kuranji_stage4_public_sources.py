#!/usr/bin/env python3
"""Audit public pre/post-event data coverage for Kuranji Stage 4.

Purpose
-------
Before claiming terrain/hazard *change* after the 21-27 Nov 2025 Cyclone Senyar
flood, verify whether independent public observations actually cover DAS Batang
Kuranji in useful pre/post windows.

Sources checked
---------------
1) ICESat-2 ATL08 V007 and ATL03 V007 via NASA CMR.
   - Finds granules intersecting the DAS bbox.
   - Separates pre- and post-event observations.
   - Detects repeated ATL08 RGT/region combinations across pre/post windows.
   - ICESat-2 is along-track elevation evidence, NOT a wall-to-wall DEM.

2) Vantor/Maxar Open Data event "Cyclone-Senyar-Indonesia-Nov-2025".
   - Reads the public event footprint GeoJSON.
   - Clips footprints to the actual DAS polygon.
   - Reports dates, platform, GSD, cloud %, catalog IDs, and DAS coverage.
   - This is high-resolution optical imagery, NOT automatically a DEM.

3) NISAR via ASF Search API.
   - Searches BETA-era acquisitions over the DAS.
   - Reports acquisition dates and processing levels.
   - NISAR is SAR change evidence, NOT a direct terrain DEM.

4) Sentinel-1 via ASF Search API as a public fallback/reference SAR source.

Outputs
-------
data/work/kuranji/16_stage4_source_audit/
  stage4_public_source_audit.json
  icesat2_atl08_granules.csv
  icesat2_atl03_granules.csv
  icesat2_repeat_track_pairs.csv
  maxar_senyar_intersections.csv
  maxar_senyar_intersections.geojson
  nisar_results.csv
  nisar_results.geojson
  sentinel1_results.csv
  README_STAGE4_SOURCE_AUDIT.md

This script only audits availability. It does not download large image/HDF5
products and does not alter any Stage-1/2/3 frozen result.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from pyproj import CRS, Transformer
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import transform as shp_transform, unary_union

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data/work/kuranji/16_stage4_source_audit"
OUT.mkdir(parents=True, exist_ok=True)

DAS_UTM = ROOT / "data/work/kuranji/01_prepared/DAS_KURANJI_UTM47S.geojson"
WGS84 = CRS.from_epsg(4326)
UTM47S = CRS.from_epsg(32747)

# Frozen Stage-1 AOI bounds.
BBOX = (100.338509965, -0.936554134, 100.564338684, -0.789776802)
EVENT_START = datetime(2025, 11, 21, tzinfo=timezone.utc)
EVENT_END = datetime(2025, 11, 27, 23, 59, 59, tzinfo=timezone.utc)
PRE_START = datetime(2025, 8, 1, tzinfo=timezone.utc)
PRE_END = datetime(2025, 11, 20, 23, 59, 59, tzinfo=timezone.utc)
POST_START = datetime(2025, 11, 28, tzinfo=timezone.utc)
POST_END = datetime(2026, 1, 31, 23, 59, 59, tzinfo=timezone.utc)

# Current official ICESat-2 V007 collection concept IDs.
CMR_COLLECTIONS = {
    "ATL08": "C3565574177-NSIDC_CPRD",
    "ATL03": "C3326974349-NSIDC_CPRD",
}
CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"

MAXAR_EVENT_URL = (
    "https://raw.githubusercontent.com/opengeos/maxar-open-data/master/"
    "datasets/Cyclone-Senyar-Indonesia-Nov-2025.geojson"
)

ASF_URL = "https://api.daac.asf.alaska.edu/services/search/param"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Kuranji-Stage4-Source-Audit/1.0 research-use",
    "Accept": "application/json,application/geo+json,*/*",
})


def write_csv(path: Path, rows: list[dict[str, Any]]):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen = set()
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def parse_dt(value: str | None):
    if not value:
        return None
    v = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def iso(dt: datetime):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def period(dt: datetime | None):
    if dt is None:
        return "UNKNOWN"
    if PRE_START <= dt <= PRE_END:
        return "PRE"
    if EVENT_START <= dt <= EVENT_END:
        return "EVENT"
    if POST_START <= dt <= POST_END:
        return "POST"
    return "OTHER"


def load_das_wgs84():
    if not DAS_UTM.exists():
        raise FileNotFoundError(DAS_UTM)
    fc = json.loads(DAS_UTM.read_text(encoding="utf-8"))
    geoms = [shape(ft["geometry"]) for ft in fc.get("features", []) if ft.get("geometry")]
    if not geoms:
        raise RuntimeError("DAS geometry missing")
    g = unary_union(geoms)
    tf = Transformer.from_crs(UTM47S, WGS84, always_xy=True).transform
    return shp_transform(tf, g)


def get_json(url: str, params=None, timeout=180):
    r = SESSION.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json(), r.url


def cmr_temporal(begin: datetime, end: datetime):
    return f"{iso(begin)},{iso(end)}"


def cmr_query(product: str):
    params = {
        "collection_concept_id": CMR_COLLECTIONS[product],
        "bounding_box": ",".join(str(x) for x in BBOX),
        "temporal": cmr_temporal(PRE_START, POST_END),
        "page_size": 2000,
    }
    data, url = get_json(CMR_URL, params=params)
    items = data.get("items", []) if isinstance(data, dict) else []
    rows = []
    raw_items = []
    for item in items:
        umm = item.get("umm") or {}
        meta = item.get("meta") or {}
        name = umm.get("GranuleUR") or meta.get("native-id") or ""
        tr = (umm.get("TemporalExtent") or {}).get("RangeDateTime") or {}
        begin = parse_dt(tr.get("BeginningDateTime"))
        end = parse_dt(tr.get("EndingDateTime"))
        rgt = cycle = region = None
        # ICESat-2 naming token after timestamp: RGT(4)+cycle(2)+region(2)
        m = re.search(r"ATL(?:03|08)_\d{14}_(\d{4})(\d{2})(\d{2})_", name)
        if m:
            rgt, cycle, region = m.groups()

        row = {
            "product": product,
            "granule": name,
            "begin_utc": iso(begin) if begin else "",
            "end_utc": iso(end) if end else "",
            "period": period(begin),
            "rgt": rgt or "",
            "cycle": cycle or "",
            "region": region or "",
            "concept_id": meta.get("concept-id", ""),
        }
        rows.append(row)
        raw_items.append(item)
    return rows, raw_items, url, data.get("hits") if isinstance(data, dict) else None


def build_repeat_pairs(atl08_rows):
    groups = defaultdict(lambda: {"PRE": [], "EVENT": [], "POST": []})
    for r in atl08_rows:
        key = (r.get("rgt"), r.get("region"))
        if not all(key):
            continue
        p = r.get("period")
        if p in groups[key]:
            groups[key][p].append(r)

    pairs = []
    for (rgt, region), d in sorted(groups.items()):
        for pre in d["PRE"]:
            for post in d["POST"]:
                pre_dt = parse_dt(pre["begin_utc"])
                post_dt = parse_dt(post["begin_utc"])
                days = (post_dt - pre_dt).total_seconds() / 86400 if pre_dt and post_dt else None
                pairs.append({
                    "rgt": rgt,
                    "region": region,
                    "pre_cycle": pre.get("cycle", ""),
                    "pre_date": pre.get("begin_utc", ""),
                    "pre_granule": pre.get("granule", ""),
                    "post_cycle": post.get("cycle", ""),
                    "post_date": post.get("begin_utc", ""),
                    "post_granule": post.get("granule", ""),
                    "delta_days": round(days, 3) if days is not None else "",
                })
    return pairs


def maxar_audit(das):
    data, url = get_json(MAXAR_EVENT_URL)
    features = data.get("features", [])
    out_features = []
    rows = []
    das_area = das.area

    for i, ft in enumerate(features, 1):
        if not ft.get("geometry"):
            continue
        g = shape(ft["geometry"])
        if g.is_empty or not g.intersects(das):
            continue
        inter = g.intersection(das)
        if inter.is_empty or inter.area <= 0:
            continue
        p = ft.get("properties") or {}
        # Area percentages in geographic CRS are only relative diagnostics. A
        # proper area is computed after reprojecting both to UTM47S.
        tf = Transformer.from_crs(WGS84, UTM47S, always_xy=True).transform
        inter_utm = shp_transform(tf, inter)
        das_utm = shp_transform(tf, das)
        a_km2 = inter_utm.area / 1e6
        rows.append({
            "feature_id": i,
            "datetime": p.get("datetime", ""),
            "period": period(parse_dt(p.get("datetime"))),
            "platform": p.get("platform", ""),
            "catalog_id": p.get("catalog_id", ""),
            "gsd_m": p.get("gsd", ""),
            "cloud_percent": p.get("tile:clouds_percent", ""),
            "intersect_das_km2": round(a_km2, 6),
            "visual_url": p.get("visual", ""),
            "pan_url": p.get("pan_analytic", ""),
            "ms_url": p.get("ms_analytic", ""),
        })
        out_features.append({
            "type": "Feature",
            "geometry": mapping(inter),
            "properties": rows[-1],
        })

    union = unary_union([shape(f["geometry"]) for f in out_features]) if out_features else None
    if union and not union.is_empty:
        tf = Transformer.from_crs(WGS84, UTM47S, always_xy=True).transform
        union_area = shp_transform(tf, union).area / 1e6
        das_area_km2 = shp_transform(tf, das).area / 1e6
        pct = 100 * union_area / das_area_km2 if das_area_km2 else 0
    else:
        union_area = 0.0
        das_area_km2 = shp_transform(
            Transformer.from_crs(WGS84, UTM47S, always_xy=True).transform, das
        ).area / 1e6
        pct = 0.0

    fc = {
        "type": "FeatureCollection",
        "name": "Maxar_Cyclone_Senyar_Kuranji_intersections",
        "features": out_features,
    }
    return rows, fc, {
        "catalog_url": url,
        "event_feature_count_total": len(features),
        "intersecting_feature_count": len(rows),
        "union_coverage_km2": union_area,
        "das_area_km2": das_area_km2,
        "das_coverage_percent": pct,
        "unique_dates": sorted({str(r["datetime"]) for r in rows}),
        "unique_platforms": sorted({str(r["platform"]) for r in rows}),
        "unique_catalog_ids": sorted({str(r["catalog_id"]) for r in rows}),
    }


def normalize_asf_geojson(data):
    # API normally returns one FeatureCollection, but tolerate list responses.
    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        return data
    if isinstance(data, list):
        feats = []
        for obj in data:
            if isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
                feats.extend(obj.get("features", []))
            elif isinstance(obj, dict) and obj.get("type") == "Feature":
                feats.append(obj)
        return {"type": "FeatureCollection", "features": feats}
    return {"type": "FeatureCollection", "features": []}


def asf_query(dataset: str, start: datetime, end: datetime, max_results=1000):
    params = {
        "dataset": dataset,
        "bbox": ",".join(str(x) for x in BBOX),
        "start": iso(start),
        "end": iso(end),
        "maxResults": max_results,
        "output": "geojson",
    }
    data, url = get_json(ASF_URL, params=params)
    fc = normalize_asf_geojson(data)
    rows = []
    for ft in fc.get("features", []):
        p = ft.get("properties") or {}
        acq = (
            p.get("startTime")
            or p.get("start")
            or p.get("sceneDate")
            or p.get("acquisitionDate")
            or ""
        )
        rows.append({
            "dataset": dataset,
            "acquisition_utc": acq,
            "period": period(parse_dt(acq)),
            "scene_name": p.get("sceneName") or p.get("fileID") or p.get("granuleName") or "",
            "processing_level": p.get("processingLevel", ""),
            "flight_direction": p.get("flightDirection", ""),
            "relative_orbit": p.get("pathNumber") or p.get("relativeOrbit") or "",
            "frame": p.get("frameNumber") or p.get("frame") or "",
            "polarization": p.get("polarization", ""),
            "url": p.get("url") or p.get("downloadUrl") or "",
        })
    return rows, fc, url


def summarize_periods(rows):
    out = defaultdict(int)
    for r in rows:
        out[r.get("period", "UNKNOWN")] += 1
    return dict(sorted(out.items()))


def unique_sorted(rows, field):
    return sorted({str(r.get(field, "")) for r in rows if str(r.get(field, "")).strip()})


def main():
    das = load_das_wgs84()
    print("=== KURANJI STAGE 4 PUBLIC SOURCE AUDIT ===")
    print("DAS bbox:", ", ".join(f"{x:.8f}" for x in BBOX))
    print("Pre window :", iso(PRE_START), "to", iso(PRE_END))
    print("Event      :", iso(EVENT_START), "to", iso(EVENT_END))
    print("Post window:", iso(POST_START), "to", iso(POST_END))

    audit: dict[str, Any] = {
        "bbox_wgs84": list(BBOX),
        "event_window": [iso(EVENT_START), iso(EVENT_END)],
        "pre_window": [iso(PRE_START), iso(PRE_END)],
        "post_window": [iso(POST_START), iso(POST_END)],
    }

    # 1. ICESat-2
    print("\n[1/4] NASA CMR — ICESat-2...")
    icesat = {}
    atl_rows = {}
    for prod in ["ATL08", "ATL03"]:
        try:
            rows, raw, query_url, hits = cmr_query(prod)
            atl_rows[prod] = rows
            write_csv(OUT / f"icesat2_{prod.lower()}_granules.csv", rows)
            (OUT / f"icesat2_{prod.lower()}_cmr_raw.json").write_text(
                json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            icesat[prod] = {
                "cmr_hits": hits,
                "returned": len(rows),
                "period_counts": summarize_periods(rows),
                "query_url": query_url,
                "granules": [r["granule"] for r in rows],
            }
            print(f"  {prod}: {len(rows)} granules; periods={summarize_periods(rows)}")
        except Exception as e:
            atl_rows[prod] = []
            icesat[prod] = {"error": repr(e)}
            print(f"  {prod}: ERROR {e}")

    repeat_pairs = build_repeat_pairs(atl_rows.get("ATL08", []))
    write_csv(OUT / "icesat2_repeat_track_pairs.csv", repeat_pairs)
    icesat["ATL08_repeat_pre_post_pairs"] = len(repeat_pairs)
    icesat["repeat_pairs"] = repeat_pairs
    audit["icesat2"] = icesat
    print("  ATL08 repeated RGT/region PRE→POST pairs:", len(repeat_pairs))
    for p in repeat_pairs[:10]:
        print(
            f"    RGT {p['rgt']} region {p['region']}: "
            f"{p['pre_date']} -> {p['post_date']} ({p['delta_days']} d)"
        )

    # 2. Maxar/Vantor Open Data
    print("\n[2/4] Vantor/Maxar Open Data — Cyclone Senyar Indonesia...")
    try:
        maxar_rows, maxar_fc, maxar_summary = maxar_audit(das)
        write_csv(OUT / "maxar_senyar_intersections.csv", maxar_rows)
        (OUT / "maxar_senyar_intersections.geojson").write_text(
            json.dumps(maxar_fc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        audit["maxar_vantor_open_data"] = maxar_summary
        print("  Total event tiles      :", maxar_summary["event_feature_count_total"])
        print("  Tiles intersecting DAS :", maxar_summary["intersecting_feature_count"])
        print(f"  Union coverage in DAS  : {maxar_summary['union_coverage_km2']:.4f} km2")
        print(f"  DAS coverage           : {maxar_summary['das_coverage_percent']:.2f}%")
        print("  Dates                  :", maxar_summary["unique_dates"])
        print("  Platforms              :", maxar_summary["unique_platforms"])
        if maxar_rows:
            clouds = [float(r["cloud_percent"]) for r in maxar_rows if str(r["cloud_percent"]) not in ("", "None")]
            gsd = [float(r["gsd_m"]) for r in maxar_rows if str(r["gsd_m"]) not in ("", "None")]
            if clouds:
                print(f"  Cloud % range          : {min(clouds):.1f}–{max(clouds):.1f}")
            if gsd:
                print(f"  GSD range              : {min(gsd):.2f}–{max(gsd):.2f} m")
    except Exception as e:
        audit["maxar_vantor_open_data"] = {"error": repr(e)}
        print("  ERROR:", e)

    # 3. NISAR BETA-era search
    print("\n[3/4] ASF — NISAR BETA-era coverage...")
    try:
        # Official BETA archive contains selected acquisitions from 17 Oct 2025 to 20 Jan 2026.
        nisar_rows, nisar_fc, nisar_url = asf_query(
            "NISAR",
            datetime(2025, 10, 17, tzinfo=timezone.utc),
            datetime(2026, 1, 20, 23, 59, 59, tzinfo=timezone.utc),
            max_results=2000,
        )
        write_csv(OUT / "nisar_results.csv", nisar_rows)
        (OUT / "nisar_results.geojson").write_text(
            json.dumps(nisar_fc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        nisar_summary = {
            "count": len(nisar_rows),
            "period_counts": summarize_periods(nisar_rows),
            "dates": unique_sorted(nisar_rows, "acquisition_utc"),
            "processing_levels": unique_sorted(nisar_rows, "processing_level"),
            "flight_directions": unique_sorted(nisar_rows, "flight_direction"),
            "relative_orbits": unique_sorted(nisar_rows, "relative_orbit"),
            "query_url": nisar_url,
        }
        audit["nisar"] = nisar_summary
        print("  Results            :", len(nisar_rows))
        print("  Periods            :", nisar_summary["period_counts"])
        print("  Processing levels  :", nisar_summary["processing_levels"])
        print("  Dates:")
        for d in nisar_summary["dates"][:30]:
            print("   ", d)
    except Exception as e:
        audit["nisar"] = {"error": repr(e)}
        print("  ERROR:", e)

    # 4. Sentinel-1 fallback/reference search
    print("\n[4/4] ASF — Sentinel-1 fallback/reference coverage...")
    try:
        s1_rows, s1_fc, s1_url = asf_query(
            "SENTINEL-1", PRE_START, POST_END, max_results=2000
        )
        write_csv(OUT / "sentinel1_results.csv", s1_rows)
        s1_summary = {
            "count": len(s1_rows),
            "period_counts": summarize_periods(s1_rows),
            "dates": unique_sorted(s1_rows, "acquisition_utc"),
            "processing_levels": unique_sorted(s1_rows, "processing_level"),
            "flight_directions": unique_sorted(s1_rows, "flight_direction"),
            "relative_orbits": unique_sorted(s1_rows, "relative_orbit"),
            "query_url": s1_url,
        }
        audit["sentinel1"] = s1_summary
        print("  Results            :", len(s1_rows))
        print("  Periods            :", s1_summary["period_counts"])
        print("  Sample dates:")
        for d in s1_summary["dates"][:20]:
            print("   ", d)
    except Exception as e:
        audit["sentinel1"] = {"error": repr(e)}
        print("  ERROR:", e)

    # Conservative source verdicts.
    atl08_pre = sum(1 for r in atl_rows.get("ATL08", []) if r.get("period") == "PRE")
    atl08_post = sum(1 for r in atl_rows.get("ATL08", []) if r.get("period") == "POST")
    maxar_ok = audit.get("maxar_vantor_open_data", {}).get("intersecting_feature_count", 0) > 0
    nisar_counts = audit.get("nisar", {}).get("period_counts", {})
    nisar_pair = nisar_counts.get("PRE", 0) > 0 and nisar_counts.get("POST", 0) > 0

    verdict = {
        "icesat2_repeat_elevation_candidate": bool(repeat_pairs),
        "icesat2_has_pre_and_post_any": atl08_pre > 0 and atl08_post > 0,
        "maxar_optical_change_candidate": bool(maxar_ok),
        "nisar_pre_post_change_candidate": bool(nisar_pair),
        "full_post_event_dem_found_by_this_audit": False,
        "interpretation": (
            "These public sources may provide along-track elevation or optical/SAR change evidence. "
            "None should be called a wall-to-wall post-event DEM unless an actual DEM/DSM/DTM product is separately verified."
        ),
    }
    audit["verdict"] = verdict

    (OUT / "stage4_public_source_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    readme = "# Stage 4 Public Source Audit — DAS Batang Kuranji\n\n"
    readme += "Event window: 21–27 Nov 2025.\n\n"
    readme += "This folder records availability checks only; no Stage-1/2/3 result is modified.\n\n"
    readme += "## Scientific interpretation\n\n"
    readme += "- ICESat-2: along-track elevation evidence, not a wall-to-wall DEM.\n"
    readme += "- Vantor/Maxar Open Data: high-resolution optical change evidence; ARD imagery is not automatically a DEM.\n"
    readme += "- NISAR/Sentinel-1: SAR surface-change evidence; not direct DEM replacement.\n"
    readme += "- A full ΔDEM analysis still requires comparable pre/post DEM/DSM/DTM products with controlled horizontal and vertical reference.\n"
    (OUT / "README_STAGE4_SOURCE_AUDIT.md").write_text(readme, encoding="utf-8")

    print("\n=== CONSERVATIVE VERDICT ===")
    print("ICESat-2 repeat-track candidate :", verdict["icesat2_repeat_elevation_candidate"])
    print("Maxar optical change candidate  :", verdict["maxar_optical_change_candidate"])
    print("NISAR pre/post change candidate :", verdict["nisar_pre_post_change_candidate"])
    print("Full post-event DEM found       :", verdict["full_post_event_dem_found_by_this_audit"])
    print("\nOutput:", OUT)
    print("NEXT: inspect these exact coverage results before deciding whether Stage 4 can be a true ΔDEM analysis or must remain multimodal change evidence.")


if __name__ == "__main__":
    main()
