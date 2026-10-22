#!/usr/bin/env python3
"""Analyze BIG bathymetry point/contour GeoJSON and export compact CSV summaries."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path


def load_fc(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise RuntimeError(f"{path} bukan GeoJSON FeatureCollection.")
    return data


def point_rows(fc: dict) -> list[dict]:
    rows = []
    for feature in fc.get("features", []):
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        coords = geom.get("coordinates") if geom.get("type") == "Point" else None
        lon = coords[0] if isinstance(coords, list) and len(coords) >= 2 else None
        lat = coords[1] if isinstance(coords, list) and len(coords) >= 2 else None
        rows.append({
            "objectid": props.get("OBJECTID"),
            "lon": lon,
            "lat": lat,
            "depth_m": props.get("NIKDLM"),
            "vertical_datum_code": props.get("DTMVER"),
            "exposition_code": props.get("EXPSOU"),
            "quality_code": props.get("QUASOU"),
            "information_code": props.get("INFORM"),
            "source_indication": props.get("ISBDTA"),
            "recording_indication": props.get("IRKDTA"),
            "recording_date_ms": props.get("TRDATA"),
            "publication_date_ms": props.get("PUBDTA"),
            "scale_max": props.get("SKLMAK"),
            "scale_min": props.get("SKLMIN"),
            "remark": props.get("REMARK"),
        })
    return rows


def contour_rows(fc: dict) -> list[dict]:
    rows = []
    for feature in fc.get("features", []):
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        rows.append({
            "objectid": props.get("OBJECTID"),
            "depth_m": props.get("NKKDLM"),
            "vertical_datum_code": props.get("DTMVER"),
            "index_contour_code": props.get("IDXKNT"),
            "contour_type_code": props.get("JNSKNT"),
            "source_indication": props.get("ISBDTA"),
            "recording_indication": props.get("IRKDTA"),
            "recording_date_ms": props.get("TRDATA"),
            "publication_date_ms": props.get("PUBDTA"),
            "scale_max": props.get("SKLMAK"),
            "scale_min": props.get("SKLMIN"),
            "remark": props.get("REMARK"),
            "geometry_type": geom.get("type"),
        })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def depth_stats(rows: list[dict]) -> dict:
    vals = []
    for row in rows:
        value = row.get("depth_m")
        if isinstance(value, (int, float)):
            vals.append(float(value))
    if not vals:
        return {"count": 0}
    return {
        "count": len(vals),
        "min_m": min(vals),
        "max_m": max(vals),
        "mean_m": statistics.fmean(vals),
        "median_m": statistics.median(vals),
        "unique_depth_values": len(set(vals)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", type=Path)
    ap.add_argument("--contours", type=Path)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    if not args.points and not args.contours:
        ap.error("Berikan --points dan/atau --contours.")

    summary = {}

    if args.points:
        fc = load_fc(args.points)
        rows = point_rows(fc)
        csv_path = args.output_dir / "soundings.csv"
        write_csv(csv_path, rows)
        stats = depth_stats(rows)
        summary["soundings"] = {
            "source": str(args.points),
            "csv": str(csv_path),
            "features": len(rows),
            **stats,
        }
        print("=== Sounding points ===")
        print(json.dumps(summary["soundings"], indent=2))

    if args.contours:
        fc = load_fc(args.contours)
        rows = contour_rows(fc)
        csv_path = args.output_dir / "depth_contours.csv"
        write_csv(csv_path, rows)
        stats = depth_stats(rows)
        summary["contours"] = {
            "source": str(args.contours),
            "csv": str(csv_path),
            "features": len(rows),
            **stats,
        }
        print("=== Depth contours ===")
        print(json.dumps(summary["contours"], indent=2))

    summary_path = args.output_dir / "depth_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Summary saved: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
