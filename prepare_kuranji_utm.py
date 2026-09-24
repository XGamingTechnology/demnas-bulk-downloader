#!/usr/bin/env python3
import json
from pathlib import Path
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
from shapely.geometry import shape, mapping
from shapely.ops import unary_union, transform as shp_transform
from pyproj import Transformer

RAW = Path("data/output/kuranji")
INPUT = Path("data/input/kuranji")
OUT = Path("data/work/kuranji/01_prepared")
OUT.mkdir(parents=True, exist_ok=True)

DEM_RAW = RAW / "DEMNAS_KURANJI_BUFFER3KM_WGS84.tif"
DAS_RAW = INPUT / "DAS_KURANJI_WGS84.geojson"
RIVER_RAW = RAW / "SUNGAI_RBI_DAS_KURANJI.geojson"

DEM_UTM = OUT / "DEMNAS_KURANJI_BUFFER3KM_UTM47S.tif"
DEM_DAS_UTM = OUT / "DEMNAS_DAS_KURANJI_UTM47S.tif"
DAS_UTM_FILE = OUT / "DAS_KURANJI_UTM47S.geojson"
RIVER_UTM_FILE = OUT / "SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson"

DST_CRS = "EPSG:32747"
NODATA = -9999.0

def load_union(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return unary_union([shape(x["geometry"]) for x in data["features"] if x.get("geometry")])

def save_geojson(features, path, epsg):
    fc = {"type":"FeatureCollection","name":path.stem,
          "crs":{"type":"name","properties":{"name":f"EPSG:{epsg}"}},
          "features":features}
    path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")

def stats(path):
    with rasterio.open(path) as ds:
        a = ds.read(1, masked=True).compressed()
        print("\nFILE:", path)
        print("CRS:", ds.crs, "SIZE:", ds.width, "x", ds.height, "RES:", ds.res)
        print("BOUNDS:", ds.bounds, "NODATA:", ds.nodata)
        if a.size:
            print("MIN/MEAN/MEDIAN/MAX:",
                  float(a.min()), float(a.mean()), float(np.median(a)), float(a.max()))
            print("P1/P99:", float(np.percentile(a,1)), float(np.percentile(a,99)))

das_wgs = load_union(DAS_RAW)
to_utm = Transformer.from_crs("EPSG:4326", DST_CRS, always_xy=True).transform
das_utm = shp_transform(to_utm, das_wgs)
print("DAS valid:", das_utm.is_valid)
print("DAS area km2:", das_utm.area/1_000_000)
print("DAS bounds:", das_utm.bounds)

save_geojson([{"type":"Feature",
               "properties":{"nama":"DAS Kuranji","luas_km2":das_utm.area/1_000_000},
               "geometry":mapping(das_utm)}], DAS_UTM_FILE, 32747)

with rasterio.open(DEM_RAW) as src:
    tr, width, height = calculate_default_transform(src.crs, DST_CRS, src.width, src.height, *src.bounds)
    profile = src.profile.copy()
    profile.update(crs=DST_CRS, transform=tr, width=width, height=height,
                   dtype="float32", nodata=NODATA, compress="DEFLATE",
                   predictor=3, tiled=True, BIGTIFF="IF_SAFER")
    with rasterio.open(DEM_UTM, "w", **profile) as dst:
        reproject(source=rasterio.band(src,1), destination=rasterio.band(dst,1),
                  src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                  dst_transform=tr, dst_crs=DST_CRS, dst_nodata=NODATA,
                  resampling=Resampling.bilinear, num_threads=2)

with rasterio.open(DEM_UTM) as src:
    clipped, ctr = mask(src, [mapping(das_utm)], crop=True, nodata=NODATA)
    profile = src.profile.copy()
    profile.update(height=clipped.shape[1], width=clipped.shape[2],
                   transform=ctr, nodata=NODATA, compress="DEFLATE")
    with rasterio.open(DEM_DAS_UTM, "w", **profile) as dst:
        dst.write(clipped)

with open(RIVER_RAW, encoding="utf-8") as f:
    rd = json.load(f)

rf = []
length = 0.0
for feat in rd["features"]:
    if not feat.get("geometry"):
        continue
    try:
        g = shp_transform(to_utm, shape(feat["geometry"]))
    except Exception:
        continue
    if g.is_empty:
        continue
    length += g.length
    rf.append({"type":"Feature","properties":feat.get("properties",{}),"geometry":mapping(g)})

save_geojson(rf, RIVER_UTM_FILE, 32747)
print("River features:", len(rf))
print("River length km:", length/1000)

stats(DEM_RAW)
stats(DEM_UTM)
stats(DEM_DAS_UTM)

print("\nOUTPUTS:")
print(DEM_UTM)
print(DEM_DAS_UTM)
print(DAS_UTM_FILE)
print(RIVER_UTM_FILE)
