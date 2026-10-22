#!/usr/bin/env python3
"""Probe official BIG bathymetry services for public download capability."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

BATNAS = "https://geoservices.big.go.id/raster/rest/services/BATNAS/Grid_Batimetri_Indonesia/ImageServer"
GRID2017 = "https://geoservices.big.go.id/gis/rest/services/PKLP/GridBatimetri_2017/MapServer"
ATLAS_BATHY = "https://geoservices.big.go.id/gis/rest/services/PTRA/Atlas_250K_Kelautan/MapServer/9"


def bbox_arg(value: str):
    vals = [float(x.strip()) for x in value.split(",")]
    if len(vals) != 4:
        raise argparse.ArgumentTypeError("bbox harus minLon,minLat,maxLon,maxLat")
    return tuple(vals)


def show_json(label: str, r: requests.Response):
    print(f"\n=== {label} ===")
    print(f"HTTP {r.status_code} | {r.headers.get('content-type','')} | bytes={len(r.content)}")
    try:
        data = r.json()
    except ValueError:
        print(r.text[:800])
        return None
    if isinstance(data, dict):
        print("keys:", ", ".join(list(data.keys())[:30]))
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--bbox",
        type=bbox_arg,
        default=(104.08144856688278,-3.508670771548452,104.43584512679433,-3.3288696787825245),
    )
    ap.add_argument("--output-dir", default="output/bathymetry_probe")
    ap.add_argument("--timeout", type=int, default=45)
    args = ap.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    bbox = ",".join(str(x) for x in args.bbox)

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; demnas-bulk-downloader/1.0)",
        "Accept": "*/*",
    })

    # 1) BATNAS ImageServer metadata.
    r = s.get(BATNAS, params={"f": "pjson"}, timeout=args.timeout)
    meta = show_json("BATNAS ImageServer metadata", r)
    if isinstance(meta, dict):
        for k in ("name","pixelSizeX","pixelSizeY","pixelType","bandCount","capabilities","extent"):
            if k in meta:
                print(f"{k}: {meta[k]}")
        (out / "batnas_metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 2) Ask ImageServer for a BBOX subset. f=json should return an image URL
    # if Export Image is enabled.
    r = s.get(
        BATNAS + "/exportImage",
        params={
            "bbox": bbox,
            "bboxSR": "4326",
            "imageSR": "4326",
            "size": "512,512",
            "format": "tiff",
            "pixelType": "F32",
            "f": "json",
        },
        timeout=args.timeout,
    )
    exp = show_json("BATNAS exportImage", r)
    if isinstance(exp, dict):
        print("export href/url:", exp.get("href") or exp.get("url"))
        (out / "batnas_export_response.json").write_text(
            json.dumps(exp, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 3) One sample depth-like value at the AOI centre.
    minx, miny, maxx, maxy = args.bbox
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2
    r = s.get(
        BATNAS + "/getSamples",
        params={
            "geometry": f"{cx},{cy}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "returnFirstValueOnly": "true",
            "f": "json",
        },
        timeout=args.timeout,
    )
    samples = show_json("BATNAS getSamples", r)
    if samples is not None:
        (out / "batnas_sample.json").write_text(
            json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 4) Older national grid service: useful fallback/render source.
    r = s.get(GRID2017, params={"f": "pjson"}, timeout=args.timeout)
    grid = show_json("GridBatimetri_2017 metadata", r)
    if isinstance(grid, dict):
        (out / "grid2017_metadata.json").write_text(
            json.dumps(grid, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 5) Vector bathymetry classes (0-500m, 500-1000m, ...).
    r = s.get(
        ATLAS_BATHY + "/query",
        params={
            "where": "1=1",
            "geometry": bbox,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "outSR": "4326",
            "outFields": "*",
            "returnGeometry": "true",
            "f": "geojson",
        },
        timeout=args.timeout,
    )
    print("\n=== Atlas 250K bathymetry vector ===")
    print(f"HTTP {r.status_code} | {r.headers.get('content-type','')} | bytes={len(r.content)}")
    if r.ok:
        try:
            fc = r.json()
            feats = fc.get("features", []) if isinstance(fc, dict) else []
            print(f"features={len(feats)}")
            if feats:
                print("sample properties:", feats[0].get("properties"))
            (out / "atlas250k_bathymetry.geojson").write_text(
                json.dumps(fc, ensure_ascii=False), encoding="utf-8"
            )
        except ValueError:
            print(r.text[:800])

    print(f"\nSaved probe outputs: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
