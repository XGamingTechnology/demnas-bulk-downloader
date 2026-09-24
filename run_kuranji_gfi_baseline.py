#!/usr/bin/env python3
"""Compute Stage-2 baseline GFI for DAS Batang Kuranji.

Method basis
------------
- MODUL TEKNIS KRB BANJIR-2
- GFA / GeomorphicFloodIndex 2.0 active source-code logic
- Local drainage adaptation selected after Stage-2 preflight:
  minimum contributing area = 6 km2 on the BREACH100 D8 routing.

This script computes:
1. hydrologically connected drainage target for every DAS cell;
2. H = terrain elevation - connected drainage elevation;
3. Ariver = flow accumulation at the connected drainage cell;
4. hr = A_km2 ** n, with n=0.354429752;
5. GFI_raw = ln(hr / H);
6. GFI normalized to [-1, +1], matching the legacy GFA plugin;
7. a diagnostic manual flood-prone mask using normalized GFI > -0.53,
   followed by the plugin's 8-neighbour, >=8-pixel component cleanup.

The -0.53 mask is DIAGNOSTIC ONLY. It is not declared the final flood-prone
threshold unless independent calibration data are unavailable and the research
explicitly adopts the module/plugin manual default.

Routing uses the full buffered BREACH100 grid to preserve hydrologic connectivity.
Normalization and reported statistics are restricted to the official DAS mask,
matching the module's analysis-domain concept.

Outputs
-------
data/work/kuranji/08_gfi_baseline/
  01_CHANNEL_FAT_6KM2_FULL.tif
  02_H_CONNECTED_DRAINAGE_M.tif
  03_ARIVER_CELLS.tif
  04_ARIVER_KM2.tif
  05_HR_M.tif
  06_GFI_RAW.tif
  07_GFI_NORMALIZED.tif
  08_GFI_MANUAL_PRONE_M053.tif
  gfi_baseline_qc.json
  gfi_baseline_stats.csv
"""

from __future__ import annotations

import csv
import json
import math
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import label
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent
PREP = ROOT / "data/work/kuranji/01_prepared"
SENS = ROOT / "data/work/kuranji/05_validation/conditioning_sensitivity"
OUT = ROOT / "data/work/kuranji/08_gfi_baseline"
OUT.mkdir(parents=True, exist_ok=True)

DEM = SENS / "BREACH100_DEM.tif"
PTR = SENS / "BREACH100_D8_POINTER.tif"
ACC = SENS / "BREACH100_FLOW_ACCUM_CELLS.tif"
DAS = PREP / "DAS_KURANJI_UTM47S.geojson"

N_EXPONENT = 0.354429752
STREAM_THRESHOLD_KM2 = 6.0
MANUAL_GFI_NORM_THRESHOLD = -0.53
MIN_COMPONENT_PIXELS = 8
NODATA_F32 = -9999.0

WBT_D8 = {
    1: (-1, 1),
    2: (0, 1),
    4: (1, 1),
    8: (1, 0),
    16: (1, -1),
    32: (0, -1),
    64: (-1, -1),
    128: (-1, 0),
}
STRUCT8 = np.ones((3, 3), dtype=np.uint8)


def load_geojson(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_geoms(path: Path):
    fc = load_geojson(path)
    geoms = [shape(ft["geometry"]) for ft in fc.get("features", []) if ft.get("geometry")]
    if not geoms:
        raise RuntimeError(f"No geometry in {path}")
    return geoms


def write_raster(path: Path, arr: np.ndarray, ref, dtype: str, nodata):
    profile = ref.profile.copy()
    profile.update(
        driver="GTiff",
        dtype=dtype,
        count=1,
        nodata=nodata,
        compress="DEFLATE",
        tiled=True,
        blockxsize=512,
        blockysize=512,
    )
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr.astype(dtype), 1)


def stats(a: np.ndarray, mask: np.ndarray):
    x = a[mask & np.isfinite(a)]
    if x.size == 0:
        return {"count": 0}
    return {
        "count": int(x.size),
        "min": float(np.min(x)),
        "p01": float(np.percentile(x, 1)),
        "p05": float(np.percentile(x, 5)),
        "p25": float(np.percentile(x, 25)),
        "median": float(np.median(x)),
        "mean": float(np.mean(x)),
        "p75": float(np.percentile(x, 75)),
        "p95": float(np.percentile(x, 95)),
        "p99": float(np.percentile(x, 99)),
        "max": float(np.max(x)),
    }


def clean_components(mask: np.ndarray, min_pixels: int):
    lab, n = label(mask, structure=STRUCT8)
    counts = np.bincount(lab.ravel())
    keep_labels = np.where(counts >= min_pixels)[0]
    keep_labels = keep_labels[keep_labels != 0]
    cleaned = np.isin(lab, keep_labels)
    return cleaned, int(n), int(len(keep_labels)), counts


def resolve_connected_channel_targets(
    ptr: np.ndarray,
    channel: np.ndarray,
    valid: np.ndarray,
    request_mask: np.ndarray,
):
    """Return flat target index of first downstream channel for requested cells.

    Uses path compression. Intermediate cells in the full buffer are cached too,
    so repeated downstream traces are inexpensive after the first visit.

    Target values:
      >=0 : flat index of connected channel cell
      -1  : unresolved/not yet evaluated
      -2  : no valid downstream channel before leaving valid raster / bad pointer
    """
    rows, cols = ptr.shape
    ncell = rows * cols
    target = np.full(ncell, -1, dtype=np.int64)

    valid_f = valid.ravel()
    channel_f = channel.ravel()
    ptr_f = ptr.ravel()

    channel_idx = np.flatnonzero(channel_f & valid_f)
    target[channel_idx] = channel_idx

    req_idx = np.flatnonzero(request_mask.ravel() & valid_f)

    def downstream_index(idx: int) -> int:
        r, c = divmod(idx, cols)
        code = int(ptr_f[idx])
        step = WBT_D8.get(code)
        if step is None:
            return -1
        nr, nc = r + step[0], c + step[1]
        if nr < 0 or nr >= rows or nc < 0 or nc >= cols:
            return -1
        ni = nr * cols + nc
        if not valid_f[ni]:
            return -1
        return ni

    t0 = time.time()
    for k, start in enumerate(req_idx.tolist(), start=1):
        if target[start] != -1:
            continue

        path = []
        seen_local = set()
        cur = start
        resolved = -2

        while True:
            tv = int(target[cur])
            if tv >= 0:
                resolved = tv
                break
            if tv == -2:
                resolved = -2
                break
            if cur in seen_local:
                resolved = -2
                break

            seen_local.add(cur)
            path.append(cur)
            nxt = downstream_index(cur)
            if nxt < 0:
                resolved = -2
                break
            cur = nxt

        for idx in path:
            target[idx] = resolved

        if k % 250000 == 0:
            elapsed = time.time() - t0
            print(f"  traced {k:,}/{len(req_idx):,} requested cells ({elapsed:.1f}s)")

    return target.reshape((rows, cols))


def main():
    for p in [DEM, PTR, ACC, DAS]:
        if not p.exists():
            raise FileNotFoundError(p)

    das_geoms = load_geoms(DAS)

    with rasterio.open(DEM) as dds, rasterio.open(PTR) as pds, rasterio.open(ACC) as ads:
        for ds in [pds, ads]:
            if (
                ds.width != dds.width
                or ds.height != dds.height
                or ds.crs != dds.crs
                or not ds.transform.almost_equals(dds.transform)
            ):
                raise RuntimeError("DEM, pointer and accumulation grids are not aligned")

        dem = dds.read(1).astype("float64")
        ptr = pds.read(1)
        acc = ads.read(1).astype("float64")
        rx, ry = abs(dds.res[0]), abs(dds.res[1])
        cell_area = rx * ry

        valid = np.isfinite(dem) & np.isfinite(acc)
        if dds.nodata is not None and np.isfinite(dds.nodata):
            valid &= ~np.isclose(dem, dds.nodata)
        if ads.nodata is not None and np.isfinite(ads.nodata):
            valid &= ~np.isclose(acc, ads.nodata)

        das_mask = rasterize(
            [(g, 1) for g in das_geoms],
            out_shape=(dds.height, dds.width),
            transform=dds.transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)
        analysis_mask = valid & das_mask

        threshold_cells = int(math.ceil(STREAM_THRESHOLD_KM2 * 1_000_000.0 / cell_area))
        # Full-buffer channel network for hydrologic tracing; statistics stay DAS-only.
        channel_full = valid & (acc >= threshold_cells)
        channel_das = channel_full & das_mask

        print("=== KURANJI STAGE 2B GFI BASELINE ===")
        print(f"Grid             : {dds.width} x {dds.height}")
        print(f"Cell area        : {cell_area:.6f} m2")
        print(f"6 km2 threshold  : {threshold_cells:,} cells")
        print(f"Analysis cells   : {np.count_nonzero(analysis_mask):,}")
        print(f"Channel cells DAS: {np.count_nonzero(channel_das):,}")
        print("\nResolving hydrologically connected drainage targets...")

        target = resolve_connected_channel_targets(ptr, channel_full, valid, analysis_mask)
        resolved = analysis_mask & (target >= 0)
        unresolved = analysis_mask & (target < 0)

        print(f"Resolved         : {np.count_nonzero(resolved):,}")
        print(f"Unresolved       : {np.count_nonzero(unresolved):,}")

        rows, cols = dem.shape
        dem_f = dem.ravel()
        acc_f = acc.ravel()
        target_f = target.ravel()
        resolved_idx = np.flatnonzero(resolved.ravel())
        target_idx = target_f[resolved_idx].astype(np.int64)

        H = np.full(dem.shape, np.nan, dtype="float64")
        Ariver_cells = np.full(dem.shape, np.nan, dtype="float64")

        h_vals = dem_f[resolved_idx] - dem_f[target_idx]
        a_vals = acc_f[target_idx]
        H.ravel()[resolved_idx] = h_vals
        Ariver_cells.ravel()[resolved_idx] = a_vals

        negative_H = resolved & (H < 0)
        zero_H = resolved & (H == 0)
        # Match active plugin behavior exactly for zero H.
        H_adj = H.copy()
        H_adj[zero_H] = 0.00001

        Ariver_km2 = ((Ariver_cells + 1.0) * cell_area) / 1_000_000.0
        hr = np.power(Ariver_km2, N_EXPONENT)

        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = hr / H_adj
            gfi_raw = np.log(ratio)

        gfi_valid = analysis_mask & np.isfinite(gfi_raw)
        if not np.any(gfi_valid):
            raise RuntimeError("No finite GFI values produced")

        raw_min = float(np.min(gfi_raw[gfi_valid]))
        raw_max = float(np.max(gfi_raw[gfi_valid]))
        if raw_max <= raw_min:
            raise RuntimeError("Degenerate GFI range")

        gfi_norm = np.full(dem.shape, np.nan, dtype="float64")
        gfi_norm[gfi_valid] = 2.0 * (
            (gfi_raw[gfi_valid] - raw_min) / (raw_max - raw_min) - 0.5
        )

        manual_raw_mask = analysis_mask & np.isfinite(gfi_norm) & (
            gfi_norm > MANUAL_GFI_NORM_THRESHOLD
        )
        manual_clean, components_before, components_after, comp_counts = clean_components(
            manual_raw_mask, MIN_COMPONENT_PIXELS
        )
        manual_clean &= das_mask

        # Report-ready statistics.
        stat_H = stats(H_adj, resolved & ~negative_H)
        stat_A = stats(Ariver_km2, resolved)
        stat_hr = stats(hr, resolved)
        stat_raw = stats(gfi_raw, gfi_valid)
        stat_norm = stats(gfi_norm, gfi_valid)

        n_analysis = int(np.count_nonzero(analysis_mask))
        n_resolved = int(np.count_nonzero(resolved))
        n_unresolved = int(np.count_nonzero(unresolved))
        n_negative = int(np.count_nonzero(negative_H))
        n_zero = int(np.count_nonzero(zero_H))
        n_gfi = int(np.count_nonzero(gfi_valid))
        prone_raw_cells = int(np.count_nonzero(manual_raw_mask))
        prone_clean_cells = int(np.count_nonzero(manual_clean))

        result = {
            "method": {
                "reference": "MODUL TEKNIS KRB BANJIR-2 + active GFA source-code logic",
                "conditioning": "BREACH100 selected in Stage 1",
                "drainage_network": "local channel_FAt adaptation",
                "stream_threshold_km2": STREAM_THRESHOLD_KM2,
                "stream_threshold_cells": threshold_cells,
                "H_definition": "terrain elevation minus first hydrologically connected downstream channel elevation",
                "zero_H_replacement_m": 0.00001,
                "hr_formula": "[((Ariver_cells + 1) * cell_area_m2)/1e6] ** n",
                "n_exponent": N_EXPONENT,
                "GFI_raw": "ln(hr/H)",
                "normalization": "2*((raw-min)/(max-min)-0.5), computed over finite official-DAS GFI cells",
                "manual_threshold_normalized": MANUAL_GFI_NORM_THRESHOLD,
                "manual_threshold_status": "diagnostic only, not final calibration",
                "component_cleanup_min_pixels": MIN_COMPONENT_PIXELS,
            },
            "grid": {
                "crs": str(dds.crs),
                "resolution_m": [rx, ry],
                "cell_area_m2": cell_area,
            },
            "routing_qc": {
                "analysis_cells": n_analysis,
                "resolved_cells": n_resolved,
                "unresolved_cells": n_unresolved,
                "resolved_fraction": n_resolved / n_analysis if n_analysis else 0.0,
                "negative_H_cells": n_negative,
                "zero_H_cells": n_zero,
                "finite_gfi_cells": n_gfi,
            },
            "statistics": {
                "H_m": stat_H,
                "Ariver_km2": stat_A,
                "hr_m": stat_hr,
                "GFI_raw": stat_raw,
                "GFI_normalized": stat_norm,
            },
            "manual_m053_diagnostic": {
                "threshold": MANUAL_GFI_NORM_THRESHOLD,
                "cells_before_cleanup": prone_raw_cells,
                "cells_after_cleanup": prone_clean_cells,
                "area_km2_after_cleanup": prone_clean_cells * cell_area / 1_000_000.0,
                "area_ha_after_cleanup": prone_clean_cells * cell_area / 10_000.0,
                "percent_of_analysis_area": 100.0 * prone_clean_cells / n_analysis if n_analysis else 0.0,
                "components_before_cleanup": components_before,
                "components_after_cleanup": components_after,
            },
        }

        # Prepare output arrays.
        def f32_out(a):
            return np.where(analysis_mask & np.isfinite(a), a, NODATA_F32).astype("float32")

        write_raster(OUT / "01_CHANNEL_FAT_6KM2_FULL.tif", channel_full.astype("uint8"), dds, "uint8", 0)
        write_raster(OUT / "02_H_CONNECTED_DRAINAGE_M.tif", f32_out(H_adj), dds, "float32", NODATA_F32)
        write_raster(OUT / "03_ARIVER_CELLS.tif", f32_out(Ariver_cells), dds, "float32", NODATA_F32)
        write_raster(OUT / "04_ARIVER_KM2.tif", f32_out(Ariver_km2), dds, "float32", NODATA_F32)
        write_raster(OUT / "05_HR_M.tif", f32_out(hr), dds, "float32", NODATA_F32)
        write_raster(OUT / "06_GFI_RAW.tif", f32_out(gfi_raw), dds, "float32", NODATA_F32)
        write_raster(OUT / "07_GFI_NORMALIZED.tif", f32_out(gfi_norm), dds, "float32", NODATA_F32)
        write_raster(OUT / "08_GFI_MANUAL_PRONE_M053.tif", manual_clean.astype("uint8"), dds, "uint8", 0)

    with (OUT / "gfi_baseline_qc.json").open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    csv_path = OUT / "gfi_baseline_stats.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variable", "count", "min", "p01", "p05", "p25", "median", "mean", "p75", "p95", "p99", "max"])
        for name, st in [
            ("H_m", stat_H),
            ("Ariver_km2", stat_A),
            ("hr_m", stat_hr),
            ("GFI_raw", stat_raw),
            ("GFI_normalized", stat_norm),
        ]:
            w.writerow([name] + [st.get(k, "") for k in ["count", "min", "p01", "p05", "p25", "median", "mean", "p75", "p95", "p99", "max"]])

    print("\n=== GFI BASELINE SUMMARY ===")
    print(f"Resolved routing : {n_resolved:,}/{n_analysis:,} ({100*n_resolved/n_analysis:.3f}%)")
    print(f"Negative H cells : {n_negative:,}")
    print(f"Zero H cells     : {n_zero:,}")
    print(f"Finite GFI cells : {n_gfi:,}")
    print(f"GFI raw range    : {stat_raw['min']:.6f} .. {stat_raw['max']:.6f}")
    print(f"GFI norm range   : {stat_norm['min']:.6f} .. {stat_norm['max']:.6f}")
    print(f"Manual -0.53 mask: {result['manual_m053_diagnostic']['area_km2_after_cleanup']:.3f} km2 "
          f"({result['manual_m053_diagnostic']['percent_of_analysis_area']:.2f}% DAS raster cells)")
    print(f"Components       : {components_before} -> {components_after} after >=8 pixel cleanup")
    print("\nQC JSON:", OUT / "gfi_baseline_qc.json")
    print("Stats  :", csv_path)
    print("Rasters:", OUT)


if __name__ == "__main__":
    main()
