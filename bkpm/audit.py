#!/usr/bin/env python3
"""Audit ONLY three BKPM GeoJSON URLs observed in browser Network.

Usage:
    python -m bkpm.audit
    python -m bkpm.audit --offline --dem data/output/DEMNAS_JAWA_TIMUR.tif
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from shapely.geometry import shape

BASE = "https://regionalinvestment.bkpm.go.id"
SOURCES = (
    "wilayah_barat.geojson",
    "wilayah_tengah.geojson",
    "wilayah_timur.geojson",
)
EXPECTED_REGION = {
    "wilayah_barat.geojson": "Barat",
    "wilayah_tengah.geojson": "Tengah",
    "wilayah_timur.geojson": "Timur",
}
MAX_FILE_BYTES = 150 * 1024 * 1024
FIELDS = ("NAME_0", "NAME_1", "KODE", "Wilayah")


def session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "demnas-bkpm-public-geojson-audit/0.1"
    retry = Retry(
        total=2, backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def fetch_file(http: requests.Session, filename: str, destination: Path) -> None:
    """Bounded public file download; don't follow redirects to other hosts."""
    url = f"{BASE}/data/{filename}"
    tmp = destination.with_name(destination.name + ".part")
    from urllib.parse import urlparse

    with http.get(url, timeout=(15, 90), stream=True) as response:
        if urlparse(response.url).hostname != "regionalinvestment.bkpm.go.id":
            raise RuntimeError("Redirect menuju host tidak diizinkan")
        response.raise_for_status()
        total = 0
        with tmp.open("wb") as out:
            for chunk in response.iter_content(1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_FILE_BYTES:
                    raise RuntimeError(f"Ukuran {filename} melewati batas aman 150 MiB")
                out.write(chunk)
    os.replace(tmp, destination)


def validate_collection(document: dict, filename: str) -> tuple[list[dict], dict]:
    """Validate schema and report anomalies; preserve source geometries."""
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raise ValueError(f"{filename}: root bukan GeoJSON FeatureCollection")
    features = document.get("features")
    if not isinstance(features, list):
        raise ValueError(f"{filename}: features bukan list")

    geometries = Counter()
    missing_fields = Counter()
    invalid_shapes = 0
    mismatch_region = 0
    province_names: list[str] = []
    codes: list[str] = []
    bbox = [float("inf"), float("inf"), float("-inf"), float("-inf")]

    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"{filename}: features[{index}] bukan Feature")
        props = feature.get("properties")
        if not isinstance(props, dict):
            raise ValueError(f"{filename}: features[{index}] tanpa properties")
        for field in FIELDS:
            if props.get(field) is None or props.get(field) == "":
                missing_fields[field] += 1
        if props.get("Wilayah") != EXPECTED_REGION[filename]:
            mismatch_region += 1
        if props.get("NAME_1"):
            province_names.append(str(props["NAME_1"]))
        if props.get("KODE") is not None:
            codes.append(str(props["KODE"]))
        geom = feature.get("geometry")
        if geom is None:
            geometries["null"] += 1
            continue
        if not isinstance(geom, dict):
            raise ValueError(f"{filename}: invalid geometry at feature {index}")
        geometries[str(geom.get("type", "unknown"))] += 1
        try:
            polygon = shape(geom)
            if polygon.is_empty or not polygon.is_valid:
                invalid_shapes += 1
            else:
                xmin, ymin, xmax, ymax = polygon.bounds
                bbox = [min(xmin, bbox[0]), min(ymin, bbox[1]),
                        max(xmax, bbox[2]), max(ymax, bbox[3])]
        except (TypeError, ValueError, KeyError):
            invalid_shapes += 1

    duplicated_names = sorted(k for k, v in Counter(province_names).items() if v > 1)
    duplicated_codes = sorted(k for k, v in Counter(codes).items() if v > 1)
    summary = {
        "source": f"{BASE}/data/{filename}",
        "feature_count": len(features),
        "geometry_types": dict(geometries),
        "fields": list(FIELDS),
        "missing_field_counts": dict(missing_fields),
        "invalid_or_empty_geometries": invalid_shapes,
        "wrong_region_label_count": mismatch_region,
        "duplicate_names": duplicated_names,
        "duplicate_codes": duplicated_codes,
        "province_names": sorted(set(province_names)),
        "bbox_epsg4326": bbox if bbox[0] != float("inf") else None,
    }
    return features, summary


def csv_write(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/bkpm"))
    parser.add_argument("--offline", action="store_true", help="Hanya data cache lokal")
    parser.add_argument("--refresh", action="store_true", help="Unduh ulang semua sumber")
    parser.add_argument("--dem", type=Path, help="GeoTIFF DEMNAS lokal; tidak diunduh")
    parser.add_argument("--max-grid", type=int, default=256,
                        help="Grid sampling maksimum per provinsi (default: 256)")
    args = parser.parse_args(argv)
    if args.offline and args.refresh:
        parser.error("--offline dan --refresh tidak boleh bersamaan")

    args.output.mkdir(parents=True, exist_ok=True)
    http = session()
    all_features = []
    summaries = []
    rows = []

    for filename in SOURCES:
        file_path = args.output / filename
        if args.refresh or not file_path.exists():
            if args.offline:
                print(f"ERROR: data lokal belum ada: {file_path}", file=sys.stderr)
                return 2
            print(f"GET {BASE}/data/{filename}")
            try:
                fetch_file(http, filename, file_path)
            except (requests.RequestException, OSError, RuntimeError) as exc:
                print(f"ERROR: {filename}: {exc}", file=sys.stderr)
                return 2

        try:
            raw = file_path.read_bytes()
            data = json.loads(raw)
            features, summary = validate_collection(data, filename)
            summary["sha256"] = hashlib.sha256(raw).hexdigest()
            summary["downloaded_bytes"] = len(raw)
        except (ValueError, OSError, UnicodeDecodeError, TypeError) as exc:
            print(f"ERROR: format {filename}: {exc}", file=sys.stderr)
            return 2

        summaries.append(summary)
        for feature in features:
            props = dict(feature["properties"])
            props["BKPM_SOURCE"] = filename
            all_features.append({
                "type": "Feature",
                "geometry": feature.get("geometry"),
                "properties": props,
            })
            rows.append({
                "NAME_0": props.get("NAME_0"),
                "NAME_1": props.get("NAME_1"),
                "KODE": props.get("KODE"),
                "Wilayah": props.get("Wilayah"),
                "source_file": filename,
            })
        print(f"OK {filename}: {len(features)} fitur; {summary['geometry_types']}")

    names = [str(r["NAME_1"]) for r in rows if r["NAME_1"]]
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "audit public GeoJSON boundaries, not investment attributes",
        "sources": summaries,
        "feature_total": len(rows),
        "unique_province_names": len(set(names)),
        "duplicated_province_names": sorted(
            k for k, v in Counter(names).items() if v > 1
        ),
        "note": "Province coverage and boundaries must be checked against current authoritative administrative data.",
    }

    if args.dem:
        if not args.dem.is_file():
            parser.error(f"--dem file tidak ada: {args.dem}")
        from .dem import summarize_dem
        elevation_rows = summarize_dem(all_features, str(args.dem), args.max_grid)
        csv_write(args.output / "terrain_sample_approx.csv", elevation_rows)
        report["terrain"] = {
            "input_dem": str(args.dem),
            "grid_limit": args.max_grid,
            "method": "downsampled raster window + polygon center-cell mask",
            "warning": "Approximate exploratory values, not native-resolution zonal statistics or suitability scores",
        }

    merged = {"type": "FeatureCollection", "features": all_features}
    (args.output / "bkpm_wilayah_merged.geojson").write_text(
        json.dumps(merged, ensure_ascii=False), encoding="utf-8"
    )
    (args.output / "audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    csv_write(args.output / "provinces.csv", rows)
    print(f"Done: {len(rows)} fitur, {len(set(names))} nama provinsi unik -> {args.output}")
    print("Periksa audit.json untuk temuan; endpoint investasi dinamis belum diidentifikasi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
