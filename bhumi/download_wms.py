#!/usr/bin/env python3
"""
BHUMI WMS downloader.

Designed for a local/proxied WMS endpoint such as:
    http://127.0.0.1:8765/bhumi/wms

Features:
- fetch/save GetCapabilities
- list advertised layers
- download a single BBOX
- split a BBOX into a grid of WMS GetMap requests
- georeference image tiles and mosaic them into one GeoTIFF

Notes:
- Defaults to WMS 1.1.1 to avoid EPSG:4326 axis-order surprises in WMS 1.3.0.
- Rasterio is only required when downloading/creating GeoTIFFs. Capabilities
  discovery and layer listing only need requests.
- This script downloads what the WMS advertises/renders. It does not bypass
  authentication or access controls.
"""

from __future__ import annotations

import argparse
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

import requests


DEFAULT_URL = "http://127.0.0.1:8765/bhumi/wms"
DEFAULT_VERSION = "1.1.1"


def request_with_retry(
    session: requests.Session,
    url: str,
    *,
    params: dict,
    timeout: int,
    retries: int,
    delay: float,
) -> requests.Response:
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == retries:
                raise
            time.sleep(delay * attempt)
    raise RuntimeError(last_exc)


def get_capabilities(
    session: requests.Session,
    url: str,
    version: str,
    timeout: int,
    retries: int,
    delay: float,
) -> bytes:
    params = {
        "SERVICE": "WMS",
        "REQUEST": "GetCapabilities",
        "VERSION": version,
    }
    return request_with_retry(
        session,
        url,
        params=params,
        timeout=timeout,
        retries=retries,
        delay=delay,
    ).content


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def iter_layers(xml_bytes: bytes) -> Iterable[tuple[str, str]]:
    root = ET.fromstring(xml_bytes)
    for elem in root.iter():
        if local_name(elem.tag) != "Layer":
            continue

        name = None
        title = None
        for child in elem:
            lname = local_name(child.tag)
            if lname == "Name" and child.text:
                name = child.text.strip()
            elif lname == "Title" and child.text:
                title = child.text.strip()

        if name:
            yield name, title or name


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    try:
        parts = [float(x.strip()) for x in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "BBOX harus: minx,miny,maxx,maxy"
        ) from exc

    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "BBOX harus berisi 4 angka: minx,miny,maxx,maxy"
        )

    minx, miny, maxx, maxy = parts
    if minx >= maxx or miny >= maxy:
        raise argparse.ArgumentTypeError("BBOX tidak valid")
    return minx, miny, maxx, maxy


def split_bbox(
    bbox: tuple[float, float, float, float],
    cols: int,
    rows: int,
):
    minx, miny, maxx, maxy = bbox
    dx = (maxx - minx) / cols
    dy = (maxy - miny) / rows

    for row in range(rows):
        y0 = miny + row * dy
        y1 = miny + (row + 1) * dy
        for col in range(cols):
            x0 = minx + col * dx
            x1 = minx + (col + 1) * dx
            yield row, col, (x0, y0, x1, y1)


def get_map(
    session: requests.Session,
    url: str,
    *,
    version: str,
    layer: str,
    bbox: tuple[float, float, float, float],
    crs: str,
    width: int,
    height: int,
    image_format: str,
    transparent: bool,
    styles: str,
    timeout: int,
    retries: int,
    delay: float,
) -> bytes:
    minx, miny, maxx, maxy = bbox

    params = {
        "SERVICE": "WMS",
        "VERSION": version,
        "REQUEST": "GetMap",
        "LAYERS": layer,
        "STYLES": styles,
        "BBOX": f"{minx},{miny},{maxx},{maxy}",
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": image_format,
        "TRANSPARENT": "TRUE" if transparent else "FALSE",
    }

    if version == "1.3.0":
        params["CRS"] = crs
    else:
        params["SRS"] = crs

    response = request_with_retry(
        session,
        url,
        params=params,
        timeout=timeout,
        retries=retries,
        delay=delay,
    )

    ctype = response.headers.get("Content-Type", "").lower()
    if "xml" in ctype or "text" in ctype:
        text = response.text[:2000]
        raise RuntimeError(f"WMS mengembalikan error/non-image:\n{text}")

    return response.content


def require_rasterio():
    try:
        import rasterio
        from rasterio.io import MemoryFile
        from rasterio.merge import merge
        from rasterio.transform import from_bounds
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Fitur download GeoTIFF membutuhkan rasterio. "
            "Install dependency terlebih dahulu, misalnya di virtualenv: "
            "python3 -m venv .venv && source .venv/bin/activate && "
            "pip install -r requirements.txt"
        ) from exc
    return rasterio, MemoryFile, merge, from_bounds


def image_bytes_to_geotiff(
    image_bytes: bytes,
    bbox: tuple[float, float, float, float],
    crs: str,
    output_path: Path,
) -> None:
    rasterio, MemoryFile, _merge, from_bounds = require_rasterio()
    minx, miny, maxx, maxy = bbox

    with MemoryFile(image_bytes) as memfile:
        with memfile.open() as src:
            data = src.read()
            profile = src.profile.copy()

            profile.update(
                driver="GTiff",
                crs=crs,
                transform=from_bounds(
                    minx,
                    miny,
                    maxx,
                    maxy,
                    src.width,
                    src.height,
                ),
                compress="deflate",
                tiled=True,
            )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(output_path, "w", **profile) as dst:
                dst.write(data)


def mosaic_tiles(tile_paths: list[Path], output_path: Path) -> None:
    rasterio, _MemoryFile, merge, _from_bounds = require_rasterio()
    datasets = [rasterio.open(path) for path in tile_paths]
    try:
        mosaic, transform = merge(datasets)
        profile = datasets[0].profile.copy()
        profile.update(
            height=mosaic.shape[1],
            width=mosaic.shape[2],
            transform=transform,
            driver="GTiff",
            compress="deflate",
            tiled=True,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(mosaic)
    finally:
        for ds in datasets:
            ds.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download layer BHUMI/OGC WMS menjadi GeoTIFF."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL endpoint WMS")
    parser.add_argument("--version", default=DEFAULT_VERSION, choices=["1.1.1", "1.3.0"])
    parser.add_argument("--capabilities", action="store_true", help="Simpan GetCapabilities")
    parser.add_argument("--list-layers", action="store_true", help="Tampilkan daftar layer")
    parser.add_argument("--layer", help="Nama layer WMS")
    parser.add_argument("--bbox", type=parse_bbox, help="minx,miny,maxx,maxy")
    parser.add_argument("--crs", default="EPSG:4326")
    parser.add_argument("--width", type=int, default=2048, help="Lebar pixel per tile")
    parser.add_argument("--height", type=int, default=2048, help="Tinggi pixel per tile")
    parser.add_argument("--cols", type=int, default=1, help="Jumlah tile arah X")
    parser.add_argument("--rows", type=int, default=1, help="Jumlah tile arah Y")
    parser.add_argument("--format", default="image/png", dest="image_format")
    parser.add_argument("--styles", default="")
    parser.add_argument("--opaque", action="store_true", help="Nonaktifkan transparansi")
    parser.add_argument("--output", default="bhumi_output.tif")
    parser.add_argument("--workdir", default=".bhumi_tiles")
    parser.add_argument("--keep-tiles", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": "demnas-bulk-downloader/bhumi-wms"})

    capabilities_xml = None
    if args.capabilities or args.list_layers:
        capabilities_xml = get_capabilities(
            session,
            args.url,
            args.version,
            args.timeout,
            args.retries,
            args.delay,
        )

    if args.capabilities:
        cap_path = Path("bhumi_wms_capabilities.xml")
        cap_path.write_bytes(capabilities_xml)
        print(f"Capabilities disimpan: {cap_path}")

    if args.list_layers:
        layers = list(iter_layers(capabilities_xml))
        if not layers:
            print("Tidak menemukan layer bernama pada GetCapabilities.")
        else:
            for idx, (name, title) in enumerate(layers, 1):
                print(f"{idx:4d}. {name} | {title}")

    if not args.layer and not args.bbox:
        if args.capabilities or args.list_layers:
            return 0
        parser.error(
            "Gunakan --list-layers / --capabilities, atau berikan --layer dan --bbox."
        )

    if not args.layer or not args.bbox:
        parser.error("Download membutuhkan --layer dan --bbox.")

    if args.cols < 1 or args.rows < 1:
        parser.error("--cols dan --rows minimal 1")

    require_rasterio()

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    tile_paths: list[Path] = []

    total = args.cols * args.rows
    for i, (row, col, tile_bbox) in enumerate(
        split_bbox(args.bbox, args.cols, args.rows),
        1,
    ):
        tile_path = workdir / f"tile_r{row:03d}_c{col:03d}.tif"
        print(
            f"[{i}/{total}] Download tile r={row} c={col} "
            f"bbox={','.join(map(str, tile_bbox))}"
        )

        image_bytes = get_map(
            session,
            args.url,
            version=args.version,
            layer=args.layer,
            bbox=tile_bbox,
            crs=args.crs,
            width=args.width,
            height=args.height,
            image_format=args.image_format,
            transparent=not args.opaque,
            styles=args.styles,
            timeout=args.timeout,
            retries=args.retries,
            delay=args.delay,
        )
        image_bytes_to_geotiff(image_bytes, tile_bbox, args.crs, tile_path)
        tile_paths.append(tile_path)

        if args.delay > 0:
            time.sleep(args.delay)

    output_path = Path(args.output)
    if len(tile_paths) == 1:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tile_paths[0].replace(output_path)
    else:
        mosaic_tiles(tile_paths, output_path)

    print(f"Selesai: {output_path.resolve()}")

    if not args.keep_tiles:
        for path in tile_paths:
            if path.exists() and path != output_path:
                path.unlink()
        try:
            workdir.rmdir()
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
