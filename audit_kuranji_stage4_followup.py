#!/usr/bin/env python3
"""Refined Stage-4 source audit for DAS Batang Kuranji.

This script follows the first public-source audit and addresses three questions:

1) NISAR: the first broad dataset=NISAR query also returned ancillary ECMWF
   products. Here we explicitly query BETA NISAR science products by
   processingLevel (GCOV, GSLC, GUNW, RSLC).

2) Sentinel-1: reduce the broad catalog result to GRD_HD scenes and identify
   closest PRE/EVENT/POST acquisitions sharing orbit direction, relative orbit,
   and polarization.

3) ICESat-2: query OpenAltimetry directly for the repeated ATL08 RGT 0453 dates
   discovered in the first audit (2025-10-14 and 2026-01-13). Raw JSON is saved
   for inspection. ICESat-2 is along-track terrain evidence, not a full DEM.

No Stage-1/2/3 frozen result is modified.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "data/work/kuranji/16_stage4_source_audit"
OUT = BASE / "followup"
OUT.mkdir(parents=True, exist_ok=True)

BBOX = (100.338509965, -0.936554134, 100.564338684, -0.789776802)
EVENT_START = datetime(2025, 11, 21, tzinfo=timezone.utc)
EVENT_END = datetime(2025, 11, 27, 23, 59, 59, tzinfo=timezone.utc)
PRE_START = datetime(2025, 8, 1, tzinfo=timezone.utc)
PRE_END = datetime(2025, 11, 20, 23, 59, 59, tzinfo=timezone.utc)
POST_START = datetime(2025, 11, 28, tzinfo=timezone.utc)
POST_END = datetime(2026, 1, 31, 23, 59, 59, tzinfo=timezone.utc)

ASF_URL = "https://api.daac.asf.alaska.edu/services/search/param"
OA_URL = "https://openaltimetry.earthdatacloud.nasa.gov/data/api/icesat2/atl08"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Kuranji-Stage4-Followup/1.0 research-use",
    "Accept": "application/json,application/geo+json,*/*",
})


def iso(dt: datetime):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def period(dt):
    if dt is None:
        return "UNKNOWN"
    if PRE_START <= dt <= PRE_END:
        return "PRE"
    if EVENT_START <= dt <= EVENT_END:
        return "EVENT"
    if POST_START <= dt <= POST_END:
        return "POST"
    return "OTHER"


def write_csv(path: Path, rows: list[dict[str, Any]]):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields, seen = [], set()
    for r in rows:
        for k in r:
            if k not in seen:
                fields.append(k)
                seen.add(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def normalize_geojson(data):
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


def asf_search(dataset, start, end, processing_level=None, data_maturity=None, max_results=2000):
    params = {
        "dataset": dataset,
        "bbox": ",".join(str(x) for x in BBOX),
        "start": iso(start),
        "end": iso(end),
        "maxResults": max_results,
        "output": "geojson",
    }
    if processing_level:
        params["processingLevel"] = processing_level
    if data_maturity:
        params["dataMaturity"] = data_maturity
    r = SESSION.get(ASF_URL, params=params, timeout=180)
    r.raise_for_status()
    fc = normalize_geojson(r.json())
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
        dt = parse_dt(acq)
        rows.append({
            "dataset": dataset,
            "processing_level": p.get("processingLevel") or processing_level or "",
            "data_maturity": p.get("dataMaturity") or data_maturity or "",
            "acquisition_utc": acq,
            "period": period(dt),
            "scene_name": p.get("sceneName") or p.get("fileID") or p.get("granuleName") or "",
            "flight_direction": p.get("flightDirection", ""),
            "relative_orbit": p.get("pathNumber") or p.get("relativeOrbit") or "",
            "frame": p.get("frameNumber") or p.get("frame") or "",
            "polarization": p.get("polarization") or p.get("mainBandPolarization") or "",
            "url": p.get("url") or p.get("downloadUrl") or "",
        })
    return rows, fc, r.url


def unique_values(rows, field):
    return sorted({str(r.get(field, "")) for r in rows if str(r.get(field, "")).strip()})


def period_counts(rows):
    d = defaultdict(int)
    for r in rows:
        d[r.get("period", "UNKNOWN")] += 1
    return dict(sorted(d.items()))


def find_s1_triplets(rows):
    """Find closest PRE/EVENT/POST acquisitions for same acquisition geometry."""
    groups = defaultdict(list)
    for r in rows:
        key = (
            str(r.get("flight_direction", "")),
            str(r.get("relative_orbit", "")),
            str(r.get("polarization", "")),
        )
        groups[key].append(r)

    triplets = []
    for key, vals in groups.items():
        pre = [r for r in vals if r.get("period") == "PRE" and parse_dt(r.get("acquisition_utc"))]
        evt = [r for r in vals if r.get("period") == "EVENT" and parse_dt(r.get("acquisition_utc"))]
        post = [r for r in vals if r.get("period") == "POST" and parse_dt(r.get("acquisition_utc"))]
        if not evt:
            continue
        pre.sort(key=lambda r: parse_dt(r["acquisition_utc"]), reverse=True)
        evt.sort(key=lambda r: abs((parse_dt(r["acquisition_utc"]) - EVENT_END).total_seconds()))
        post.sort(key=lambda r: parse_dt(r["acquisition_utc"]))
        ev = evt[0]
        pr = pre[0] if pre else None
        po = post[0] if post else None
        if pr or po:
            triplets.append({
                "flight_direction": key[0],
                "relative_orbit": key[1],
                "polarization": key[2],
                "pre_time": pr.get("acquisition_utc", "") if pr else "",
                "pre_scene": pr.get("scene_name", "") if pr else "",
                "event_time": ev.get("acquisition_utc", ""),
                "event_scene": ev.get("scene_name", ""),
                "post_time": po.get("acquisition_utc", "") if po else "",
                "post_scene": po.get("scene_name", "") if po else "",
            })
    triplets.sort(key=lambda r: r["event_time"])
    return triplets


def count_json_nodes(obj):
    """Generic diagnostics for OpenAltimetry response without assuming schema."""
    stats = {"dicts": 0, "lists": 0, "scalars": 0}
    keys = defaultdict(int)

    def walk(x):
        if isinstance(x, dict):
            stats["dicts"] += 1
            for k, v in x.items():
                keys[str(k)] += 1
                walk(v)
        elif isinstance(x, list):
            stats["lists"] += 1
            for v in x:
                walk(v)
        else:
            stats["scalars"] += 1

    walk(obj)
    stats["top_keys"] = list(obj.keys()) if isinstance(obj, dict) else []
    stats["frequent_keys"] = sorted(keys.items(), key=lambda kv: kv[1], reverse=True)[:30]
    return stats


def openaltimetry_atl08(date, track_id=453):
    params = [
        ("date", date),
        ("minx", BBOX[0]),
        ("miny", BBOX[1]),
        ("maxx", BBOX[2]),
        ("maxy", BBOX[3]),
        ("trackId", track_id),
        ("outputFormat", "json"),
        ("client", "portal"),
    ]
    for beam in ["gt1l", "gt1r", "gt2l", "gt2r", "gt3l", "gt3r"]:
        params.append(("beamName", beam))
    r = SESSION.get(OA_URL, params=params, timeout=240)
    r.raise_for_status()
    return r.json(), r.url


def main():
    print("=== KURANJI STAGE 4 REFINED SOURCE AUDIT ===")

    audit = {}

    # 1. Corrected NISAR search.
    print("\n[1/3] NISAR BETA science products (corrected query)...")
    nisar_all = []
    nisar_fc_features = []
    nisar_summary = {}
    for product in ["GCOV", "GSLC", "GUNW", "RSLC"]:
        try:
            rows, fc, url = asf_search(
                "NISAR",
                datetime(2025, 10, 17, tzinfo=timezone.utc),
                datetime(2026, 1, 20, 23, 59, 59, tzinfo=timezone.utc),
                processing_level=product,
                data_maturity="BETA",
                max_results=2000,
            )
            nisar_all.extend(rows)
            nisar_fc_features.extend(fc.get("features", []))
            nisar_summary[product] = {
                "count": len(rows),
                "period_counts": period_counts(rows),
                "dates": unique_values(rows, "acquisition_utc"),
                "query_url": url,
            }
            print(f"  {product:<4}: {len(rows)} results; periods={period_counts(rows)}")
            for d in unique_values(rows, "acquisition_utc")[:12]:
                print("       ", d)
        except Exception as e:
            nisar_summary[product] = {"error": repr(e)}
            print(f"  {product:<4}: ERROR {e}")

    write_csv(OUT / "nisar_beta_science_products.csv", nisar_all)
    (OUT / "nisar_beta_science_products.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": nisar_fc_features}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    audit["nisar"] = nisar_summary

    # 2. Sentinel-1 GRD_HD and geometry-matched pairs/triplets.
    print("\n[2/3] Sentinel-1 GRD_HD — closest geometry-matched PRE/EVENT/POST...")
    try:
        s1_rows, s1_fc, s1_url = asf_search(
            "SENTINEL-1",
            PRE_START,
            POST_END,
            processing_level="GRD_HD",
            max_results=2000,
        )
        write_csv(OUT / "sentinel1_grd_hd.csv", s1_rows)
        triplets = find_s1_triplets(s1_rows)
        write_csv(OUT / "sentinel1_candidate_triplets.csv", triplets)
        audit["sentinel1"] = {
            "count": len(s1_rows),
            "period_counts": period_counts(s1_rows),
            "candidate_triplets": triplets,
            "query_url": s1_url,
        }
        print("  GRD_HD results:", len(s1_rows), "periods=", period_counts(s1_rows))
        print("  Candidate geometry-matched groups:", len(triplets))
        for i, t in enumerate(triplets[:12], 1):
            print(
                f"  {i:>2}. {t['flight_direction']} orbit={t['relative_orbit']} pol={t['polarization']}\n"
                f"      PRE   {t['pre_time']}\n"
                f"      EVENT {t['event_time']}\n"
                f"      POST  {t['post_time']}"
            )
    except Exception as e:
        audit["sentinel1"] = {"error": repr(e)}
        print("  ERROR:", e)

    # 3. OpenAltimetry direct ATL08 test for the repeated RGT.
    print("\n[3/3] OpenAltimetry ATL08 RGT 0453 direct subset...")
    oa_summary = {}
    for date in ["2025-10-14", "2026-01-13"]:
        try:
            data, url = openaltimetry_atl08(date, track_id=453)
            out_json = OUT / f"openaltimetry_ATL08_RGT0453_{date}.json"
            out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            diag = count_json_nodes(data)
            diag["query_url"] = url
            diag["response_file"] = str(out_json)
            oa_summary[date] = diag
            print(f"  {date}: SUCCESS")
            print("      top keys:", diag["top_keys"])
            print("      frequent keys:", diag["frequent_keys"][:10])
            print("      JSON nodes:", {k: diag[k] for k in ["dicts", "lists", "scalars"]})
        except Exception as e:
            oa_summary[date] = {"error": repr(e)}
            print(f"  {date}: ERROR {e}")
    audit["openaltimetry_atl08_rgt0453"] = oa_summary

    # Conservative interpretation.
    nisar_rows_valid = sum(
        x.get("count", 0)
        for x in nisar_summary.values()
        if isinstance(x, dict) and isinstance(x.get("count", 0), int)
    )
    s1_candidates = len(audit.get("sentinel1", {}).get("candidate_triplets", []))
    oa_ok = all("error" not in oa_summary.get(d, {}) for d in ["2025-10-14", "2026-01-13"])

    verdict = {
        "nisar_beta_science_product_hits": nisar_rows_valid,
        "sentinel1_geometry_matched_event_groups": s1_candidates,
        "openaltimetry_repeat_track_both_dates_retrievable": oa_ok,
        "true_wall_to_wall_post_event_dem_available": False,
        "recommended_stage4_design": (
            "Use ICESat-2 repeat-track elevation as along-track evidence plus Sentinel-1 event change mapping; "
            "use NISAR only if corrected science-product search returns suitable PRE/POST acquisitions. "
            "Do not call this a full DeltaDEM unless a comparable post-event DEM/DSM/DTM is obtained."
        ),
    }
    audit["verdict"] = verdict
    (OUT / "stage4_followup_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== REFINED VERDICT ===")
    print("NISAR BETA science-product hits     :", verdict["nisar_beta_science_product_hits"])
    print("Sentinel-1 matched event groups     :", verdict["sentinel1_geometry_matched_event_groups"])
    print("ICESat-2 repeat dates retrievable   :", verdict["openaltimetry_repeat_track_both_dates_retrievable"])
    print("Wall-to-wall post-event DEM         :", verdict["true_wall_to_wall_post_event_dem_available"])
    print("Output:", OUT)


if __name__ == "__main__":
    main()
