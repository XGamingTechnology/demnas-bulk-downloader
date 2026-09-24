#!/usr/bin/env python3
"""Build one clean downloadable QGIS package for Kuranji Stage 1.

The analysis workspace intentionally contains many diagnostic/experimental files.
This script copies only the final Stage-1 baseline layers and report tables into a
clean export folder, derives a hillshade and watershed-validation class raster,
creates a final outlet GeoJSON, and writes a ZIP archive ready to download.

The script does NOT modify source analysis products.

Output
------
data/export/kuranji_stage1_qgis/
data/export/KURANJI_TAHAP1_QGIS_PACKAGE.zip
"""

from __future__ import annotations

import json
import math
import shutil
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from shapely.geometry import shape, mapping

ROOT = Path(__file__).resolve().parent
PREP = ROOT / "data/work/kuranji/01_prepared"
SENS = ROOT / "data/work/kuranji/05_validation/conditioning_sensitivity"
CAL = ROOT / "data/work/kuranji/05_validation/breach100_stream_calibration"
DOCS = ROOT / "docs"
EXPORT_ROOT = ROOT / "data/export"
PKG = EXPORT_ROOT / "kuranji_stage1_qgis"
ZIP_OUT = EXPORT_ROOT / "KURANJI_TAHAP1_QGIS_PACKAGE.zip"

# Final products selected at the end of Stage 1.
SOURCES = {
    "raster/01_DEM_BREACH100_FINAL.tif": SENS / "BREACH100_DEM.tif",
    "raster/03_D8_POINTER_FINAL.tif": SENS / "BREACH100_D8_POINTER.tif",
    "raster/04_FLOW_ACCUMULATION_CELLS_FINAL.tif": SENS / "BREACH100_FLOW_ACCUM_CELLS.tif",
    "raster/05_STREAM_FINAL_6KM2.tif": CAL / "STREAM_BREACH100_6KM2.tif",
    "raster/06_WATERSHED_FINAL.tif": SENS / "BREACH100_WATERSHED.tif",
    "raster/07_REFERENCE_ONLY.tif": SENS / "BREACH100_REF_ONLY.tif",
    "raster/08_MODEL_ONLY.tif": SENS / "BREACH100_MODEL_ONLY.tif",
    "vector/DAS_KURANJI_REFERENCE.geojson": PREP / "DAS_KURANJI_UTM47S.geojson",
    "vector/SUNGAI_RBI_REFERENCE.geojson": PREP / "SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson",
    "vector/RESIDUAL_COMPONENTS.geojson": SENS / "BREACH_RESIDUAL_COMPONENTS.geojson",
    "table/stream_threshold_calibration.csv": CAL / "breach100_stream_threshold_calibration.csv",
    "qc/breach_sensitivity.json": SENS / "breach_sensitivity.json",
    "qc/breach_residual_analysis.json": SENS / "breach_residual_analysis.json",
    "qc/stream_threshold_calibration.json": CAL / "breach100_stream_threshold_calibration.json",
    "docs/KURANJI_LAPORAN_TAHAP_1_BASELINE_HIDROLOGI.md": DOCS / "KURANJI_LAPORAN_TAHAP_1_BASELINE_HIDROLOGI.md",
    "docs/KURANJI_METODE_TEKNIS_HIDROLOGI_BASELINE.md": DOCS / "KURANJI_METODE_TEKNIS_HIDROLOGI_BASELINE.md",
    "docs/KURANJI_ROADMAP_DELIVERABLE_LAPORAN.md": DOCS / "KURANJI_ROADMAP_DELIVERABLE_LAPORAN.md",
}


def load_geojson(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def reset_package():
    if PKG.exists():
        shutil.rmtree(PKG)
    PKG.mkdir(parents=True, exist_ok=True)
    if ZIP_OUT.exists():
        ZIP_OUT.unlink()


def copy_required_files():
    missing = []
    for rel, src in SOURCES.items():
        if not src.exists():
            missing.append(str(src))
            continue
        dst = PKG / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    if missing:
        raise FileNotFoundError("Required Stage-1 outputs are missing:\n- " + "\n- ".join(missing))


def make_hillshade():
    src_path = SENS / "BREACH100_DEM.tif"
    out_path = PKG / "raster/02_HILLSHADE_BREACH100.tif"

    with rasterio.open(src_path) as ds:
        z = ds.read(1).astype("float64")
        valid = np.isfinite(z)
        if ds.nodata is not None and np.isfinite(ds.nodata):
            valid &= ~np.isclose(z, ds.nodata)

        # Preserve nodata while avoiding extreme gradient artefacts at the mask edge.
        work = z.copy()
        if np.any(valid):
            fill_value = float(np.nanmedian(z[valid]))
            work[~valid] = fill_value

        xres, yres = abs(ds.res[0]), abs(ds.res[1])
        dz_dy, dz_dx = np.gradient(work, yres, xres)
        slope = np.arctan(np.hypot(dz_dx, dz_dy))
        aspect = np.arctan2(-dz_dx, dz_dy)

        azimuth = math.radians(315.0)
        altitude = math.radians(45.0)
        shaded = (
            np.sin(altitude) * np.cos(slope)
            + np.cos(altitude) * np.sin(slope) * np.cos(azimuth - aspect)
        )
        hs = np.clip((shaded + 1.0) / 2.0 * 255.0, 0, 255).astype("uint8")
        hs[~valid] = 0

        profile = ds.profile.copy()
        profile.update(
            driver="GTiff",
            dtype="uint8",
            count=1,
            nodata=0,
            compress="DEFLATE",
            tiled=True,
            blockxsize=512,
            blockysize=512,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(out_path, "w", **profile) as out:
            out.write(hs, 1)
            out.update_tags(
                DERIVATION="Simple analytical hillshade from BREACH100 DEM",
                AZIMUTH_DEGREES="315",
                ALTITUDE_DEGREES="45",
            )


def watershed_validation_class():
    wat_path = SENS / "BREACH100_WATERSHED.tif"
    das_path = PREP / "DAS_KURANJI_UTM47S.geojson"
    out_path = PKG / "raster/09_WATERSHED_VALIDATION_CLASS.tif"

    das_fc = load_geojson(das_path)
    das_geoms = [shape(ft["geometry"]) for ft in das_fc.get("features", []) if ft.get("geometry")]
    if not das_geoms:
        raise RuntimeError("Reference DAS geometry missing")

    with rasterio.open(wat_path) as ds:
        a = ds.read(1).astype("float64", copy=False)
        model = np.isfinite(a) & (a > 0)
        if ds.nodata is not None and np.isfinite(ds.nodata):
            model &= ~np.isclose(a, ds.nodata)

        ref = rasterize(
            [(g, 1) for g in das_geoms],
            out_shape=(ds.height, ds.width),
            transform=ds.transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)

        # 0 background; 1 intersection; 2 reference-only; 3 model-only.
        cls = np.zeros((ds.height, ds.width), dtype="uint8")
        cls[ref & model] = 1
        cls[ref & ~model] = 2
        cls[~ref & model] = 3

        profile = ds.profile.copy()
        profile.update(
            driver="GTiff",
            dtype="uint8",
            count=1,
            nodata=0,
            compress="DEFLATE",
            tiled=True,
            blockxsize=512,
            blockysize=512,
        )
        with rasterio.open(out_path, "w", **profile) as out:
            out.write(cls, 1)
            out.update_tags(
                CLASS_1="intersection",
                CLASS_2="reference_only",
                CLASS_3="model_only",
            )


def make_outlet_geojson():
    pour = SENS / "BREACH100_POUR_POINT.tif"
    out_path = PKG / "vector/OUTLET_FINAL.geojson"
    with rasterio.open(pour) as ds:
        a = ds.read(1)
        rr, cc = np.where(a > 0)
        if len(rr) != 1:
            raise RuntimeError(f"Expected one final pour point, found {len(rr)}")
        r, c = int(rr[0]), int(cc[0])
        x, y = rasterio.transform.xy(ds.transform, r, c, offset="center")
        fc = {
            "type": "FeatureCollection",
            "name": "kuranji_final_outlet_breach100",
            "crs": {"type": "name", "properties": {"name": str(ds.crs)}},
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [float(x), float(y)]},
                    "properties": {
                        "name": "Final outlet",
                        "conditioning": "BreachDepressionsLeastCost 100 cells",
                        "stream_threshold_km2": 6.0,
                    },
                }
            ],
        }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)


def copy_optional_admin():
    """Copy likely local admin files if they are present in ignored data folders."""
    patterns = [
        "**/*Kecamatan*.shp",
        "**/*KECAMATAN*.shp",
        "**/*kecamatan*.shp",
        "**/*Kelurahan*.shp",
        "**/*KELURAHAN*.shp",
        "**/*kelurahan*.shp",
        "**/*Kecamatan*.geojson",
        "**/*kelurahan*.geojson",
        "**/*Pauh*.gpkg",
        "**/*Kuranji*.gpkg",
    ]
    found = []
    seen = set()
    data_root = ROOT / "data"
    for pattern in patterns:
        for p in data_root.glob(pattern):
            if not p.is_file() or PKG in p.parents or p in seen:
                continue
            seen.add(p)
            found.append(p)

    admin_dir = PKG / "vector/admin_optional"
    if not found:
        return []
    admin_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for p in found:
        if p.suffix.lower() == ".shp":
            stem = p.with_suffix("")
            for sidecar in p.parent.glob(stem.name + ".*"):
                if sidecar.is_file():
                    dst = admin_dir / sidecar.name
                    shutil.copy2(sidecar, dst)
                    copied.append(str(dst.relative_to(PKG)))
        else:
            dst = admin_dir / p.name
            shutil.copy2(p, dst)
            copied.append(str(dst.relative_to(PKG)))
    return sorted(set(copied))


def write_readme(optional_admin):
    text = f"""# KURANJI STAGE 1 QGIS PACKAGE

This package contains the final hydrologic baseline selected at the end of Stage 1.

Final method
- CRS: EPSG:32747 (WGS 84 / UTM zone 47S)
- Conditioning: BreachDepressionsLeastCost
- Search distance: 100 cells (~833 m)
- min_dist: True
- fill: True
- Routing: D8
- Final stream threshold: 6 km2
- Final modeled stream length: 81.00 km
- RBI reference stream length: 79.813 km
- Watershed area: 212.125 km2
- Reference DAS raster area: 224.694 km2
- IoU: 0.9161
- Dice: 0.9562

Raster files
01_DEM_BREACH100_FINAL.tif            Final conditioned DEM
02_HILLSHADE_BREACH100.tif            Hillshade for cartographic display
03_D8_POINTER_FINAL.tif                D8 flow direction pointer
04_FLOW_ACCUMULATION_CELLS_FINAL.tif   D8 flow accumulation in cells
05_STREAM_FINAL_6KM2.tif               Final stream raster (6 km2 threshold)
06_WATERSHED_FINAL.tif                 Final modeled watershed
07_REFERENCE_ONLY.tif                  Reference DAS area absent from model
08_MODEL_ONLY.tif                      Model watershed area outside reference DAS
09_WATERSHED_VALIDATION_CLASS.tif      1=intersection, 2=reference-only, 3=model-only

Vector files
DAS_KURANJI_REFERENCE.geojson          Reference DAS
SUNGAI_RBI_REFERENCE.geojson           RBI river reference
OUTLET_FINAL.geojson                    Final pour point/outlet
RESIDUAL_COMPONENTS.geojson             Residual component centroids/attributes

Table / QC
stream_threshold_calibration.csv        Report-ready stream calibration table
qc/*.json                               Validation and sensitivity audit outputs

Recommended Stage-1 report maps
1. Study location
2. DEM + hillshade
3. Flow accumulation
4. Final 6 km2 stream network vs RBI
5. Modeled watershed vs reference DAS
6. Residual mismatch

Optional local administration copied automatically:
{chr(10).join('- ' + x for x in optional_admin) if optional_admin else '- None detected automatically. Add the Pauh/Kuranji kelurahan layer manually if needed.'}

Do not use diagnostic experiment rasters from other folders for the final report unless a method appendix specifically requires them.
"""
    with (PKG / "README_QGIS_PACKAGE.md").open("w", encoding="utf-8") as f:
        f.write(text)


def zip_package():
    with zipfile.ZipFile(ZIP_OUT, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for p in sorted(PKG.rglob("*")):
            if p.is_file():
                arc = Path(PKG.name) / p.relative_to(PKG)
                zf.write(p, arcname=str(arc))


def main():
    print("=== PACKAGE KURANJI STAGE 1 FOR QGIS ===")
    reset_package()
    copy_required_files()
    print("[1/6] Final files copied")
    make_hillshade()
    print("[2/6] Hillshade created")
    watershed_validation_class()
    print("[3/6] Watershed validation class raster created")
    make_outlet_geojson()
    print("[4/6] Final outlet GeoJSON created")
    optional_admin = copy_optional_admin()
    print(f"[5/6] Optional admin files detected: {len(optional_admin)}")
    write_readme(optional_admin)
    zip_package()
    print("[6/6] ZIP created")
    print("\nFolder :", PKG)
    print("ZIP    :", ZIP_OUT)
    print(f"Size   : {ZIP_OUT.stat().st_size / 1024 / 1024:.2f} MB")
    print("\nDownload this ZIP to your computer/iPad and extract it before opening in QGIS.")


if __name__ == "__main__":
    main()
