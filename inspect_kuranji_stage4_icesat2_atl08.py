#!/usr/bin/env python3
"""Inspect OpenAltimetry ATL08 repeat-track JSON for Kuranji Stage 4.

This is a schema/QC discovery step before any elevation-difference matching.
It intentionally avoids assuming an undocumented OpenAltimetry JSON layout.

Inputs
------
data/work/kuranji/16_stage4_source_audit/followup/
  openaltimetry_ATL08_RGT0453_2025-10-14.json
  openaltimetry_ATL08_RGT0453_2026-01-13.json

Outputs
-------
data/work/kuranji/22_stage4_icesat2_schema/
  ICESAT2_SCHEMA_REPORT.json
  ATL08_2025-10-14_candidate_points.csv
  ATL08_2026-01-13_candidate_points.csv

The candidate CSVs are diagnostic only. Elevation change must not be computed
until beam identity, coordinate semantics, terrain-vs-canopy field meaning,
quality fields, and positional comparability are confirmed from the actual
response structure.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "data/work/kuranji/16_stage4_source_audit/followup"
OUT = ROOT / "data/work/kuranji/22_stage4_icesat2_schema"
OUT.mkdir(parents=True, exist_ok=True)

FILES = {
    "2025-10-14": SRC / "openaltimetry_ATL08_RGT0453_2025-10-14.json",
    "2026-01-13": SRC / "openaltimetry_ATL08_RGT0453_2026-01-13.json",
}

BEAM_RE = re.compile(r"gt[123][lr]", re.IGNORECASE)
LAT_KEYS = {"lat", "latitude", "segment_lat", "lat_ph"}
LON_KEYS = {"lon", "lng", "longitude", "segment_lon", "lon_ph"}
ELEV_KEYS = {
    "elev", "elevation", "height", "h", "h_te_best_fit", "terrain", "terrain_h",
    "terrain_height", "h_mean_canopy_abs", "h_canopy_abs", "h_te_interp",
}


def finite_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def path_str(path: tuple[Any, ...]) -> str:
    return "/".join(str(x) for x in path)


def beam_from_path(path: tuple[Any, ...]) -> str:
    for token in reversed(path):
        m = BEAM_RE.search(str(token))
        if m:
            return m.group(0).lower()
    return "UNKNOWN"


def summarize_tree(obj: Any):
    types = Counter()
    keys = Counter()
    beam_paths = set()
    max_depth = 0
    list_lengths = []

    def walk(x: Any, path=()):
        nonlocal max_depth
        max_depth = max(max_depth, len(path))
        if isinstance(x, dict):
            types["dict"] += 1
            for k, v in x.items():
                keys[str(k)] += 1
                if BEAM_RE.search(str(k)):
                    beam_paths.add(path_str(path + (k,)))
                walk(v, path + (k,))
        elif isinstance(x, list):
            types["list"] += 1
            list_lengths.append(len(x))
            for i, v in enumerate(x):
                walk(v, path + (i,))
        else:
            types[type(x).__name__] += 1

    walk(obj)
    return {
        "types": dict(types),
        "max_depth": max_depth,
        "top_keys": list(obj.keys()) if isinstance(obj, dict) else [],
        "frequent_keys": keys.most_common(80),
        "beam_paths": sorted(beam_paths),
        "list_length_summary": {
            "count": len(list_lengths),
            "min": min(list_lengths) if list_lengths else None,
            "median": median(list_lengths) if list_lengths else None,
            "max": max(list_lengths) if list_lengths else None,
        },
    }


def infer_triplet_indices(rows: list[list[Any]]):
    """Infer latitude, longitude, elevation columns from numeric rows by value ranges.

    This is diagnostic only. Kuranji coordinates are roughly lon 100.3-100.6,
    lat -1.0 to -0.7; elevation is expected to be a plausible terrestrial height.
    """
    if not rows:
        return None
    ncol = min(len(r) for r in rows)
    if ncol < 3:
        return None

    samples = rows[: min(500, len(rows))]
    cols = [[] for _ in range(ncol)]
    for r in samples:
        for j in range(ncol):
            if finite_num(r[j]):
                cols[j].append(float(r[j]))

    def frac(vals, predicate):
        if not vals:
            return 0.0
        return sum(1 for v in vals if predicate(v)) / len(vals)

    lat_scores = [frac(v, lambda x: -2.0 <= x <= 1.0) for v in cols]
    lon_scores = [frac(v, lambda x: 99.0 <= x <= 102.0) for v in cols]
    elev_scores = [frac(v, lambda x: -200.0 <= x <= 5000.0) for v in cols]

    lat_i = max(range(ncol), key=lambda i: lat_scores[i])
    lon_i = max(range(ncol), key=lambda i: lon_scores[i])
    elev_candidates = [i for i in range(ncol) if i not in {lat_i, lon_i}]
    if not elev_candidates:
        return None
    elev_i = max(elev_candidates, key=lambda i: elev_scores[i])

    if lat_scores[lat_i] < 0.8 or lon_scores[lon_i] < 0.8 or elev_scores[elev_i] < 0.5:
        return None
    return {
        "lat_index": lat_i,
        "lon_index": lon_i,
        "elevation_index": elev_i,
        "lat_score": lat_scores[lat_i],
        "lon_score": lon_scores[lon_i],
        "elevation_score": elev_scores[elev_i],
    }


def discover_candidate_arrays(obj: Any):
    candidates = []

    def walk(x: Any, path=()):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, path + (k,))
            return
        if not isinstance(x, list):
            return

        # Candidate A: list of dictionaries containing coordinate/elevation-like keys.
        dict_rows = [r for r in x if isinstance(r, dict)]
        if len(dict_rows) >= 2:
            key_union = set().union(*(set(r.keys()) for r in dict_rows[:100]))
            lower_map = {str(k).lower(): k for k in key_union}
            lat_key = next((lower_map[k] for k in LAT_KEYS if k in lower_map), None)
            lon_key = next((lower_map[k] for k in LON_KEYS if k in lower_map), None)
            elev_key = next((lower_map[k] for k in ELEV_KEYS if k in lower_map), None)
            if lat_key is not None and lon_key is not None and elev_key is not None:
                candidates.append({
                    "kind": "dict_rows",
                    "path": path_str(path),
                    "beam": beam_from_path(path),
                    "count": len(dict_rows),
                    "lat_key": str(lat_key),
                    "lon_key": str(lon_key),
                    "elevation_key": str(elev_key),
                    "sample": dict_rows[:3],
                })

        # Candidate B: list of numeric rows, e.g. lat/lon/elevation[/canopy].
        num_rows = [r for r in x if isinstance(r, list) and len(r) >= 3 and all(finite_num(v) for v in r[:3])]
        if len(num_rows) >= 2:
            inferred = infer_triplet_indices(num_rows)
            if inferred:
                candidates.append({
                    "kind": "numeric_rows",
                    "path": path_str(path),
                    "beam": beam_from_path(path),
                    "count": len(num_rows),
                    "row_length_min": min(len(r) for r in num_rows),
                    "row_length_max": max(len(r) for r in num_rows),
                    "inferred": inferred,
                    "sample": num_rows[:3],
                })

        for i, v in enumerate(x):
            walk(v, path + (i,))

    walk(obj)

    # De-duplicate nested detections by (kind,path).
    seen = set()
    out = []
    for c in candidates:
        key = (c["kind"], c["path"])
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def extract_diagnostic_points(obj: Any, candidates: list[dict[str, Any]]):
    """Re-walk object and extract candidate coordinate/elevation rows.

    Elevation remains generically labelled elevation_candidate until the actual
    OpenAltimetry field semantics are confirmed from the response schema.
    """
    target_paths = {c["path"]: c for c in candidates}
    points = []

    def walk(x: Any, path=()):
        p = path_str(path)
        if p in target_paths and isinstance(x, list):
            c = target_paths[p]
            if c["kind"] == "dict_rows":
                for idx, r in enumerate(x):
                    if not isinstance(r, dict):
                        continue
                    try:
                        lat = float(r[c["lat_key"]])
                        lon = float(r[c["lon_key"]])
                        elev = float(r[c["elevation_key"]])
                    except Exception:
                        continue
                    if all(math.isfinite(v) for v in [lat, lon, elev]):
                        points.append({
                            "candidate_path": p,
                            "beam": c["beam"],
                            "row_index": idx,
                            "lat": lat,
                            "lon": lon,
                            "elevation_candidate": elev,
                            "source_kind": c["kind"],
                        })
            elif c["kind"] == "numeric_rows":
                inf = c["inferred"]
                for idx, r in enumerate(x):
                    if not isinstance(r, list):
                        continue
                    try:
                        lat = float(r[inf["lat_index"]])
                        lon = float(r[inf["lon_index"]])
                        elev = float(r[inf["elevation_index"]])
                    except Exception:
                        continue
                    if all(math.isfinite(v) for v in [lat, lon, elev]):
                        points.append({
                            "candidate_path": p,
                            "beam": c["beam"],
                            "row_index": idx,
                            "lat": lat,
                            "lon": lon,
                            "elevation_candidate": elev,
                            "source_kind": c["kind"],
                        })

        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, path + (k,))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, path + (i,))

    walk(obj)
    return points


def summarize_points(points: list[dict[str, Any]]):
    if not points:
        return {"count": 0}
    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    elev = [p["elevation_candidate"] for p in points]
    beams = Counter(p["beam"] for p in points)
    return {
        "count": len(points),
        "beams": dict(sorted(beams.items())),
        "bbox": [min(lons), min(lats), max(lons), max(lats)],
        "elevation_candidate": {
            "min": min(elev),
            "median": median(elev),
            "max": max(elev),
        },
        "candidate_paths": sorted(set(p["candidate_path"] for p in points)),
    }


def write_points_csv(path: Path, points: list[dict[str, Any]]):
    fields = ["candidate_path", "beam", "row_index", "lat", "lon", "elevation_candidate", "source_kind"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(points)


def main():
    print("=== KURANJI STAGE 4 ICESAT-2 ATL08 SCHEMA INSPECTION ===")
    report = {
        "rgt": 453,
        "purpose": "schema/QC discovery before repeat-track elevation matching",
        "dates": {},
    }

    for date, path in FILES.items():
        print(f"\n[{date}] {path}")
        if not path.exists():
            raise FileNotFoundError(path)
        print(f"  file size: {path.stat().st_size / 1024:.1f} KiB")
        data = json.loads(path.read_text(encoding="utf-8"))

        tree = summarize_tree(data)
        candidates = discover_candidate_arrays(data)
        points = extract_diagnostic_points(data, candidates)
        point_summary = summarize_points(points)

        out_csv = OUT / f"ATL08_{date}_candidate_points.csv"
        write_points_csv(out_csv, points)

        report["dates"][date] = {
            "source_file": str(path),
            "file_size_bytes": path.stat().st_size,
            "tree": tree,
            "candidate_arrays": candidates,
            "diagnostic_points": point_summary,
            "candidate_points_csv": str(out_csv),
        }

        print("  top keys:", tree["top_keys"])
        print("  beam paths found:", len(tree["beam_paths"]))
        for b in tree["beam_paths"][:18]:
            print("    ", b)
        print("  candidate arrays:", len(candidates))
        for c in candidates[:18]:
            print(
                f"    {c['kind']:<12} beam={c['beam']:<7} count={c['count']:<6} path={c['path']}"
            )
        print("  diagnostic points:", point_summary.get("count", 0))
        print("  points by beam:", point_summary.get("beams", {}))
        print("  bbox:", point_summary.get("bbox"))
        print("  elevation candidate summary:", point_summary.get("elevation_candidate"))

    # Compare beam/path availability only; no elevation subtraction yet.
    pre = report["dates"]["2025-10-14"]["diagnostic_points"]
    post = report["dates"]["2026-01-13"]["diagnostic_points"]
    pre_beams = set(pre.get("beams", {}))
    post_beams = set(post.get("beams", {}))
    report["cross_date_preflight"] = {
        "common_beams": sorted(pre_beams & post_beams),
        "pre_only_beams": sorted(pre_beams - post_beams),
        "post_only_beams": sorted(post_beams - pre_beams),
        "safe_to_subtract_elevation_now": False,
        "reason": (
            "Candidate extraction is diagnostic. Confirm actual field semantics, beam identity, "
            "quality fields, and along-track positional correspondence before computing delta elevation."
        ),
    }

    out_report = OUT / "ICESAT2_SCHEMA_REPORT.json"
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== CROSS-DATE PREFLIGHT ===")
    print("common beams:", report["cross_date_preflight"]["common_beams"])
    print("pre-only beams:", report["cross_date_preflight"]["pre_only_beams"])
    print("post-only beams:", report["cross_date_preflight"]["post_only_beams"])
    print("safe to subtract elevation now: NO")
    print("\nReport:", out_report)
    print("NEXT: inspect the actual beam/candidate paths and field semantics from this report, then build strict same-beam repeat-track matching.")


if __name__ == "__main__":
    main()
