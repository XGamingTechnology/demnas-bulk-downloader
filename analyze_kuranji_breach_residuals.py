#!/usr/bin/env python3
"""Analyze residual mismatch after Kuranji least-cost breaching.

This script compares BREACH100 and BREACH250 watershed masks against the official
reference DAS and the previously diagnosed ~32.8 km2 secondary partition.

It answers four questions:
1. Are BREACH100 and BREACH250 watershed masks actually identical cell-by-cell?
2. How much of the baseline secondary partition is now captured by the main basin?
3. Where is the remaining reference-only area (~12.6 km2)?
4. Is the remaining mismatch one coherent block or many small edge fragments?

Outputs
-------
data/work/kuranji/05_validation/conditioning_sensitivity/
  breach_residual_analysis.json
  BREACH100_REF_ONLY.tif
  BREACH100_MODEL_ONLY.tif
  BREACH250_REF_ONLY.tif
  BREACH250_MODEL_ONLY.tif
  BREACH_RESIDUAL_COMPONENTS.geojson
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import label, center_of_mass
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent
PREP = ROOT / "data/work/kuranji/01_prepared"
WAT = ROOT / "data/work/kuranji/03_watershed"
OUT = ROOT / "data/work/kuranji/05_validation/conditioning_sensitivity"
OUT.mkdir(parents=True, exist_ok=True)

DAS = PREP / "DAS_KURANJI_UTM47S.geojson"
RBI = PREP / "SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson"
SECONDARY = WAT / "SECONDARY_PARTITION_100M_RANK2.tif"

SCENARIOS = {
    "breach100": OUT / "BREACH100_WATERSHED.tif",
    "breach250": OUT / "BREACH250_WATERSHED.tif",
}

REPORT = OUT / "breach_residual_analysis.json"
COMPONENTS_GEOJSON = OUT / "BREACH_RESIDUAL_COMPONENTS.geojson"
STRUCTURE8 = np.ones((3, 3), dtype=np.uint8)
MIN_COMPONENT_AREA_KM2 = 0.01
MAX_COMPONENTS_PER_CLASS = 50


def load_geoms(path: Path):
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    gs = [shape(ft["geometry"]) for ft in data.get("features", []) if ft.get("geometry")]
    if not gs:
        raise RuntimeError(f"No geometries in {path}")
    return gs


def valid_mask(ds, arr):
    m = np.isfinite(arr)
    if ds.nodata is not None and np.isfinite(ds.nodata):
        m &= ~np.isclose(arr, ds.nodata)
    return m


def write_mask(path: Path, mask: np.ndarray, ref):
    profile = ref.profile.copy()
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
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(mask.astype("uint8"), 1)


def component_summary(mask, transform, cell_area, scenario, kind):
    lab, ncomp = label(mask, structure=STRUCTURE8)
    if ncomp == 0:
        return [], []

    counts = np.bincount(lab.ravel())
    ids = np.arange(1, len(counts))
    areas = counts[1:] * cell_area / 1_000_000.0
    order = ids[np.argsort(areas)[::-1]]

    rows = []
    features = []
    rank = 0
    for cid in order:
        n = int(counts[cid])
        area = float(n * cell_area / 1_000_000.0)
        if area < MIN_COMPONENT_AREA_KM2:
            continue
        rank += 1
        if rank > MAX_COMPONENTS_PER_CLASS:
            break
        cy, cx = center_of_mass(mask.astype("uint8"), lab, cid)
        x, y = rasterio.transform.xy(transform, int(round(cy)), int(round(cx)), offset="center")
        rec = {
            "scenario": scenario,
            "kind": kind,
            "rank": rank,
            "component_id": int(cid),
            "cells": n,
            "area_km2": area,
            "centroid_x": float(x),
            "centroid_y": float(y),
        }
        rows.append(rec)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(x), float(y)]},
            "properties": rec,
        })
    return rows, features


def main():
    for p in [DAS, RBI, SECONDARY, *SCENARIOS.values()]:
        if not p.exists():
            raise FileNotFoundError(p)

    das_geoms = load_geoms(DAS)
    _ = load_geoms(RBI)  # retained as provenance / future spatial checks

    with rasterio.open(SCENARIOS["breach100"]) as ref, rasterio.open(SECONDARY) as sds:
        if sds.width != ref.width or sds.height != ref.height or sds.crs != ref.crs or not sds.transform.almost_equals(ref.transform):
            raise RuntimeError("Secondary partition grid differs from breach watershed grid")

        cell_area = abs(ref.res[0] * ref.res[1])
        das_mask = rasterize(
            [(g, 1) for g in das_geoms],
            out_shape=(ref.height, ref.width),
            transform=ref.transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)
        secondary_mask = sds.read(1) > 0
        ref_cells = int(np.count_nonzero(das_mask))
        ref_area = float(ref_cells * cell_area / 1_000_000.0)
        sec_cells = int(np.count_nonzero(secondary_mask))
        sec_area = float(sec_cells * cell_area / 1_000_000.0)

        scenario_masks = {}
        scenario_results = {}
        all_features = []

        for name, path in SCENARIOS.items():
            with rasterio.open(path) as ds:
                if ds.width != ref.width or ds.height != ref.height or ds.crs != ref.crs or not ds.transform.almost_equals(ref.transform):
                    raise RuntimeError(f"Grid differs: {path}")
                a = ds.read(1).astype("float64", copy=False)
                model = valid_mask(ds, a) & (a > 0)

            scenario_masks[name] = model
            ref_only = das_mask & ~model
            model_only = model & ~das_mask
            intersection = das_mask & model

            ref_only_out = OUT / f"{name.upper()}_REF_ONLY.tif"
            model_only_out = OUT / f"{name.upper()}_MODEL_ONLY.tif"
            write_mask(ref_only_out, ref_only, ref)
            write_mask(model_only_out, model_only, ref)

            ref_only_rows, ref_only_features = component_summary(
                ref_only, ref.transform, cell_area, name, "reference_only"
            )
            model_only_rows, model_only_features = component_summary(
                model_only, ref.transform, cell_area, name, "model_only"
            )
            all_features.extend(ref_only_features)
            all_features.extend(model_only_features)

            sec_in = secondary_mask & model
            sec_out = secondary_mask & ~model
            sec_in_cells = int(np.count_nonzero(sec_in))
            sec_out_cells = int(np.count_nonzero(sec_out))

            scenario_results[name] = {
                "reference_area_km2": ref_area,
                "model_area_km2": float(np.count_nonzero(model) * cell_area / 1_000_000.0),
                "intersection_area_km2": float(np.count_nonzero(intersection) * cell_area / 1_000_000.0),
                "reference_only_area_km2": float(np.count_nonzero(ref_only) * cell_area / 1_000_000.0),
                "model_only_area_km2": float(np.count_nonzero(model_only) * cell_area / 1_000_000.0),
                "secondary_partition": {
                    "baseline_area_km2": sec_area,
                    "captured_by_main_watershed_km2": float(sec_in_cells * cell_area / 1_000_000.0),
                    "captured_fraction": float(sec_in_cells / sec_cells) if sec_cells else 0.0,
                    "remaining_outside_main_watershed_km2": float(sec_out_cells * cell_area / 1_000_000.0),
                    "remaining_fraction": float(sec_out_cells / sec_cells) if sec_cells else 0.0,
                },
                "reference_only_components_ge_0_01km2": ref_only_rows,
                "model_only_components_ge_0_01km2": model_only_rows,
                "outputs": {
                    "reference_only_raster": str(ref_only_out.relative_to(ROOT)),
                    "model_only_raster": str(model_only_out.relative_to(ROOT)),
                },
            }

        xor = scenario_masks["breach100"] ^ scenario_masks["breach250"]
        xor_cells = int(np.count_nonzero(xor))
        comparison = {
            "watershed_masks_identical": xor_cells == 0,
            "xor_cells": xor_cells,
            "xor_area_km2": float(xor_cells * cell_area / 1_000_000.0),
        }

    fc = {
        "type": "FeatureCollection",
        "name": "breach_residual_components",
        "crs": {"type": "name", "properties": {"name": str(ref.crs)}},
        "features": all_features,
    }
    with COMPONENTS_GEOJSON.open("w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)

    report = {
        "reference_das_area_km2": ref_area,
        "baseline_secondary_partition_area_km2": sec_area,
        "breach100_vs_breach250": comparison,
        "scenarios": scenario_results,
        "interpretation_note": (
            "If most of the baseline ~32.8 km2 secondary partition is captured by the breached main watershed, "
            "then least-cost breaching successfully reconnects much of that terrain even if the internal 6 km2 stream path still disagrees with RBI. "
            "The remaining reference-only components should then be inspected separately before any stream burning/enforcement."
        ),
    }
    with REPORT.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("=== KURANJI BREACH RESIDUAL ANALYSIS ===")
    print(f"Reference DAS       : {ref_area:.3f} km2")
    print(f"Secondary baseline  : {sec_area:.3f} km2")
    print(f"B100 vs B250 same?  : {comparison['watershed_masks_identical']} | XOR={comparison['xor_area_km2']:.6f} km2")

    for name, row in scenario_results.items():
        sec = row["secondary_partition"]
        print(f"\n{name}")
        print(f"  model area        : {row['model_area_km2']:.3f} km2")
        print(f"  intersection      : {row['intersection_area_km2']:.3f} km2")
        print(f"  reference-only    : {row['reference_only_area_km2']:.3f} km2")
        print(f"  model-only        : {row['model_only_area_km2']:.3f} km2")
        print(f"  secondary captured: {sec['captured_by_main_watershed_km2']:.3f} km2 ({sec['captured_fraction']*100:.2f}%)")
        print(f"  secondary outside : {sec['remaining_outside_main_watershed_km2']:.3f} km2 ({sec['remaining_fraction']*100:.2f}%)")
        print("  largest reference-only components:")
        for c in row["reference_only_components_ge_0_01km2"][:10]:
            print(f"    #{c['rank']:>2} area={c['area_km2']:.3f} km2 at X={c['centroid_x']:.1f}, Y={c['centroid_y']:.1f}")
        print("  largest model-only components:")
        for c in row["model_only_components_ge_0_01km2"][:10]:
            print(f"    #{c['rank']:>2} area={c['area_km2']:.3f} km2 at X={c['centroid_x']:.1f}, Y={c['centroid_y']:.1f}")

    print("\nJSON      :", REPORT)
    print("Components:", COMPONENTS_GEOJSON)


if __name__ == "__main__":
    main()
