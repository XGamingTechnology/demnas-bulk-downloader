#!/usr/bin/env python3
"""Package previously downloaded BKPM GeoJSON into an offline-first static WebGIS.

Does not fetch from the network or infer missing point coordinates.
The HTML viewer loads these local files with an HTTP server (or GitHub Pages).
"""
from __future__ import annotations
import argparse
import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .spatial_quality import audit_records


def create_package(source: Path, destination: Path) -> dict:
    records_json = json.loads((source / "region_records.json").read_text(encoding="utf-8"))
    projects_json = json.loads((source / "bkpm_opportunities_api_points.geojson").read_text(encoding="utf-8"))
    commodities_json = json.loads((source / "bkpm_komoditas_original.geojson").read_text(encoding="utf-8"))
    api_audit = json.loads((source / "audit.json").read_text(encoding="utf-8"))

    if projects_json.get("type") != "FeatureCollection" or commodities_json.get("type") != "FeatureCollection":
        raise ValueError("Both source datasets must be GeoJSON FeatureCollection")
    records = records_json.get("records")
    projects = projects_json.get("features")
    commodities = commodities_json.get("features")
    if not isinstance(records, list) or not isinstance(projects, list) or not isinstance(commodities, list):
        raise ValueError("Invalid record/feature structure")
    if (len(records) != api_audit.get("reported_total_records")
            or api_audit.get("pagination_status") != "all_reported_pages_reached"):
        raise ValueError("Source API snapshot not complete per its own audit")
    qa, missing, shared, coverage = audit_records(records, projects)
    if (qa["source_duplicate_ids"] or qa["geojson_duplicate_ids"]
            or qa["geojson_invalid_feature_count"]
            or qa["expected_points_missing_from_geojson"]
            or qa["unexpected_geojson_ids"] or qa["coordinate_mismatch_ids"]):
        raise ValueError("Spatial ID/geometry audit failed; will not publish inconsistent data")
    if qa["expected_valid_points"] != len(projects):
        raise ValueError("Unexpected project point count")

    data_dir = destination / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    for original, outname in (
        ("bkpm_opportunities_api_points.geojson", "bkpm_opportunities_api_points.geojson"),
        ("bkpm_komoditas_original.geojson", "bkpm_komoditas_original.geojson"),
    ):
        shutil.copyfile(source / original, data_dir / outname)

    summary = {
        "packaged_utc": datetime.now(timezone.utc).isoformat(),
        "source_checked_at_utc": api_audit.get("checked_at_utc"),
        "quality_audited_utc": qa.get("audited_utc"),
        "source_record_count": len(records),
        "mapped_project_count": len(projects),
        "missing_project_coordinate_count": len(missing),
        "commodity_feature_count": len(commodities),
        "project_shared_coordinate_group_count": len(shared),
        "api_pagination_status": api_audit.get("pagination_status"),
        "source_api_endpoint": api_audit.get("region_source"),
        "source_commodity_endpoint": "https://regionalinvestment.bkpm.go.id/data/komoditas.geojson",
        "warnings": [
            "Coordinates are not field-validated sites",
            "Opportunity values are not LKPM realisations",
            "Five missing-coordinate projects are non-spatial records, not inferred points",
            "External CDN/basemap requires internet; local GeoJSON is packaged",
        ],
    }
    (data_dir / "snapshot.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (data_dir / "projects_without_coordinates.json").write_text(
        json.dumps(missing, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (data_dir / "shared_coordinates.json").write_text(
        json.dumps(shared, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (data_dir / "attribute_presence.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=Path("data/bkpm/spatial_api"))
    p.add_argument("--output", type=Path, default=Path("data/bkpm/webgis_preview"))
    args = p.parse_args(argv)
    source_html = Path(__file__).resolve().parent / "webgis" / "index.html"
    if not source_html.exists():
        p.error("Static WebGIS index.html missing from source tree")
    summary = create_package(args.input, args.output)
    shutil.copyfile(source_html, args.output / "index.html")
    print(json.dumps({"output": str(args.output),
                      "project_points": summary["mapped_project_count"],
                      "missing_coordinate_records": summary["missing_project_coordinate_count"],
                      "commodity_points": summary["commodity_feature_count"]},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
