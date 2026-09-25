#!/usr/bin/env python3
"""Prepare exact Sentinel-1 PRE/EVENT/POST manifest for Kuranji Stage 4.

This is a pre-download/preprocessing guardrail. It:
- queries Sentinel-1 GRD_HD over the frozen Stage-4 window;
- intersects each scene footprint with the ACTUAL DAS polygon (not bbox only);
- reports scene coverage percentage of DAS;
- finds matching PRE/EVENT/POST acquisition groups by direction, relative orbit,
  polarization and, where available, frame;
- ranks groups by DAS coverage and temporal proximity to the 21-27 Nov event;
- records exact scene names, platform, acquisition time, URL and remote size when
  exposed by HTTP headers;
- checks local availability of SNAP/gpt, Java, GDAL and Python raster tooling.

No large scene is downloaded by this script.
"""

from __future__ import annotations

import csv
import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from pyproj import CRS, Transformer
from shapely.geometry import shape
from shapely.ops import transform as shp_transform, unary_union

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data/work/kuranji/17_stage4_sentinel1_prepare"
OUT.mkdir(parents=True, exist_ok=True)

DAS_UTM = ROOT / "data/work/kuranji/01_prepared/DAS_KURANJI_UTM47S.geojson"
ASF_URL = "https://api.daac.asf.alaska.edu/services/search/param"

WGS84 = CRS.from_epsg(4326)
UTM47S = CRS.from_epsg(32747)
BBOX = (100.338509965, -0.936554134, 100.564338684, -0.789776802)

EVENT_START = datetime(2025, 11, 21, tzinfo=timezone.utc)
EVENT_END = datetime(2025, 11, 27, 23, 59, 59, tzinfo=timezone.utc)
PRE_START = datetime(2025, 10, 15, tzinfo=timezone.utc)
PRE_END = datetime(2025, 11, 20, 23, 59, 59, tzinfo=timezone.utc)
POST_START = datetime(2025, 11, 28, tzinfo=timezone.utc)
POST_END = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Kuranji-Stage4-Sentinel1-Prepare/1.0 research-use",
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


def load_das():
    fc = json.loads(DAS_UTM.read_text(encoding="utf-8"))
    geoms = [shape(f["geometry"]) for f in fc.get("features", []) if f.get("geometry")]
    if not geoms:
        raise RuntimeError("DAS geometry missing")
    das_utm = unary_union(geoms)
    to_wgs = Transformer.from_crs(UTM47S, WGS84, always_xy=True).transform
    return das_utm, shp_transform(to_wgs, das_utm)


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


def asf_search():
    params = {
        "dataset": "SENTINEL-1",
        "processingLevel": "GRD_HD",
        "bbox": ",".join(str(x) for x in BBOX),
        "start": iso(PRE_START),
        "end": iso(POST_END),
        "maxResults": 2000,
        "output": "geojson",
    }
    r = SESSION.get(ASF_URL, params=params, timeout=180)
    r.raise_for_status()
    return normalize_geojson(r.json()), r.url


def prop(p, *names):
    for n in names:
        v = p.get(n)
        if v not in (None, "", []):
            return v
    return ""


def write_csv(path: Path, rows: list[dict[str, Any]]):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields, seen = [], set()
    for row in rows:
        for k in row:
            if k not in seen:
                fields.append(k)
                seen.add(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def remote_head(url):
    if not url:
        return {"http_status": "", "content_length_bytes": "", "content_type": "", "final_url": ""}
    try:
        r = SESSION.head(url, allow_redirects=True, timeout=45)
        # Some servers reject HEAD; use a minimal ranged GET only if needed.
        if r.status_code >= 400:
            r = SESSION.get(url, headers={"Range": "bytes=0-0"}, stream=True, allow_redirects=True, timeout=45)
        length = r.headers.get("content-length", "")
        # Range response may expose total in Content-Range: bytes 0-0/TOTAL
        cr = r.headers.get("content-range", "")
        if cr and "/" in cr:
            total = cr.rsplit("/", 1)[-1]
            if total.isdigit():
                length = total
        return {
            "http_status": r.status_code,
            "content_length_bytes": length,
            "content_type": r.headers.get("content-type", ""),
            "final_url": r.url,
        }
    except Exception as e:
        return {"http_status": f"ERROR:{e}", "content_length_bytes": "", "content_type": "", "final_url": ""}


def scene_rows(fc, das_utm):
    to_utm = Transformer.from_crs(WGS84, UTM47S, always_xy=True).transform
    das_area = das_utm.area
    rows = []
    geo_features = []

    for ft in fc.get("features", []):
        if not ft.get("geometry"):
            continue
        p = ft.get("properties") or {}
        g_wgs = shape(ft["geometry"])
        if g_wgs.is_empty:
            continue
        g_utm = shp_transform(to_utm, g_wgs)
        inter = g_utm.intersection(das_utm)
        if inter.is_empty or inter.area <= 0:
            continue

        acq = prop(p, "startTime", "start", "sceneDate", "acquisitionDate")
        dt = parse_dt(acq)
        coverage = 100.0 * inter.area / das_area if das_area else 0.0
        url = prop(p, "url", "downloadUrl")
        row = {
            "scene_name": prop(p, "sceneName", "fileID", "granuleName"),
            "platform": prop(p, "platform", "platformName", "satellite"),
            "acquisition_utc": acq,
            "period": period(dt),
            "flight_direction": prop(p, "flightDirection"),
            "relative_orbit": prop(p, "pathNumber", "relativeOrbit"),
            "frame": prop(p, "frameNumber", "frame"),
            "polarization": prop(p, "polarization", "mainBandPolarization"),
            "processing_level": prop(p, "processingLevel"),
            "beam_mode": prop(p, "beamModeType", "beamMode"),
            "das_coverage_pct": coverage,
            "intersect_das_km2": inter.area / 1e6,
            "download_url": url,
        }
        rows.append(row)
        geo_features.append({
            "type": "Feature",
            "geometry": ft["geometry"],
            "properties": row,
        })
    return rows, {"type": "FeatureCollection", "features": geo_features}


def temporal_distance_hours(dt, target):
    return abs((dt - target).total_seconds()) / 3600.0 if dt else 1e9


def find_groups(rows):
    """Rank PRE/EVENT/POST triplets conservatively.

    First grouping includes frame if populated. A second fallback without frame is
    also considered because ASF frame metadata can vary across adjacent footprints.
    """
    candidates = []

    for use_frame in [True, False]:
        groups = defaultdict(list)
        for r in rows:
            key = [
                str(r.get("flight_direction", "")),
                str(r.get("relative_orbit", "")),
                str(r.get("polarization", "")),
            ]
            if use_frame:
                key.append(str(r.get("frame", "")))
            groups[tuple(key)].append(r)

        for key, vals in groups.items():
            pre = [r for r in vals if r["period"] == "PRE" and parse_dt(r["acquisition_utc"])]
            evt = [r for r in vals if r["period"] == "EVENT" and parse_dt(r["acquisition_utc"])]
            post = [r for r in vals if r["period"] == "POST" and parse_dt(r["acquisition_utc"])]
            if not pre or not evt or not post:
                continue

            # Prefer high DAS coverage, then nearest event dates.
            pre.sort(key=lambda r: (-float(r["das_coverage_pct"]), temporal_distance_hours(parse_dt(r["acquisition_utc"]), EVENT_START)))
            evt.sort(key=lambda r: (-float(r["das_coverage_pct"]), temporal_distance_hours(parse_dt(r["acquisition_utc"]), EVENT_END)))
            post.sort(key=lambda r: (-float(r["das_coverage_pct"]), temporal_distance_hours(parse_dt(r["acquisition_utc"]), POST_START)))

            pr, ev, po = pre[0], evt[0], post[0]
            min_cov = min(float(pr["das_coverage_pct"]), float(ev["das_coverage_pct"]), float(po["das_coverage_pct"]))
            mean_cov = sum(float(x["das_coverage_pct"]) for x in [pr, ev, po]) / 3.0
            same_platform = len({str(x.get("platform", "")) for x in [pr, ev, po] if str(x.get("platform", ""))}) <= 1

            score = (
                min_cov * 1000
                + mean_cov * 10
                - temporal_distance_hours(parse_dt(pr["acquisition_utc"]), EVENT_START)
                - temporal_distance_hours(parse_dt(ev["acquisition_utc"]), EVENT_END)
                - temporal_distance_hours(parse_dt(po["acquisition_utc"]), POST_START)
                + (25 if same_platform else 0)
                + (10 if use_frame else 0)
            )
            candidates.append({
                "grouping": "direction+orbit+pol+frame" if use_frame else "direction+orbit+pol",
                "flight_direction": pr.get("flight_direction", ""),
                "relative_orbit": pr.get("relative_orbit", ""),
                "polarization": pr.get("polarization", ""),
                "frame": pr.get("frame", "") if use_frame else "",
                "same_platform_all_three": same_platform,
                "min_das_coverage_pct": min_cov,
                "mean_das_coverage_pct": mean_cov,
                "score": score,
                "pre_scene": pr["scene_name"],
                "pre_platform": pr["platform"],
                "pre_time": pr["acquisition_utc"],
                "pre_coverage_pct": pr["das_coverage_pct"],
                "pre_url": pr["download_url"],
                "event_scene": ev["scene_name"],
                "event_platform": ev["platform"],
                "event_time": ev["acquisition_utc"],
                "event_coverage_pct": ev["das_coverage_pct"],
                "event_url": ev["download_url"],
                "post_scene": po["scene_name"],
                "post_platform": po["platform"],
                "post_time": po["acquisition_utc"],
                "post_coverage_pct": po["das_coverage_pct"],
                "post_url": po["download_url"],
            })

    # Deduplicate identical 3-scene combinations, retaining stricter grouping.
    best_by_triplet = {}
    for c in sorted(candidates, key=lambda x: x["score"], reverse=True):
        k = (c["pre_scene"], c["event_scene"], c["post_scene"])
        if k not in best_by_triplet:
            best_by_triplet[k] = c
    return sorted(best_by_triplet.values(), key=lambda x: x["score"], reverse=True)


def command_exists(name):
    p = shutil.which(name)
    return p or ""


def processor_preflight():
    return {
        "snap_gpt": command_exists("gpt"),
        "snap_gui": command_exists("snap"),
        "java": command_exists("java"),
        "gdalinfo": command_exists("gdalinfo"),
        "gdalwarp": command_exists("gdalwarp"),
        "python": command_exists("python"),
    }


def main():
    print("=== KURANJI STAGE 4 SENTINEL-1 PREPARATION ===")
    das_utm, _ = load_das()
    fc, query_url = asf_search()
    rows, scene_fc = scene_rows(fc, das_utm)

    print("ASF GRD_HD scenes intersecting actual DAS:", len(rows))
    print("Period counts:")
    for p in ["PRE", "EVENT", "POST", "OTHER", "UNKNOWN"]:
        n = sum(1 for r in rows if r["period"] == p)
        if n:
            print(f"  {p:<7}: {n}")

    write_csv(OUT / "sentinel1_grd_hd_actual_das.csv", rows)
    (OUT / "sentinel1_grd_hd_actual_das.geojson").write_text(
        json.dumps(scene_fc, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    groups = find_groups(rows)
    write_csv(OUT / "candidate_triplets_ranked.csv", groups)

    if not groups:
        raise RuntimeError("No PRE/EVENT/POST triplet found after actual-DAS filtering")

    print("\nRanked candidate triplets:")
    for i, g in enumerate(groups[:5], 1):
        print(
            f"#{i} {g['flight_direction']} orbit={g['relative_orbit']} pol={g['polarization']} "
            f"mincov={g['min_das_coverage_pct']:.2f}% same_platform={g['same_platform_all_three']}"
        )
        print(f"   PRE   {g['pre_time']}  {g['pre_platform']}  {g['pre_scene']}")
        print(f"   EVENT {g['event_time']}  {g['event_platform']}  {g['event_scene']}")
        print(f"   POST  {g['post_time']}  {g['post_platform']}  {g['post_scene']}")

    best = groups[0]
    manifest_rows = []
    for role in ["pre", "event", "post"]:
        url = best[f"{role}_url"]
        h = remote_head(url)
        size = h.get("content_length_bytes", "")
        size_gb = ""
        try:
            size_gb = round(int(size) / (1024**3), 3)
        except Exception:
            pass
        manifest_rows.append({
            "role": role.upper(),
            "scene_name": best[f"{role}_scene"],
            "platform": best[f"{role}_platform"],
            "acquisition_utc": best[f"{role}_time"],
            "flight_direction": best["flight_direction"],
            "relative_orbit": best["relative_orbit"],
            "polarization": best["polarization"],
            "coverage_pct": best[f"{role}_coverage_pct"],
            "download_url": url,
            "http_status": h.get("http_status", ""),
            "remote_size_bytes": size,
            "remote_size_gib": size_gb,
            "final_url": h.get("final_url", ""),
        })

    write_csv(OUT / "SELECTED_SENTINEL1_TRIPLET.csv", manifest_rows)
    (OUT / "SELECTED_SENTINEL1_TRIPLET.json").write_text(
        json.dumps({
            "selection": best,
            "files": manifest_rows,
            "selection_rule": "actual DAS intersection + matching acquisition geometry + high coverage + temporal proximity; no model tuning",
            "query_url": query_url,
        }, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    preflight = processor_preflight()
    (OUT / "processing_preflight.json").write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== SELECTED TRIPLET ===")
    for r in manifest_rows:
        print(f"{r['role']}: {r['scene_name']}")
        print(f"  platform : {r['platform']}")
        print(f"  time     : {r['acquisition_utc']}")
        print(f"  coverage : {float(r['coverage_pct']):.2f}% DAS")
        print(f"  HTTP     : {r['http_status']}")
        print(f"  size GiB : {r['remote_size_gib'] or 'unknown'}")
        print(f"  URL      : {r['download_url']}")

    print("\n=== PROCESSING PREFLIGHT ===")
    for k, v in preflight.items():
        print(f"{k:<10}: {v or 'NOT FOUND'}")

    print("\nOutput:", OUT)
    print("NEXT: decide download/preprocessing route from the exact scene manifest and available processor stack.")


if __name__ == "__main__":
    main()
