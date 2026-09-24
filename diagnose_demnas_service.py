#!/usr/bin/env python3
import json
import tempfile
from pathlib import Path

import numpy as np
import rasterio

from download_demnas import DEMNAS_SERVICE, EXPORT_URL, session_with_retries

POINT_X = 100.45
POINT_Y = -0.86
BBOX = (100.44, -0.87, 100.46, -0.85)
SIZE = (256, 256)


def print_json(title, data):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    print(json.dumps(data, indent=2, ensure_ascii=False)[:5000])


def inspect_tiff(path):
    with rasterio.open(path) as ds:
        a = ds.read(1).astype("float64", copy=False)
        finite = np.isfinite(a)
        x = a[finite]
        print("Driver     :", ds.driver)
        print("CRS        :", ds.crs)
        print("Size       :", ds.width, "x", ds.height)
        print("Dtype      :", ds.dtypes)
        print("NoData     :", ds.nodata)
        print("Bounds     :", ds.bounds)
        print("Finite px  :", f"{x.size:,}")
        if x.size:
            print("Min        :", float(x.min()))
            print("Median     :", float(np.median(x)))
            print("Max        :", float(x.max()))
            vals, counts = np.unique(x, return_counts=True)
            order = np.argsort(counts)[-10:][::-1]
            print("Most common values:")
            for i in order:
                print("  ", float(vals[i]), int(counts[i]))


def export_variant(session, label, extra):
    xmin, ymin, xmax, ymax = BBOX
    params = {
        "bbox": f"{xmin},{ymin},{xmax},{ymax}",
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": f"{SIZE[0]},{SIZE[1]}",
        "format": "tiff",
        "f": "json",
    }
    params.update(extra)

    print("\n" + "=" * 72)
    print("EXPORT VARIANT:", label)
    print("=" * 72)
    print("Params:", params)

    r = session.get(EXPORT_URL, params=params, timeout=180)
    r.raise_for_status()
    info = r.json()
    print("Response:", json.dumps(info, ensure_ascii=False)[:3000])

    if "error" in info:
        return
    href = info.get("href")
    if not href:
        print("No href returned")
        return

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / f"{label}.tif"
        rr = session.get(href, timeout=300)
        rr.raise_for_status()
        out.write_bytes(rr.content)
        print("Downloaded :", out.stat().st_size, "bytes")
        try:
            inspect_tiff(out)
        except Exception as e:
            print("Raster inspect ERROR:", repr(e))


def main():
    session = session_with_retries()

    print("DEMNAS service:", DEMNAS_SERVICE)
    print("Test point     :", POINT_X, POINT_Y)
    print("Test bbox      :", BBOX)

    # 1) Service metadata
    r = session.get(DEMNAS_SERVICE, params={"f": "json"}, timeout=120)
    r.raise_for_status()
    meta = r.json()
    print_json("SERVICE METADATA (selected)", {
        "pixelType": meta.get("pixelType"),
        "pixelSizeX": meta.get("pixelSizeX"),
        "pixelSizeY": meta.get("pixelSizeY"),
        "minValues": meta.get("minValues"),
        "maxValues": meta.get("maxValues"),
        "extent": meta.get("extent"),
        "defaultMosaicMethod": meta.get("defaultMosaicMethod"),
        "defaultResamplingMethod": meta.get("defaultResamplingMethod"),
    })

    # 2) Identify point value directly from service
    identify_url = f"{DEMNAS_SERVICE}/identify"
    params = {
        "geometry": f"{POINT_X},{POINT_Y}",
        "geometryType": "esriGeometryPoint",
        "sr": "4326",
        "returnGeometry": "false",
        "returnCatalogItems": "true",
        "f": "json",
    }
    r = session.get(identify_url, params=params, timeout=120)
    r.raise_for_status()
    print_json("IDENTIFY AT KURANJI", r.json())

    # 3) Compare export modes
    export_variant(session, "default", {})
    export_variant(session, "f32", {
        "pixelType": "F32",
        "interpolation": "RSP_NearestNeighbor",
    })
    export_variant(session, "f32_nodata", {
        "pixelType": "F32",
        "interpolation": "RSP_NearestNeighbor",
        "noData": "-9999",
        "noDataInterpretation": "esriNoDataMatchAny",
    })


if __name__ == "__main__":
    main()
