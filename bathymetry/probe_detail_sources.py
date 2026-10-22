#!/usr/bin/env python3
"""
Probe/download more detailed public BIG bathymetry products for a chosen AOI.

Sources checked:
1. BATNAS raster ImageServer
2. DataBatimetri_BIG_2017 multi-scale feature layers
3. HIPSOGRAFI_WLP_25K feature layers

The script only uses public ArcGIS REST query/export operations.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

from download_bathymetry import (
    create_session,
    export_batnas,
    make_bathymetry_only,
    validate_geotiff,
)

DATA2017 = "https://geoservices.big.go.id/gis/rest/services/PKLP/DataBatimetri_BIG_2017/MapServer"
HIPS25K = "https://geoservices.big.go.id/rbi/rest/services/HIPSOGRAFI/HIPSOGRAFI_WLP_25K/MapServer"

PRESETS = {
    # Western Bangka Strait: sea corridor between eastern Sumatra and Bangka.
    "bangka-strait": (105.10, -2.50, 105.80, -1.60),
    # Around Tanjung Kelayang / north-western Belitung.
    "tanjung-kelayang": (107.55, -2.65, 107.78, -2.45),
}

DATA2017_LAYERS = {
    10: "LLN500K_titik",
    11: "LLN500K_kontur",
    12: "LLN500K_area",
    14: "LLN250K_titik",
    15: "LLN250K_kontur",
    16: "LLN250K_area",
    18: "LLN50K_titik",
    19: "LLN50K_kontur",
    20: "LLN50K_area",
    22: "LPI25K_titik",
    23: "LPI25K_kontur",
    24: "LPI25K_area",
    26: "LPI50K_titik",
    27: "LPI50K_kontur",
    28: "LPI50K_area",
    30: "LPI250K_titik",
    31: "LPI250K_kontur",
    32: "LPI250K_area",
}

HIPS25K_LAYERS = {
    0: "TitikKedalaman",
    2: "KonturKedalaman",
    3: "AreaKedalaman",
}


def parse_bbox(value: str):
    vals = tuple(float(x.strip()) for x in value.split(","))
    if len(vals) != 4:
        raise argparse.ArgumentTypeError("BBOX harus minLon,minLat,maxLon,maxLat")
    minx, miny, maxx, maxy = vals
    if minx >= maxx or miny >= maxy:
        raise argparse.ArgumentTypeError("BBOX tidak valid")
    return vals


def bbox_text(bbox):
    return ",".join(str(v) for v in bbox)


def query_count(session, base, layer_id, bbox, timeout):
    r = session.get(
        f"{base}/{layer_id}/query",
        params={
            "where": "1=1",
            "geometry": bbox_text(bbox),
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326",
            "returnCountOnly": "true",
            "f": "json",
        },
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(json.dumps(data["error"], ensure_ascii=False))
    return int(data.get("count") or 0)


def layer_metadata(session, base, layer_id, timeout):
    r = session.get(
        f"{base}/{layer_id}",
        params={"f": "pjson"},
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise RuntimeError("Layer metadata bukan JSON object")
    return data


def download_geojson(session, base, layer_id, bbox, output, timeout):
    meta = layer_metadata(session, base, layer_id, timeout)
    max_records = int(meta.get("maxRecordCount") or 1000)
    page_size = max(1, min(max_records, 2000))

    features = []
    offset = 0
    while True:
        r = session.get(
            f"{base}/{layer_id}/query",
            params={
                "where": "1=1",
                "geometry": bbox_text(bbox),
                "geometryType": "esriGeometryEnvelope",
                "spatialRel": "esriSpatialRelIntersects",
                "inSR": "4326",
                "outSR": "4326",
                "outFields": "*",
                "returnGeometry": "true",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "f": "geojson",
            },
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(json.dumps(data["error"], ensure_ascii=False))
        batch = data.get("features", []) if isinstance(data, dict) else []
        features.extend(batch)
        if len(batch) < page_size:
            break
        offset += len(batch)

    fc = {"type": "FeatureCollection", "features": features}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    return len(features)


def probe_group(session, label, base, layers, bbox, outdir, timeout, download_vectors):
    print(f"\n=== {label} ===")
    summary = {}
    for layer_id, alias in layers.items():
        try:
            meta = layer_metadata(session, base, layer_id, timeout)
            count = query_count(session, base, layer_id, bbox, timeout)
            summary[str(layer_id)] = {
                "alias": alias,
                "name": meta.get("name"),
                "type": meta.get("type"),
                "geometryType": meta.get("geometryType"),
                "count": count,
            }
            print(
                f"{layer_id:02d} {alias:18s} count={count:<8d} "
                f"name={meta.get('name')} type={meta.get('geometryType') or meta.get('type')}"
            )

            if download_vectors and count > 0 and meta.get("type") == "Feature Layer":
                path = outdir / f"{label.lower().replace(' ','_')}_{layer_id:02d}_{alias}.geojson"
                n = download_geojson(session, base, layer_id, bbox, path, timeout)
                summary[str(layer_id)]["output"] = str(path)
                summary[str(layer_id)]["downloaded_features"] = n
                print(f"   saved {path} ({n} features)")
        except Exception as exc:
            summary[str(layer_id)] = {"alias": alias, "error": str(exc)}
            print(f"{layer_id:02d} {alias:18s} ERROR {exc}")

    return summary


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Probe detailed BIG bathymetry sources for Bangka/Belitung or custom AOI."
    )
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--preset", choices=sorted(PRESETS))
    group.add_argument("--bbox", type=parse_bbox)

    ap.add_argument("--output-dir", default="output/bathymetry_detail")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--download-vectors", action="store_true")
    ap.add_argument("--skip-batnas", action="store_true")
    ap.add_argument("--positive-depth", action="store_true")
    args = ap.parse_args()

    bbox = PRESETS[args.preset] if args.preset else args.bbox
    label = args.preset or "custom"
    outdir = Path(args.output_dir) / label
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"AOI: {label}")
    print(f"BBOX: {bbox_text(bbox)}")
    print(f"Output: {outdir}")

    session = create_session()
    manifest = {"aoi": label, "bbox": list(bbox), "sources": {}}

    if not args.skip_batnas:
        print("\n=== BATNAS raster ===")
        tif = outdir / "batnas.tif"
        try:
            info = export_batnas(
                session, bbox, tif, args.timeout,
                width=None, height=None, max_size=4096,
            )
            validate_geotiff(tif)
            masked = outdir / (
                "batnas_depth_positive.tif"
                if args.positive_depth
                else "batnas_bathymetry_only.tif"
            )
            make_bathymetry_only(
                tif, masked, positive_depth=args.positive_depth
            )
            validate_geotiff(masked)
            manifest["sources"]["batnas"] = {
                "status": "downloaded",
                **info,
                "bathymetry_only": str(masked),
            }
        except Exception as exc:
            manifest["sources"]["batnas"] = {
                "status": "failed",
                "error": str(exc),
            }
            print(f"BATNAS ERROR: {exc}", file=sys.stderr)

    manifest["sources"]["data_batimetri_big_2017"] = probe_group(
        session,
        "DataBatimetri_BIG_2017",
        DATA2017,
        DATA2017_LAYERS,
        bbox,
        outdir,
        args.timeout,
        args.download_vectors,
    )

    manifest["sources"]["hipsografi_wlp_25k"] = probe_group(
        session,
        "HIPSOGRAFI_WLP_25K",
        HIPS25K,
        HIPS25K_LAYERS,
        bbox,
        outdir,
        args.timeout,
        args.download_vectors,
    )

    manifest_path = outdir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nManifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
