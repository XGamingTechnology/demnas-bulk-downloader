#!/usr/bin/env python3
"""
DEMNAS Bulk Downloader
Downloads DEMNAS from Badan Informasi Geospasial (BIG) ArcGIS ImageServer,
using an official BIG province boundary, then creates one masked GeoTIFF.

Default example:
    python download_demnas.py --province "Jawa Timur"
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import time
from pathlib import Path
from typing import Iterable

import numpy as np
import requests
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.windows import Window, bounds as window_bounds, transform as window_transform
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union
from shapely.prepared import prep


DEMNAS_SERVICE = (
    "https://geoservices.big.go.id/raster/rest/services/"
    "DEMNAS/DEM_Indonesia/ImageServer"
)
EXPORT_URL = f"{DEMNAS_SERVICE}/exportImage"

# Official BIG province boundary layer
PROVINCE_URL = (
    "https://geoservices.big.go.id/rbi/rest/services/"
    "BATASWILAYAH/BATAS_WILAYAH/MapServer/12"
)

# Native pixel size reported by BIG ImageServer, EPSG:4326
NATIVE_RES = 7.498500299940011e-5

# DEMNAS service full extent, used only for snapping to the native grid.
SERVICE_XMIN = 94.75
SERVICE_YMIN = -11.250000000000002

# Server says max image width=15000 and max height=4100.
# Keep a small safety margin.
TILE_W = 12000
TILE_H = 4000

NODATA = -9999.0
USER_AGENT = "demnas-bulk-downloader/1.0"


def norm_name(value: str) -> str:
    return " ".join(value.upper().strip().split())


def session_with_retries() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    adapter = requests.adapters.HTTPAdapter(
        max_retries=requests.adapters.Retry(
            total=5,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
        )
    )
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def get_province_geometry(session: requests.Session, province: str):
    """
    Ambil polygon provinsi langsung dari layer RBI BIG.
    Satu provinsi dapat terdiri dari banyak feature; semuanya digabung.
    """
    query_url = f"{PROVINCE_URL}/query"

    sql_province = province.replace("'", "''")

    params = {
        "where": f"wadmpr='{sql_province}'",
        "outFields": "wadmpr",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }

    print(f"[1/4] Mengambil batas provinsi resmi BIG: {province}")

    r = session.get(query_url, params=params, timeout=180)
    r.raise_for_status()
    data = r.json()

    features = data.get("features", [])

    if not features:
        raise RuntimeError(
            f"Provinsi '{province}' tidak ditemukan pada layer RBI BIG."
        )

    geometries = [
        shape(feature["geometry"])
        for feature in features
        if feature.get("geometry")
    ]

    if not geometries:
        raise RuntimeError("Feature ditemukan tetapi geometry kosong.")

    geom = unary_union(geometries)

    if geom.is_empty:
        raise RuntimeError("Geometry hasil union kosong.")

    print(
        f"      ditemukan {len(geometries)} feature; "
        f"digabung menjadi {geom.geom_type}"
    )

    return geom


def snap_down(v: float, origin: float, res: float) -> float:
    return origin + math.floor((v - origin) / res) * res


def snap_up(v: float, origin: float, res: float) -> float:
    return origin + math.ceil((v - origin) / res) * res


def aligned_extent(geom, res: float):
    minx, miny, maxx, maxy = geom.bounds
    xmin = snap_down(minx, SERVICE_XMIN, res)
    ymin = snap_down(miny, SERVICE_YMIN, res)
    xmax = snap_up(maxx, SERVICE_XMIN, res)
    ymax = snap_up(maxy, SERVICE_YMIN, res)
    width = int(round((xmax - xmin) / res))
    height = int(round((ymax - ymin) / res))
    return xmin, ymin, xmax, ymax, width, height


def iter_tiles(xmin, ymin, xmax, ymax, width, height, res):
    ncols = math.ceil(width / TILE_W)
    nrows = math.ceil(height / TILE_H)

    for row in range(nrows):
        h = min(TILE_H, height - row * TILE_H)
        tile_ymax = ymax - row * TILE_H * res
        tile_ymin = tile_ymax - h * res

        for col in range(ncols):
            w = min(TILE_W, width - col * TILE_W)
            tile_xmin = xmin + col * TILE_W * res
            tile_xmax = tile_xmin + w * res

            yield {
                "row": row,
                "col": col,
                "width": w,
                "height": h,
                "xmin": tile_xmin,
                "ymin": tile_ymin,
                "xmax": tile_xmax,
                "ymax": tile_ymax,
            }


def human_size(nbytes: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(nbytes)
    for unit in units:
        if x < 1024 or unit == units[-1]:
            return f"{x:.2f} {unit}"
        x /= 1024
    return f"{x:.2f} TB"


def request_export(session, tile, out_file: Path):
    """
    Ask ArcGIS for an export URL (JSON), then stream the TIFF to disk.
    """
    params = {
        "bbox": (
            f"{tile['xmin']:.15f},{tile['ymin']:.15f},"
            f"{tile['xmax']:.15f},{tile['ymax']:.15f}"
        ),
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": f"{tile['width']},{tile['height']}",
        "format": "tiff",
        "pixelType": "F32",
        "interpolation": "RSP_NearestNeighbor",
        "noData": str(NODATA),
        "noDataInterpretation": "esriNoDataMatchAny",
        "f": "json",
    }

    meta = session.get(EXPORT_URL, params=params, timeout=180)
    meta.raise_for_status()
    info = meta.json()

    if "error" in info:
        raise RuntimeError(json.dumps(info["error"], ensure_ascii=False))

    href = info.get("href")
    if not href:
        raise RuntimeError(
            "BIG tidak mengembalikan URL file pada exportImage. "
            f"Response: {json.dumps(info)[:1000]}"
        )

    tmp = out_file.with_suffix(out_file.suffix + ".part")
    with session.get(href, stream=True, timeout=600) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    if tmp.stat().st_size < 1024:
        raise RuntimeError(f"File terlalu kecil / invalid: {tmp}")

    tmp.replace(out_file)


def validate_tile(path: Path, expected_w: int, expected_h: int) -> bool:
    if not path.exists() or path.stat().st_size < 1024:
        return False
    try:
        with rasterio.open(path) as src:
            return (
                src.width == expected_w
                and src.height == expected_h
                and src.count >= 1
            )
    except Exception:
        return False


def download_tiles(session, tiles, geom, tiles_dir: Path):
    tiles_dir.mkdir(parents=True, exist_ok=True)
    prepared = prep(geom)
    needed = []

    # Skip tiles whose bbox doesn't intersect the province polygon.
    for t in tiles:
        if prepared.intersects(box(t["xmin"], t["ymin"], t["xmax"], t["ymax"])):
            needed.append(t)

    print(f"[2/4] Tile yang berpotongan dengan provinsi: {len(needed)}")

    for i, tile in enumerate(needed, 1):
        out = tiles_dir / f"demnas_r{tile['row']:03d}_c{tile['col']:03d}.tif"

        if validate_tile(out, tile["width"], tile["height"]):
            print(f"  [{i}/{len(needed)}] sudah ada, skip: {out.name}")
            tile["path"] = out
            continue

        print(
            f"  [{i}/{len(needed)}] download {out.name} "
            f"({tile['width']}x{tile['height']})"
        )

        last_err = None
        for attempt in range(1, 6):
            try:
                request_export(session, tile, out)
                if not validate_tile(out, tile["width"], tile["height"]):
                    raise RuntimeError("TIFF hasil download tidak lolos validasi.")
                last_err = None
                break
            except Exception as e:
                last_err = e
                part = out.with_suffix(out.suffix + ".part")
                if part.exists():
                    part.unlink(missing_ok=True)
                if attempt < 5:
                    sleep_s = min(30, attempt * 4)
                    print(f"      gagal: {e}; retry {attempt}/5 dalam {sleep_s}s")
                    time.sleep(sleep_s)

        if last_err is not None:
            raise RuntimeError(f"Gagal download {out.name}: {last_err}")

        tile["path"] = out

    return needed


def create_final_geotiff(tiles, geom, output: Path, extent, res):
    xmin, ymin, xmax, ymax, width, height = extent
    output.parent.mkdir(parents=True, exist_ok=True)

    profile = {
        "driver": "GTiff",
        "width": width,
        "height": height,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(xmin, ymax, res, res),
        "nodata": NODATA,
        "compress": "DEFLATE",
        "predictor": 3,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
        "BIGTIFF": "YES",
        "SPARSE_OK": "TRUE",
    }

    print(f"[3/4] Menyusun + mask ke batas provinsi: {output}")
    print(f"      ukuran raster final: {width:,} x {height:,} pixel")

    prepared = prep(geom)

    with rasterio.open(output, "w", **profile) as dst:
        # GeoTIFF unwritten areas behave as nodata only if explicitly initialized
        # when a tile is absent. We write nodata window-by-window only where needed.
        for i, tile in enumerate(tiles, 1):
            path = Path(tile["path"])
            col_off = tile["col"] * TILE_W
            row_off = tile["row"] * TILE_H
            dst_window = Window(
                col_off=col_off,
                row_off=row_off,
                width=tile["width"],
                height=tile["height"],
            )

            with rasterio.open(path) as src:
                # Process source by its internal blocks/windows to keep RAM low.
                for _, src_window in src.block_windows(1):
                    src_bounds = window_bounds(src_window, src.transform)
                    block_poly = box(*src_bounds)
                    if not prepared.intersects(block_poly):
                        continue

                    data = src.read(1, window=src_window).astype("float32", copy=False)
                    tr = window_transform(src_window, src.transform)

                    inside = geometry_mask(
                        [mapping(geom)],
                        out_shape=data.shape,
                        transform=tr,
                        invert=True,
                        all_touched=False,
                    )
                    masked = np.where(inside, data, NODATA).astype("float32", copy=False)

                    write_window = Window(
                        col_off=dst_window.col_off + src_window.col_off,
                        row_off=dst_window.row_off + src_window.row_off,
                        width=src_window.width,
                        height=src_window.height,
                    )
                    dst.write(masked, 1, window=write_window)

            print(f"  [{i}/{len(tiles)}] masuk final: {path.name}")

    # Build overviews for smoother QGIS/ArcGIS display.
    print("[4/4] Membuat overview raster...")
    with rasterio.open(output, "r+") as dst:
        factors = [
            f for f in (2, 4, 8, 16, 32, 64)
            if dst.width // f >= 256 and dst.height // f >= 256
        ]
        if factors:
            dst.build_overviews(factors, rasterio.enums.Resampling.average)
            dst.update_tags(ns="rio_overview", resampling="average")


def save_boundary(geom, province: str, output_dir: Path):
    safe = province.upper().replace(" ", "_")
    p = output_dir / f"BATAS_{safe}_BIG.geojson"
    feature = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"WADMPR": province},
            "geometry": mapping(geom),
        }],
    }
    p.write_text(json.dumps(feature, ensure_ascii=False), encoding="utf-8")
    return p


def main():
    parser = argparse.ArgumentParser(
        description="Bulk download DEMNAS resmi BIG per provinsi."
    )
    parser.add_argument(
        "--province",
        default="Jawa Timur",
        help='Nama provinsi, contoh: "Jawa Timur"',
    )
    parser.add_argument(
        "--workdir",
        default="data",
        help="Folder kerja (default: data)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Tidak meminta konfirmasi sebelum download.",
    )
    parser.add_argument(
        "--keep-tiles",
        action="store_true",
        help="Pertahankan tile TIFF setelah raster final selesai.",
    )
    args = parser.parse_args()

    province = args.province
    safe = norm_name(province).replace(" ", "_")
    workdir = Path(args.workdir)
    tiles_dir = workdir / "tiles" / safe
    output_dir = workdir / "output"
    output = output_dir / f"DEMNAS_{safe}.tif"

    session = session_with_retries()
    geom = get_province_geometry(session, province)
    output_dir.mkdir(parents=True, exist_ok=True)
    boundary_path = save_boundary(geom, province, output_dir)

    extent = aligned_extent(geom, NATIVE_RES)
    xmin, ymin, xmax, ymax, width, height = extent
    raw_bytes = width * height * 4
    all_tiles = list(iter_tiles(xmin, ymin, xmax, ymax, width, height, NATIVE_RES))
    intersecting_count = sum(
        1 for t in all_tiles
        if geom.intersects(box(t["xmin"], t["ymin"], t["xmax"], t["ymax"]))
    )

    print("\n=== DEMNAS Bulk Downloader ===")
    print(f"Provinsi           : {province}")
    print(f"CRS                : EPSG:4326")
    print(f"Resolusi           : {NATIVE_RES:.15f} derajat/pixel (native service)")
    print(f"Extent aligned     : {xmin:.6f}, {ymin:.6f}, {xmax:.6f}, {ymax:.6f}")
    print(f"Ukuran bbox        : {width:,} x {height:,} pixel")
    print(f"Tile intersect     : {intersecting_count}")
    print(f"Raw float32 bbox   : ~{human_size(raw_bytes)} sebelum kompresi/mask")
    print(f"Batas GeoJSON      : {boundary_path}")
    print(f"Output             : {output}\n")

    if not args.yes:
        answer = input("Lanjut download? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Dibatalkan.")
            return 0

    tiles = download_tiles(session, all_tiles, geom, tiles_dir)
    create_final_geotiff(tiles, geom, output, extent, NATIVE_RES)

    if not args.keep_tiles:
        print("Menghapus tile sementara...")
        shutil.rmtree(tiles_dir, ignore_errors=True)

    print("\nSELESAI")
    print(f"DEMNAS : {output.resolve()}")
    print(f"Batas  : {boundary_path.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nDihentikan oleh user. Tile yang sudah selesai tetap tersimpan untuk resume.")
        raise SystemExit(130)
