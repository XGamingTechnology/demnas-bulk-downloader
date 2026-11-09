#!/usr/bin/env python3
"""Offline quality-control of downloaded BKPM investment opportunity snapshots.

No HTTP requests. Uses the 185-record API snapshot and project GeoJSON that
spatial_api_collect.py generated. Never makes coordinates up for missing points.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .spatial_api_collect import make_point

FIELDS_TO_CHECK = ("id_peluang", "nama", "lon", "lat")
CANDIDATE_INVESTMENT_FIELDS = ("invest", "sektor", "irr", "npv", "status", "provinsi", "kabupaten")


def present(value):
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def stringify(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return str(value)


def audit_records(records: list[dict], features: list[dict]) -> tuple[dict, list[dict], list[dict], list[dict]]:
    """Return (report, missing-coordinate rows, duplicate-location groups, field coverage)."""
    if not isinstance(records, list) or not isinstance(features, list):
        raise ValueError("Records and features must be lists")

    id_counts = Counter(
        r.get("id_peluang") for r in records
        if isinstance(r, dict) and isinstance(r.get("id_peluang"), int)
        and not isinstance(r.get("id_peluang"), bool)
    )
    repeated_ids = [k for k, v in id_counts.items() if v > 1]
    expected_points = {}
    missing = []
    reasons = Counter()
    keys = Counter()

    for record in records:
        if not isinstance(record, dict):
            reasons["record_not_object"] += 1
            missing.append({"id_peluang": "", "nama": "", "lon_raw": "",
                            "lat_raw": "", "reason": "record_not_object"})
            continue
        for k, v in record.items():
            if present(v):
                keys[str(k)] += 1
        feature, status = make_point(record)
        reasons[status] += 1
        if feature:
            pid = record["id_peluang"]
            expected_points[pid] = feature["geometry"]["coordinates"]
        else:
            missing.append({
                "id_peluang": stringify(record.get("id_peluang")),
                "nama": stringify(record.get("nama")),
                "lon_raw": stringify(record.get("lon")),
                "lat_raw": stringify(record.get("lat")),
                "province_raw": stringify(record.get("provinsi", record.get("nama_provinsi"))),
                "district_raw": stringify(record.get("kabupaten_kota", record.get("nama_kabupaten"))),
                "reason": status,
            })

    exported_ids = Counter()
    actual_coords = {}
    invalid_export_features = 0
    for feature in features:
        try:
            pid = feature["properties"]["source_project_id"]
            xy = feature["geometry"]["coordinates"]
            if isinstance(pid, bool) or not isinstance(pid, int):
                raise ValueError("Invalid ID")
            if not isinstance(xy, list) or len(xy) != 2:
                raise ValueError("Invalid coordinate shape")
            exported_ids[pid] += 1
            actual_coords[pid] = xy
        except (KeyError, ValueError, TypeError):
            invalid_export_features += 1

    missing_in_export = sorted(set(expected_points) - set(exported_ids))
    unexpected_in_export = sorted(set(exported_ids) - set(expected_points))
    altered_positions = [
        pid for pid, xy in expected_points.items()
        if pid in actual_coords and any(
            abs(float(a) - float(b)) > 1e-9
            for a, b in zip(xy, actual_coords[pid])
        )
    ]
    groups = defaultdict(list)
    for pid, xy in expected_points.items():
        groups[tuple(round(float(v), 7) for v in xy)].append(pid)
    duplicated_locations = [
        {
            "longitude": str(xy[0]), "latitude": str(xy[1]),
            "project_count": len(ids), "project_ids": ",".join(map(str, sorted(ids))),
            "note": "Shared coordinates; not necessarily a data error"
        } for xy, ids in sorted(groups.items()) if len(ids) > 1
    ]

    coverage = [
        {
            "field": field,
            "nonempty_records": keys.get(field, 0),
            "total_records": len(records),
            "share_pct": round(keys.get(field, 0) * 100 / len(records), 2) if records else 0,
        } for field in sorted(
            set(FIELDS_TO_CHECK)
            | {key for key in keys if any(token in key.lower() for token in CANDIDATE_INVESTMENT_FIELDS)}
        )
    ]
    report = {
        "source_record_count": len(records),
        "source_unique_valid_ids": len(id_counts),
        "source_duplicate_ids": sorted(repeated_ids),
        "expected_valid_points": len(expected_points),
        "coordinate_failure_count": len(missing),
        "coordinate_checks": dict(reasons),
        "geojson_point_count": len(features),
        "geojson_unique_ids": len(exported_ids),
        "geojson_duplicate_ids": sorted(k for k, v in exported_ids.items() if v > 1),
        "geojson_invalid_feature_count": invalid_export_features,
        "expected_points_missing_from_geojson": missing_in_export,
        "unexpected_geojson_ids": unexpected_in_export,
        "coordinate_mismatch_ids": sorted(altered_positions),
        "shared_coordinate_groups": len(duplicated_locations),
        "interpretation": [
            "Coordinate range check is not site-level spatial verification",
            "Shared coordinates can be genuine co-located projects or regional centroids",
            "Investment opportunities and realized LKPM statistics must not be summed",
            "Missing coordinates remain absent; no geocoding or artificial points generated",
        ],
    }
    return report, missing, duplicated_locations, coverage


def write_csv(path: Path, records: list[dict], headers: list[str]):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/bkpm/spatial_api"))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    inp = args.input
    out = args.output or inp / "quality"
    data = json.loads((inp / "region_records.json").read_text(encoding="utf-8"))
    point_geojson = json.loads(
        (inp / "bkpm_opportunities_api_points.geojson").read_text(encoding="utf-8")
    )
    records = data.get("records")
    if point_geojson.get("type") != "FeatureCollection":
        parser.error("Point file is not a FeatureCollection")
    report, missing, shared, coverage = audit_records(records, point_geojson.get("features"))
    report["audited_utc"] = datetime.now(timezone.utc).isoformat()
    prior_audit_path = inp / "audit.json"
    if prior_audit_path.exists():
        previous = json.loads(prior_audit_path.read_text(encoding="utf-8"))
        report["api_reported_total_records"] = previous.get("reported_total_records")
        report["api_pagination_status"] = previous.get("pagination_status")
        report["record_total_matches_api"] = (
            report["source_record_count"] == previous.get("reported_total_records")
        )
    out.mkdir(parents=True, exist_ok=True)
    (out / "quality_summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_csv(out / "projects_without_coordinates.csv", missing,
              ["id_peluang", "nama", "lon_raw", "lat_raw",
               "province_raw", "district_raw", "reason"])
    write_csv(out / "shared_coordinates.csv", shared,
              ["longitude", "latitude", "project_count", "project_ids", "note"])
    write_csv(out / "attribute_presence.csv", coverage,
              ["field", "nonempty_records", "total_records", "share_pct"])
    print(json.dumps({
        "records": report["source_record_count"],
        "points": report["geojson_point_count"],
        "missing_coordinates": report["coordinate_failure_count"],
        "shared_coordinate_groups": report["shared_coordinate_groups"],
        "ids_or_geometry_mismatch": bool(
            report["source_duplicate_ids"]
            or report["geojson_duplicate_ids"]
            or report["expected_points_missing_from_geojson"]
            or report["unexpected_geojson_ids"]
            or report["coordinate_mismatch_ids"]
            or report["geojson_invalid_feature_count"]
        ),
        "output": str(out),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
