#!/usr/bin/env python3
"""Positional-tolerance QC for Kuranji Stage-3 validation.

Purpose
-------
Evaluate sensitivity of binary overlap metrics to small spatial offsets between
modeled flood-domain rasters and the observed BIG/BRIN WorldView flood extent.

This is NOT threshold calibration. Model domains are fixed. The script only
computes tolerant matching at distances of 0, 1, 2, 3 and 5 pixels.

Method
------
For each tolerance distance r:
- Observed recall under tolerance: an observed cell is counted as captured if a
  predicted cell occurs within r pixels.
- Predicted precision under tolerance: a predicted cell is counted as confirmed
  if an observed cell occurs within r pixels.

This symmetric proximity treatment avoids artificially expanding only one dataset.
Exact-overlap metrics at r=0 remain the primary strict validation metrics.

Outputs
-------
data/work/kuranji/15_stage3_validation/positional_tolerance/
  positional_tolerance_metrics.csv
  positional_tolerance_qc.json
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import binary_dilation, generate_binary_structure, iterate_structure

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "data/work/kuranji/15_stage3_validation"
OBS = BASE / "results_big_layer3/raster/OBSERVED_BIG_BRIN_20251201.tif"
SCEN_DIR = ROOT / "data/work/kuranji/12_fuzzy_hazard_sensitivity/rasters"
OUT = BASE / "positional_tolerance"
OUT.mkdir(parents=True, exist_ok=True)

SCENARIOS = ["P175", "M175"]
RADII = [0, 1, 2, 3, 5]


def safe_div(a, b):
    return float(a / b) if b else None


def write_csv(path, rows):
    if not rows:
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    required = [OBS] + [SCEN_DIR / f"{s}_HAZARD_CLASS.tif" for s in SCENARIOS]
    for p in required:
        if not p.exists():
            raise FileNotFoundError(p)

    rows = []
    with rasterio.open(OBS) as ods:
        obs = ods.read(1) == 1
        cell_size = float((abs(ods.res[0]) + abs(ods.res[1])) / 2.0)
        cell_area = abs(ods.res[0] * ods.res[1])

        base_struct = generate_binary_structure(2, 2)

        for sc in SCENARIOS:
            with rasterio.open(SCEN_DIR / f"{sc}_HAZARD_CLASS.tif") as ds:
                if (
                    ds.width != ods.width
                    or ds.height != ods.height
                    or ds.crs != ods.crs
                    or not ds.transform.almost_equals(ods.transform)
                ):
                    raise RuntimeError(f"Alignment mismatch: {sc}")
                pred = ds.read(1) > 0

            n_obs = int(np.count_nonzero(obs))
            n_pred = int(np.count_nonzero(pred))

            for r in RADII:
                if r == 0:
                    obs_buf = obs
                    pred_buf = pred
                else:
                    structure = iterate_structure(base_struct, r)
                    obs_buf = binary_dilation(obs, structure=structure)
                    pred_buf = binary_dilation(pred, structure=structure)

                obs_captured = int(np.count_nonzero(obs & pred_buf))
                pred_confirmed = int(np.count_nonzero(pred & obs_buf))

                recall_tol = safe_div(obs_captured, n_obs)
                precision_tol = safe_div(pred_confirmed, n_pred)
                f1_tol = (
                    safe_div(2 * precision_tol * recall_tol, precision_tol + recall_tol)
                    if precision_tol is not None and recall_tol is not None and (precision_tol + recall_tol) > 0
                    else None
                )

                rows.append({
                    "scenario": sc,
                    "tolerance_pixels": r,
                    "tolerance_m_approx": r * cell_size,
                    "observed_area_km2": n_obs * cell_area / 1e6,
                    "predicted_area_km2": n_pred * cell_area / 1e6,
                    "observed_captured_km2": obs_captured * cell_area / 1e6,
                    "predicted_confirmed_km2": pred_confirmed * cell_area / 1e6,
                    "tolerant_recall": recall_tol,
                    "tolerant_precision": precision_tol,
                    "tolerant_f1": f1_tol,
                })

    write_csv(OUT / "positional_tolerance_metrics.csv", rows)

    qc = {
        "purpose": "diagnostic positional sensitivity only; not model calibration",
        "observed_reference": "BIG/BRIN WorldView interpretation dated 1 Dec 2025",
        "scenarios": SCENARIOS,
        "tolerance_pixels": RADII,
        "notes": [
            "Exact r=0 values remain the primary strict validation reference.",
            "Tolerance metrics quantify near-miss sensitivity to small spatial offsets.",
            "Symmetric treatment is used: recall checks observed cells near predictions; precision checks predicted cells near observations.",
            "Tolerance results must not be used to retune GFI thresholds against the same 2025 event.",
        ],
        "rows": rows,
    }
    (OUT / "positional_tolerance_qc.json").write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== STAGE 3 POSITIONAL TOLERANCE QC ===")
    print("scenario tol_px tol_m  recall   precision F1")
    print("-------- ------ ------ -------- --------- --------")
    for r in rows:
        f = lambda x: "NA" if x is None else f"{x:.4f}"
        print(
            f"{r['scenario']:<8} {r['tolerance_pixels']:>6} {r['tolerance_m_approx']:>6.1f} "
            f"{f(r['tolerant_recall']):>8} {f(r['tolerant_precision']):>9} {f(r['tolerant_f1']):>8}"
        )

    print("\nOutput:", OUT)


if __name__ == "__main__":
    main()
