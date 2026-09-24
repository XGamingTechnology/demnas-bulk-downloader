#!/usr/bin/env python3
"""Sensitivity test: FillDepressions baseline vs least-cost breaching for DAS Kuranji.

Motivation
----------
The baseline FillDepressions routing produces a main contributing area of ~177 km2
inside the official ~224.7 km2 DAS and a stable secondary partition of ~32 km2 whose
6 km2 stream network has no overlap within 100 m of RBI. This script tests whether
that mismatch persists when the DEM is conditioned with WhiteboxTools
BreachDepressionsLeastCost instead of full filling.

Two breach search distances are tested:
- 100 cells (~0.83 km): moderate sensitivity test
- 250 cells (~2.08 km): deliberately aggressive sensitivity test

Both scenarios use --min_dist and --fill so unresolved depressions are filled after
least-cost breaching and D8 routing remains continuous. The original baseline files
are not modified.

Outputs
-------
data/work/kuranji/05_validation/conditioning_sensitivity/
  BREACH100_DEM.tif
  BREACH100_D8_POINTER.tif
  BREACH100_FLOW_ACCUM_CELLS.tif
  BREACH100_POUR_POINT.tif
  BREACH100_WATERSHED.tif
  BREACH250_DEM.tif
  BREACH250_D8_POINTER.tif
  BREACH250_FLOW_ACCUM_CELLS.tif
  BREACH250_POUR_POINT.tif
  BREACH250_WATERSHED.tif
  breach_sensitivity.json
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import distance_transform_edt
from shapely.geometry import shape
from whitebox import WhiteboxTools

ROOT = Path(__file__).resolve().parent
PREP = ROOT / "data/work/kuranji/01_prepared"
HYD = ROOT / "data/work/kuranji/02_hydrology"
WAT = ROOT / "data/work/kuranji/03_watershed"
OUT = ROOT / "data/work/kuranji/05_validation/conditioning_sensitivity"
OUT.mkdir(parents=True, exist_ok=True)

WBT_INPUT = HYD / "00_DEM_WBT_INPUT.tif"
BASE_FILLED = HYD / "01_DEM_FILLED.tif"
BASE_POINTER = HYD / "02_D8_POINTER.tif"
BASE_ACC = HYD / "03_FLOW_ACCUM_CELLS.tif"
DAS = PREP / "DAS_KURANJI_UTM47S.geojson"
RBI = PREP / "SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson"
SECONDARY_MASK = WAT / "SECONDARY_PARTITION_100M_RANK2.tif"
REPORT = OUT / "breach_sensitivity.json"

SCENARIOS = {
    "breach100": 100,
    "breach250": 250,
}
STREAM_THRESHOLD_KM2 = 6.0
TOLERANCES_M = [25.0, 50.0, 100.0]


def load_geoms(path: Path):
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    geoms = [shape(ft["geometry"]) for ft in data.get("features", []) if ft.get("geometry")]
    if not geoms:
        raise RuntimeError(f"No geometries: {path}")
    return geoms


def valid_mask(ds, arr):
    m = np.isfinite(arr)
    if ds.nodata is not None and np.isfinite(ds.nodata):
        m &= ~np.isclose(arr, ds.nodata)
    return m


def require_success(name: str, rc, path: Path):
    if rc not in (0, None):
        raise RuntimeError(f"{name} failed; rc={rc}")
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"{name} output missing: {path}")


def write_pour(path: Path, row: int, col: int, ref):
    arr = np.zeros((ref.height, ref.width), dtype="int32")
    arr[row, col] = 1
    profile = ref.profile.copy()
    for key in ("compress", "predictor", "tiled", "blockxsize", "blockysize", "interleave"):
        profile.pop(key, None)
    profile.update(driver="GTiff", dtype="int32", count=1, nodata=0, BIGTIFF="IF_SAFER")
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)


def fraction_near(source_mask, distances, tol):
    n = int(np.count_nonzero(source_mask))
    if n == 0:
        return 0.0
    return float(np.count_nonzero(source_mask & (distances <= tol)) / n)


def harmonic(a, b):
    return 0.0 if a + b == 0 else float(2.0 * a * b / (a + b))


def change_stats(original_ds, conditioned_ds, das_mask):
    a = original_ds.read(1).astype("float64", copy=False)
    b = conditioned_ds.read(1).astype("float64", copy=False)
    valid = das_mask & valid_mask(original_ds, a) & valid_mask(conditioned_ds, b)
    d = b[valid] - a[valid]
    return {
        "compared_cells_inside_das": int(d.size),
        "changed_gt_1e_6m": int(np.count_nonzero(np.abs(d) > 1e-6)),
        "lowered_gt_0_001m": int(np.count_nonzero(d < -0.001)),
        "raised_gt_0_001m": int(np.count_nonzero(d > 0.001)),
        "mean_delta_m": float(np.mean(d)),
        "mean_abs_delta_m": float(np.mean(np.abs(d))),
        "min_delta_m": float(np.min(d)),
        "max_delta_m": float(np.max(d)),
        "p01_delta_m": float(np.percentile(d, 1)),
        "p99_delta_m": float(np.percentile(d, 99)),
    }


def run_scenario(wbt, name, dist_cells, das_mask, rbi_mask, secondary_mask, ref_area_cells, cell_area, sampling):
    prefix = name.upper()
    dem_out = OUT / f"{prefix}_DEM.tif"
    ptr_out = OUT / f"{prefix}_D8_POINTER.tif"
    acc_out = OUT / f"{prefix}_FLOW_ACCUM_CELLS.tif"
    pour_out = OUT / f"{prefix}_POUR_POINT.tif"
    wat_out = OUT / f"{prefix}_WATERSHED.tif"

    for p in [dem_out, ptr_out, acc_out, pour_out, wat_out]:
        if p.exists():
            p.unlink()

    print(f"\n=== {name}: BreachDepressionsLeastCost dist={dist_cells} cells ===")
    args = [
        f"--dem={WBT_INPUT}",
        f"--output={dem_out}",
        f"--dist={dist_cells}",
        "--min_dist",
        "--fill",
    ]
    rc = wbt.run_tool("BreachDepressionsLeastCost", args)
    require_success(f"{name} BreachDepressionsLeastCost", rc, dem_out)

    rc = wbt.d8_pointer(dem=str(dem_out), output=str(ptr_out), esri_pntr=False)
    require_success(f"{name} D8Pointer", rc, ptr_out)

    rc = wbt.d8_flow_accumulation(
        i=str(ptr_out), output=str(acc_out), out_type="cells",
        log=False, clip=False, pntr=True, esri_pntr=False,
    )
    require_success(f"{name} D8FlowAccumulation", rc, acc_out)

    with rasterio.open(acc_out) as ads, rasterio.open(WBT_INPUT) as ods, rasterio.open(dem_out) as cds:
        accum = ads.read(1).astype("float64", copy=False)
        valid = das_mask & valid_mask(ads, accum)
        rr, cc = np.where(valid)
        idx = int(np.argmax(accum[rr, cc]))
        outlet_r, outlet_c = int(rr[idx]), int(cc[idx])
        outlet_cells = float(accum[outlet_r, outlet_c])
        outlet_area = float(outlet_cells * cell_area / 1_000_000.0)
        outlet_x, outlet_y = rasterio.transform.xy(ads.transform, outlet_r, outlet_c, offset="center")

        dist_to_rbi = distance_transform_edt(~rbi_mask, sampling=sampling)
        outlet_rbi_dist = float(dist_to_rbi[outlet_r, outlet_c])

        min_cells = int(math.ceil(STREAM_THRESHOLD_KM2 * 1_000_000.0 / cell_area))
        stream = valid & (accum >= min_cells)
        dist_to_model = distance_transform_edt(~stream, sampling=sampling)
        stream_metrics = {}
        for tol in TOLERANCES_M:
            p = fraction_near(stream, dist_to_rbi, tol)
            r = fraction_near(rbi_mask & das_mask, dist_to_model, tol)
            stream_metrics[f"{int(tol)}m"] = {
                "model_near_rbi_fraction": p,
                "rbi_near_model_fraction": r,
                "harmonic_f1": harmonic(p, r),
            }

        sec_valid = valid & secondary_mask
        sec_stream = sec_valid & (accum >= min_cells)
        secondary_metrics = {
            "zone_cells": int(np.count_nonzero(secondary_mask)),
            "stream_cells": int(np.count_nonzero(sec_stream)),
            "max_accum_area_km2_inside_baseline_secondary_zone": (
                float(np.max(accum[sec_valid]) * cell_area / 1_000_000.0)
                if np.any(sec_valid) else 0.0
            ),
            "stream_near_rbi": {},
        }
        for tol in TOLERANCES_M:
            secondary_metrics["stream_near_rbi"][f"{int(tol)}m"] = fraction_near(sec_stream, dist_to_rbi, tol)

        conditioning = change_stats(ods, cds, das_mask)
        write_pour(pour_out, outlet_r, outlet_c, ads)

    rc = wbt.watershed(
        d8_pntr=str(ptr_out), pour_pts=str(pour_out), output=str(wat_out), esri_pntr=False,
    )
    require_success(f"{name} Watershed", rc, wat_out)

    with rasterio.open(wat_out) as wds:
        wat = wds.read(1).astype("float64", copy=False)
        model = valid_mask(wds, wat) & (wat > 0)
        inter = int(np.count_nonzero(model & das_mask))
        union = int(np.count_nonzero(model | das_mask))
        model_n = int(np.count_nonzero(model))
        iou = float(inter / union) if union else 0.0
        dice = float(2 * inter / (model_n + ref_area_cells)) if (model_n + ref_area_cells) else 0.0

    return {
        "breach_dist_cells": dist_cells,
        "breach_dist_m_approx": float(dist_cells * math.sqrt(cell_area)),
        "conditioning_change_inside_das": conditioning,
        "max_accumulation_outlet_inside_reference_das": {
            "row": outlet_r,
            "col": outlet_c,
            "x": float(outlet_x),
            "y": float(outlet_y),
            "accum_cells": outlet_cells,
            "catchment_area_km2": outlet_area,
            "distance_to_rbi_m": outlet_rbi_dist,
        },
        "stream_6km2_vs_rbi": stream_metrics,
        "baseline_secondary_zone_response": secondary_metrics,
        "watershed_validation": {
            "reference_area_km2": float(ref_area_cells * cell_area / 1_000_000.0),
            "model_area_km2": float(model_n * cell_area / 1_000_000.0),
            "intersection_area_km2": float(inter * cell_area / 1_000_000.0),
            "union_area_km2": float(union * cell_area / 1_000_000.0),
            "iou": iou,
            "dice": dice,
        },
        "outputs": {
            "conditioned_dem": str(dem_out.relative_to(ROOT)),
            "pointer": str(ptr_out.relative_to(ROOT)),
            "flow_accum_cells": str(acc_out.relative_to(ROOT)),
            "pour_point": str(pour_out.relative_to(ROOT)),
            "watershed": str(wat_out.relative_to(ROOT)),
        },
    }


def main():
    for p in [WBT_INPUT, BASE_FILLED, BASE_POINTER, BASE_ACC, DAS, RBI, SECONDARY_MASK]:
        if not p.exists():
            raise FileNotFoundError(p)

    das_geoms = load_geoms(DAS)
    rbi_geoms = load_geoms(RBI)

    with rasterio.open(WBT_INPUT) as ref, rasterio.open(SECONDARY_MASK) as sds:
        rx, ry = abs(ref.res[0]), abs(ref.res[1])
        cell_area = rx * ry
        sampling = (ry, rx)
        das_mask = rasterize(
            [(g, 1) for g in das_geoms], out_shape=(ref.height, ref.width),
            transform=ref.transform, fill=0, all_touched=False, dtype="uint8"
        ).astype(bool)
        rbi_mask = rasterize(
            [(g, 1) for g in rbi_geoms], out_shape=(ref.height, ref.width),
            transform=ref.transform, fill=0, all_touched=True, dtype="uint8"
        ).astype(bool)
        if sds.width != ref.width or sds.height != ref.height or sds.crs != ref.crs or not sds.transform.almost_equals(ref.transform):
            raise RuntimeError("Secondary partition mask grid differs")
        secondary_mask = sds.read(1) > 0
        ref_cells = int(np.count_nonzero(das_mask))

    wbt = WhiteboxTools()
    wbt.set_verbose_mode(True)
    wbt.set_compress_rasters(False)

    results = {}
    for name, dist in SCENARIOS.items():
        results[name] = run_scenario(
            wbt, name, dist, das_mask, rbi_mask, secondary_mask,
            ref_cells, cell_area, sampling,
        )

    report = {
        "purpose": (
            "Independent conditioning sensitivity test before any RBI stream burning/enforcement. "
            "If the ~177 km2 main outlet and ~32 km2 secondary behaviour persist under least-cost breaching, "
            "the DEM/reference mismatch is robust to depression-removal method."
        ),
        "grid": {
            "crs": "EPSG:32747",
            "resolution_m": [rx, ry],
            "cell_area_m2": cell_area,
        },
        "reference_das_area_km2": float(ref_cells * cell_area / 1_000_000.0),
        "stream_threshold_km2": STREAM_THRESHOLD_KM2,
        "scenarios": results,
    }

    with REPORT.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n=== BREACH SENSITIVITY SUMMARY ===")
    print(f"Reference DAS: {report['reference_das_area_km2']:.3f} km2")
    for name, row in results.items():
        o = row["max_accumulation_outlet_inside_reference_das"]
        w = row["watershed_validation"]
        s = row["stream_6km2_vs_rbi"]["100m"]
        sec = row["baseline_secondary_zone_response"]
        ch = row["conditioning_change_inside_das"]
        print(f"\n{name} (dist={row['breach_dist_cells']} cells ~{row['breach_dist_m_approx']:.0f} m)")
        print(f"  outlet accum area : {o['catchment_area_km2']:.3f} km2")
        print(f"  outlet RBI dist   : {o['distance_to_rbi_m']:.1f} m")
        print(f"  watershed area    : {w['model_area_km2']:.3f} km2")
        print(f"  IoU / Dice        : {w['iou']:.4f} / {w['dice']:.4f}")
        print(f"  stream 100m P/R/F1: {s['model_near_rbi_fraction']:.3f} / {s['rbi_near_model_fraction']:.3f} / {s['harmonic_f1']:.3f}")
        print(f"  secondary max CA  : {sec['max_accum_area_km2_inside_baseline_secondary_zone']:.3f} km2")
        print(f"  secondary stream <=100m RBI: {sec['stream_near_rbi']['100m']:.3f}")
        print(f"  DEM changed cells : {ch['changed_gt_1e_6m']:,}; mean abs delta={ch['mean_abs_delta_m']:.4f} m")
        print(f"  max lowering/raising: {ch['min_delta_m']:.3f} / {ch['max_delta_m']:.3f} m")
    print("\nJSON:", REPORT)


if __name__ == "__main__":
    main()
