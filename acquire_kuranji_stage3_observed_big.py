#!/usr/bin/env python3
"""Acquire official BIG/BRIN 2025 flood extent candidates for Kuranji Stage 3.

This script does NOT calibrate or validate the GFI model yet. It performs a source
acquisition + preflight/QC step so we can decide which official observed layer is
methodologically suitable as the independent validation reference.

Official service:
  https://geoservices.big.go.id/gis/rest/services/STIG/2025_BANJIRSUMATERA/MapServer

Candidate layers:
  3 = Data BRIN - Area terdampak banjir
  5 = Data per 8 Desember

Outputs:
  data/work/kuranji/15_stage3_validation/source_big/
    service_metadata.json
    layer3_metadata.json
    layer5_metadata.json
    layer3_raw_bbox.geojson
    layer5_raw_bbox.geojson
    layer3_kuranji_clip_utm47s.geojson
    layer5_kuranji_clip_utm47s.geojson
    layer3_kuranji_aligned.tif
    layer5_kuranji_aligned.tif
    source_preflight_qc.json
    source_attributes_layer3.csv
    source_attributes_layer5.csv

The two candidate sources are kept separate. Do not merge them until provenance,
dates and spatial behaviour have been reviewed.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import rasterio
import requests
from pyproj import CRS, Transformer
from rasterio.features import rasterize
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform, unary_union

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data/work/kuranji/15_stage3_validation/source_big"
OUT.mkdir(parents=True, exist_ok=True)

SERVICE = "https://geoservices.big.go.id/gis/rest/services/STIG/2025_BANJIRSUMATERA/MapServer"
DAS_PATH = ROOT / "data/work/kuranji/01_prepared/DAS_KURANJI_UTM47S.geojson"
REF_RASTER = ROOT / "data/work/kuranji/14_stage2_admin_final/raster/P175_HAZARD_CLASS.tif"
TARGET_CRS = CRS.from_epsg(32747)
WGS84 = CRS.from_epsg(4326)


def get_json(url: str, params=None):
    r = requests.get(url, params=params, timeout=120)
    r.raise_for_status()
    return r.json()


def read_geojson(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_das():
    fc = read_geojson(DAS_PATH)
    geoms = [shape(f["geometry"]) for f in fc.get("features", []) if f.get("geometry")]
    if not geoms:
        raise RuntimeError("No DAS geometry")
    return unary_union(geoms)


def query_geojson(layer_id: int, bbox_wgs84):
    xmin, ymin, xmax, ymax = bbox_wgs84
    params = {
        "where": "1=1",
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    url = f"{SERVICE}/{layer_id}/query"
    r = requests.get(url, params=params, timeout=180)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"ArcGIS query error layer {layer_id}: {data['error']}")
    return data, r.url


def save_geojson(path: Path, features, crs_name="EPSG:32747"):
    fc = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": crs_name}},
        "features": features,
    }
    path.write_text(json.dumps(fc, ensure_ascii=False, indent=2), encoding="utf-8")


def flatten_attrs(features):
    keys = []
    seen = set()
    for ft in features:
        for k in (ft.get("properties") or {}).keys():
            if k not in seen:
                seen.add(k)
                keys.append(k)
    return keys


def write_attrs(path: Path, features):
    keys = flatten_attrs(features)
    if not keys:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["feature_id"] + keys)
        w.writeheader()
        for i, ft in enumerate(features, 1):
            row = {"feature_id": i}
            row.update(ft.get("properties") or {})
            w.writerow(row)


def clip_reproject(raw_fc, das_utm):
    tf = Transformer.from_crs(WGS84, TARGET_CRS, always_xy=True).transform
    out = []
    area_sum = 0.0
    for i, ft in enumerate(raw_fc.get("features", []), 1):
        if not ft.get("geometry"):
            continue
        g = shape(ft["geometry"])
        if g.is_empty:
            continue
        g = shp_transform(tf, g)
        if not g.intersects(das_utm):
            continue
        inter = g.intersection(das_utm)
        if inter.is_empty or inter.area <= 0:
            continue
        p = dict(ft.get("properties") or {})
        p["_source_feature_id"] = i
        p["_clip_area_ha"] = inter.area / 10000.0
        p["_clip_area_km2"] = inter.area / 1e6
        area_sum += inter.area
        out.append({"type": "Feature", "geometry": mapping(inter), "properties": p})
    return out, area_sum


def union_area(features):
    gs = [shape(f["geometry"]) for f in features if f.get("geometry")]
    if not gs:
        return None, 0.0
    u = unary_union(gs)
    return u, u.area


def rasterize_candidate(features, out_path: Path):
    with rasterio.open(REF_RASTER) as ref:
        arr = np.zeros((ref.height, ref.width), dtype="uint8")
        shapes = [(shape(f["geometry"]), 1) for f in features if f.get("geometry")]
        if shapes:
            arr = rasterize(
                shapes,
                out_shape=(ref.height, ref.width),
                transform=ref.transform,
                fill=0,
                default_value=1,
                all_touched=False,
                dtype="uint8",
            )
        profile = ref.profile.copy()
        profile.update(dtype="uint8", count=1, nodata=0, compress="DEFLATE")
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(arr, 1)
        return {
            "cells": int(np.count_nonzero(arr == 1)),
            "area_km2": float(np.count_nonzero(arr == 1) * abs(ref.res[0] * ref.res[1]) / 1e6),
            "crs": str(ref.crs),
            "shape": [ref.height, ref.width],
        }


def unique_values(features, key):
    vals = []
    seen = set()
    for ft in features:
        v = (ft.get("properties") or {}).get(key)
        if v is None:
            continue
        s = str(v).strip()
        if s and s not in seen:
            seen.add(s); vals.append(s)
    return vals


def main():
    for p in [DAS_PATH, REF_RASTER]:
        if not p.exists():
            raise FileNotFoundError(p)

    das = load_das()
    tf_back = Transformer.from_crs(TARGET_CRS, WGS84, always_xy=True).transform
    das_wgs = shp_transform(tf_back, das)
    bbox = das_wgs.bounds

    print("=== STAGE 3 SOURCE ACQUISITION — BIG 2025 ===")
    print("DAS WGS84 bbox:", ", ".join(f"{x:.8f}" for x in bbox))

    service_meta = get_json(SERVICE, {"f": "pjson"})
    layer3_meta = get_json(f"{SERVICE}/3", {"f": "pjson"})
    layer5_meta = get_json(f"{SERVICE}/5", {"f": "pjson"})
    (OUT / "service_metadata.json").write_text(json.dumps(service_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "layer3_metadata.json").write_text(json.dumps(layer3_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "layer5_metadata.json").write_text(json.dumps(layer5_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    results = {}
    for lid, label in [(3, "layer3"), (5, "layer5")]:
        print(f"\nDownloading BIG layer {lid} inside DAS bbox...")
        fc, query_url = query_geojson(lid, bbox)
        raw_features = fc.get("features", [])
        raw_path = OUT / f"{label}_raw_bbox.geojson"
        raw_path.write_text(json.dumps(fc, ensure_ascii=False, indent=2), encoding="utf-8")
        write_attrs(OUT / f"source_attributes_{label}.csv", raw_features)

        clipped, summed_area = clip_reproject(fc, das)
        clip_path = OUT / f"{label}_kuranji_clip_utm47s.geojson"
        save_geojson(clip_path, clipped)
        u, uarea = union_area(clipped)
        rast = rasterize_candidate(clipped, OUT / f"{label}_kuranji_aligned.tif")

        results[label] = {
            "layer_id": lid,
            "layer_name": (layer3_meta if lid == 3 else layer5_meta).get("name"),
            "query_url": query_url,
            "raw_features_in_bbox": len(raw_features),
            "clipped_features_intersect_DAS": len(clipped),
            "summed_clip_area_km2": summed_area / 1e6,
            "union_clip_area_km2": uarea / 1e6,
            "aligned_raster": rast,
            "attribute_keys": flatten_attrs(raw_features),
            "tgl_citra_values": unique_values(raw_features, "Tgl_citra"),
            "sumber_data_values": unique_values(raw_features, "Sumber_dat"),
            "provinsi_values": unique_values(raw_features, "Provinsi"),
            "kabupaten_values": unique_values(raw_features, "Kabupaten"),
            "layer_values": unique_values(raw_features, "layer"),
        }

        print(f"Raw features       : {len(raw_features)}")
        print(f"Intersect DAS      : {len(clipped)}")
        print(f"Union area in DAS  : {uarea/1e6:.4f} km2")
        print(f"Raster area        : {rast['area_km2']:.4f} km2")
        if results[label]["tgl_citra_values"]:
            print("Tgl_citra           :", results[label]["tgl_citra_values"])
        if results[label]["sumber_data_values"]:
            print("Sumber_dat          :", results[label]["sumber_data_values"])
        if results[label]["layer_values"]:
            print("layer values        :", results[label]["layer_values"])
        if results[label]["kabupaten_values"]:
            print("Kabupaten           :", results[label]["kabupaten_values"])

    # Cross-source overlap, diagnostic only.
    with rasterio.open(OUT / "layer3_kuranji_aligned.tif") as a, rasterio.open(OUT / "layer5_kuranji_aligned.tif") as b:
        x = a.read(1) == 1
        y = b.read(1) == 1
        tp = int(np.count_nonzero(x & y))
        union = int(np.count_nonzero(x | y))
        cell_area = abs(a.res[0] * a.res[1])
        cross = {
            "intersection_km2": tp * cell_area / 1e6,
            "union_km2": union * cell_area / 1e6,
            "jaccard": tp / union if union else None,
            "layer3_only_km2": int(np.count_nonzero(x & ~y)) * cell_area / 1e6,
            "layer5_only_km2": int(np.count_nonzero(y & ~x)) * cell_area / 1e6,
        }

    qc = {
        "service": SERVICE,
        "service_description": service_meta.get("serviceDescription"),
        "copyrightText": service_meta.get("copyrightText"),
        "DAS_bbox_wgs84": list(bbox),
        "DAS_area_km2": das.area / 1e6,
        "candidates": results,
        "cross_source_overlap": cross,
        "decision_status": "PRE-FLIGHT ONLY — review provenance/date/coverage before selecting observed validation reference",
    }
    (OUT / "source_preflight_qc.json").write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== CROSS-SOURCE DIAGNOSTIC ===")
    print(f"Intersection       : {cross['intersection_km2']:.4f} km2")
    print(f"Union              : {cross['union_km2']:.4f} km2")
    print(f"Jaccard            : {cross['jaccard'] if cross['jaccard'] is not None else 'NA'}")
    print(f"Layer 3 only       : {cross['layer3_only_km2']:.4f} km2")
    print(f"Layer 5 only       : {cross['layer5_only_km2']:.4f} km2")
    print("\nOutput:", OUT)
    print("NEXT: review the printed dates/sources/coverage before running model validation.")


if __name__ == "__main__":
    main()
