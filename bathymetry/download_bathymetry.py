#!/usr/bin/env python3
"""
Download public bathymetry data from official BIG services.

Primary source:
- BATNAS Grid_Batimetri_Indonesia ImageServer -> GeoTIFF subset by BBOX

Optional:
- getSamples at a point
- Atlas 250K bathymetry vector classes -> GeoJSON

This tool only uses public BIG ArcGIS REST services.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import requests

BATNAS = "https://geoservices.big.go.id/raster/rest/services/BATNAS/Grid_Batimetri_Indonesia/ImageServer"
ATLAS_BATHY = "https://geoservices.big.go.id/gis/rest/services/PTRA/Atlas_250K_Kelautan/MapServer/9"


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    try:
        vals = tuple(float(x.strip()) for x in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "BBOX harus minLon,minLat,maxLon,maxLat"
        ) from exc
    if len(vals) != 4:
        raise argparse.ArgumentTypeError("BBOX harus empat angka")
    minx, miny, maxx, maxy = vals
    if minx >= maxx or miny >= maxy:
        raise argparse.ArgumentTypeError("BBOX tidak valid")
    return vals


def parse_point(value: str) -> tuple[float, float]:
    try:
        vals = tuple(float(x.strip()) for x in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Point harus lon,lat") from exc
    if len(vals) != 2:
        raise argparse.ArgumentTypeError("Point harus dua angka lon,lat")
    return vals


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; demnas-bulk-downloader/1.0)",
        "Accept": "*/*",
    })
    return s


def batnas_metadata(session: requests.Session, timeout: int) -> dict:
    r = session.get(BATNAS, params={"f": "pjson"}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict) or data.get("error"):
        raise RuntimeError(
            "BATNAS metadata tidak valid: "
            + json.dumps(data, ensure_ascii=False)[:1000]
        )
    return data


def choose_size(
    bbox: tuple[float, float, float, float],
    pixel_size_deg: float,
    max_size: int,
) -> tuple[int, int]:
    minx, miny, maxx, maxy = bbox
    width = max(1, int(math.ceil((maxx - minx) / pixel_size_deg)))
    height = max(1, int(math.ceil((maxy - miny) / pixel_size_deg)))

    scale = min(1.0, max_size / max(width, height))
    width = max(1, int(math.ceil(width * scale)))
    height = max(1, int(math.ceil(height * scale)))
    return width, height


def export_batnas(
    session: requests.Session,
    bbox: tuple[float, float, float, float],
    output: Path,
    timeout: int,
    width: int | None,
    height: int | None,
    max_size: int,
) -> dict:
    meta = batnas_metadata(session, timeout)
    pixel_size = float(meta.get("pixelSizeX") or 0.0013888889)

    if width is None or height is None:
        auto_w, auto_h = choose_size(bbox, pixel_size, max_size)
        width = width or auto_w
        height = height or auto_h

    bbox_text = ",".join(str(x) for x in bbox)
    params = {
        "bbox": bbox_text,
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": f"{width},{height}",
        "format": "tiff",
        "pixelType": "F32",
        "noDataInterpretation": "esriNoDataMatchAny",
        "f": "json",
    }

    r = session.get(
        BATNAS + "/exportImage",
        params=params,
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict) or data.get("error"):
        raise RuntimeError(
            "BATNAS exportImage gagal: "
            + json.dumps(data, ensure_ascii=False)[:1500]
        )

    href = data.get("href") or data.get("url")
    if not href:
        raise RuntimeError(
            "BATNAS exportImage tidak mengembalikan href/url."
        )

    print(f"Export size: {data.get('width')} x {data.get('height')}")
    print(f"Export extent: {data.get('extent')}")
    print(f"Download: {href}")

    img = session.get(href, timeout=timeout)
    img.raise_for_status()

    prefix = img.content[:4]
    if prefix not in (b"II*\x00", b"MM\x00*"):
        raise RuntimeError(
            "Response BATNAS bukan TIFF valid. "
            f"Content-Type={img.headers.get('content-type','')} "
            f"bytes={len(img.content)}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(img.content)
    print(f"GeoTIFF saved: {output} ({len(img.content)} bytes)")

    return {
        "source": "BIG BATNAS",
        "service": BATNAS,
        "bbox": list(bbox),
        "width": data.get("width"),
        "height": data.get("height"),
        "extent": data.get("extent"),
        "pixel_type": "F32",
        "output": str(output),
        "bytes": len(img.content),
    }


def sample_batnas(
    session: requests.Session,
    point: tuple[float, float],
    timeout: int,
) -> dict:
    lon, lat = point
    r = session.get(
        BATNAS + "/getSamples",
        params={
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "returnGeometry": "true",
            "returnFirstValueOnly": "true",
            "f": "json",
        },
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict) or data.get("error"):
        raise RuntimeError(
            "BATNAS getSamples gagal: "
            + json.dumps(data, ensure_ascii=False)[:1000]
        )
    return data


def download_atlas_vector(
    session: requests.Session,
    bbox: tuple[float, float, float, float],
    output: Path,
    timeout: int,
) -> int:
    bbox_text = ",".join(str(x) for x in bbox)
    r = session.get(
        ATLAS_BATHY + "/query",
        params={
            "where": "1=1",
            "geometry": bbox_text,
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326",
            "outSR": "4326",
            "outFields": "*",
            "returnGeometry": "true",
            "f": "geojson",
        },
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise RuntimeError("Atlas bathymetry response bukan GeoJSON object.")
    features = data.get("features") or []
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Atlas GeoJSON saved: {output} ({len(features)} features)")
    return len(features)


def validate_geotiff(path: Path) -> None:
    try:
        import rasterio
    except ModuleNotFoundError:
        print("rasterio tidak tersedia; validasi GeoTIFF dilewati.")
        return

    with rasterio.open(path) as ds:
        print("\n=== GeoTIFF ===")
        print(f"driver: {ds.driver}")
        print(f"size: {ds.width} x {ds.height}")
        print(f"crs: {ds.crs}")
        print(f"bounds: {ds.bounds}")
        print(f"bands: {ds.count}")
        print(f"dtype: {ds.dtypes}")
        print(f"nodata: {ds.nodata}")

        band = ds.read(1, masked=True)
        if band.count() > 0:
            print(f"valid_pixels: {band.count()}/{band.size}")
            print(f"min: {float(band.min())}")
            print(f"max: {float(band.max())}")
            print(f"mean: {float(band.mean())}")
        else:
            print("valid_pixels: 0")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Download public BIG BATNAS bathymetry by BBOX."
    )
    ap.add_argument("--bbox", type=parse_bbox, required=True)
    ap.add_argument(
        "--output",
        default="output/bathymetry/batnas.tif",
    )
    ap.add_argument("--width", type=int)
    ap.add_argument("--height", type=int)
    ap.add_argument(
        "--max-size",
        type=int,
        default=4096,
        help="Maximum auto-generated image dimension.",
    )
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument(
        "--sample",
        type=parse_point,
        help="Optional lon,lat point for getSamples.",
    )
    ap.add_argument(
        "--atlas-vector",
        action="store_true",
        help="Also download Atlas 250K bathymetry vector classes.",
    )
    ap.add_argument(
        "--metadata",
        action="store_true",
        help="Save BATNAS ImageServer metadata.",
    )
    args = ap.parse_args()

    session = create_session()
    out = Path(args.output)

    try:
        if args.metadata:
            meta = batnas_metadata(session, args.timeout)
            meta_path = out.with_suffix(".metadata.json")
            save_json(meta_path, meta)
            print(f"Metadata saved: {meta_path}")

        manifest = export_batnas(
            session,
            args.bbox,
            out,
            args.timeout,
            args.width,
            args.height,
            args.max_size,
        )
        save_json(out.with_suffix(".json"), manifest)
        validate_geotiff(out)

        point = args.sample
        if point is None:
            minx, miny, maxx, maxy = args.bbox
            point = ((minx + maxx) / 2, (miny + maxy) / 2)

        sample = sample_batnas(session, point, args.timeout)
        sample_path = out.with_suffix(".sample.json")
        save_json(sample_path, sample)
        print(f"Sample saved: {sample_path}")

        samples = sample.get("samples") if isinstance(sample, dict) else None
        if isinstance(samples, list) and samples:
            first = samples[0]
            print("Sample:", json.dumps(first, ensure_ascii=False))

        if args.atlas_vector:
            atlas_path = out.with_name(out.stem + "_atlas250k.geojson")
            download_atlas_vector(
                session, args.bbox, atlas_path, args.timeout
            )

    except (requests.RequestException, ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
