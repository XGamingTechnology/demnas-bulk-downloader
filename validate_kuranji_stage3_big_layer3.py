#!/usr/bin/env python3
"""Stage-3 external validation for DAS Batang Kuranji.

Observed reference
------------------
BIG/BRIN 2025_BANJIRSUMATERA MapServer layer 3, preflighted by
`acquire_kuranji_stage3_observed_big.py`:
- Tgl_citra  : 1/12/2025
- Sumber_dat : Hasil interpretasi citra WorldView
- Kabupaten  : Kota Padang

The source is treated as an independent post-event observed flood-affected extent.
Because the image date is 1 Dec 2025, after the main 21-27 Nov event window, it may
under-represent peak inundation. FP/FN are therefore relative to this observed
reference, not proof that all model-only cells were dry at peak event.

Binary flood extent validates model DOMAIN only:
- M175 and M250 have identical manual-mask extent.
- P175 and P250 have identical physical WD>0 extent.
Spread 1.75 vs 2.50 cannot be selected from binary flood extent alone.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "data/work/kuranji/15_stage3_validation"
SRC = BASE / "source_big"
OUT = BASE / "results_big_layer3"
RAS_OUT = OUT / "raster"
TAB_OUT = OUT / "table"
QC_OUT = OUT / "qc"
for d in (RAS_OUT, TAB_OUT, QC_OUT):
    d.mkdir(parents=True, exist_ok=True)

OBS = SRC / "layer3_kuranji_aligned.tif"
SOURCE_QC = SRC / "source_preflight_qc.json"
DAS = ROOT / "data/work/kuranji/01_prepared/DAS_KURANJI_UTM47S.geojson"
ADMIN = ROOT / "data/work/kuranji/14_stage2_admin_final/vector/ADMIN_ALL_INTERSECTING_UTM47S.geojson"
SCEN_DIR = ROOT / "data/work/kuranji/12_fuzzy_hazard_sensitivity/rasters"
SCENARIOS = ["M175", "M250", "P175", "P250"]


def read_fc(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows):
    if not rows:
        return
    fields, seen = [], set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def norm(v):
    return " ".join(str(v or "").strip().upper().split())


def load_union(path: Path):
    fc = read_fc(path)
    geoms = [shape(ft["geometry"]) for ft in fc.get("features", []) if ft.get("geometry")]
    if not geoms:
        raise RuntimeError(f"No geometry in {path}")
    return unary_union(geoms)


def safe_div(a, b):
    return float(a / b) if b else None


def metrics(pred, obs, zone, cell_area):
    tp = int(np.count_nonzero(zone & pred & obs))
    fp = int(np.count_nonzero(zone & pred & ~obs))
    fn = int(np.count_nonzero(zone & ~pred & obs))
    tn = int(np.count_nonzero(zone & ~pred & ~obs))
    km2 = lambda n: float(n * cell_area / 1e6)

    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * tp, 2 * tp + fp + fn)
    iou = safe_div(tp, tp + fp + fn)
    specificity = safe_div(tn, tn + fp)
    balanced_accuracy = (
        (recall + specificity) / 2.0
        if recall is not None and specificity is not None
        else None
    )

    return {
        "zone_cells": tp + fp + fn + tn,
        "zone_km2": km2(tp + fp + fn + tn),
        "predicted_cells": tp + fp,
        "predicted_km2": km2(tp + fp),
        "observed_cells": tp + fn,
        "observed_km2": km2(tp + fn),
        "tp_cells": tp,
        "tp_km2": km2(tp),
        "fp_cells": fp,
        "fp_km2": km2(fp),
        "fn_cells": fn,
        "fn_km2": km2(fn),
        "tn_cells": tn,
        "tn_km2": km2(tn),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "iou": iou,
        "specificity": specificity,
        "balanced_accuracy": balanced_accuracy,
        "observed_capture_pct": 100.0 * recall if recall is not None else None,
        "predicted_confirmed_pct": 100.0 * precision if precision is not None else None,
    }


def admin_features():
    fc = read_fc(ADMIN)
    kelurahan = []
    by_kec = defaultdict(list)
    for ft in fc.get("features", []):
        if not ft.get("geometry"):
            continue
        g = shape(ft["geometry"])
        p = ft.get("properties") or {}
        kab = norm(p.get("WADMKK"))
        kec = norm(p.get("WADMKC"))
        kel = norm(p.get("WADMKD"))
        kelurahan.append((g, {"WADMKK": kab, "WADMKC": kec, "WADMKD": kel}))
        by_kec[(kab, kec)].append(g)

    kecamatan = []
    for (kab, kec), geoms in sorted(by_kec.items()):
        kecamatan.append((unary_union(geoms), {"WADMKK": kab, "WADMKC": kec}))
    return kecamatan, kelurahan


def raster_zone(geom, ref, das_mask):
    arr = rasterize(
        [(geom, 1)],
        out_shape=(ref.height, ref.width),
        transform=ref.transform,
        fill=0,
        all_touched=False,
        dtype="uint8",
    ).astype(bool)
    return arr & das_mask


def write_confusion(path, pred, obs, das_mask, ref):
    # 0 outside DAS, 1 TN, 2 TP, 3 FP, 4 FN
    arr = np.zeros(pred.shape, dtype="uint8")
    arr[das_mask & ~pred & ~obs] = 1
    arr[das_mask & pred & obs] = 2
    arr[das_mask & pred & ~obs] = 3
    arr[das_mask & ~pred & obs] = 4
    profile = ref.profile.copy()
    profile.update(dtype="uint8", count=1, nodata=0, compress="DEFLATE", tiled=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)


def fmt(v):
    return "NA" if v is None else f"{v:.4f}"


def main():
    required = [OBS, SOURCE_QC, DAS, ADMIN]
    required += [SCEN_DIR / f"{s}_HAZARD_CLASS.tif" for s in SCENARIOS]
    for path in required:
        if not path.exists():
            raise FileNotFoundError(path)

    source_qc = json.loads(SOURCE_QC.read_text(encoding="utf-8"))
    cand3 = source_qc.get("candidates", {}).get("layer3", {})
    cand5 = source_qc.get("candidates", {}).get("layer5", {})

    dates = [str(x) for x in cand3.get("tgl_citra_values", [])]
    sources = [str(x) for x in cand3.get("sumber_data_values", [])]
    kabupaten = [str(x) for x in cand3.get("kabupaten_values", [])]

    if "1/12/2025" not in dates:
        raise RuntimeError(f"Unexpected layer-3 image date(s): {dates}")
    if not any("WORLDVIEW" in x.upper() for x in sources):
        raise RuntimeError(f"Unexpected layer-3 source: {sources}")
    if not any("PADANG" in x.upper() for x in kabupaten):
        raise RuntimeError(f"Layer 3 is not identified as Kota Padang: {kabupaten}")

    layer5_values = [str(x).lower() for x in cand5.get("layer_values", [])]
    layer5_excluded = any("ac_tami" in x or "aceh" in x for x in layer5_values)

    das_geom = load_union(DAS)
    kec_features, kel_features = admin_features()

    das_rows, kec_rows, kel_rows, class_rows = [], [], [], []

    with rasterio.open(OBS) as obs_ds:
        obs = obs_ds.read(1) == 1
        cell_area = abs(obs_ds.res[0] * obs_ds.res[1])
        das_mask = rasterize(
            [(das_geom, 1)],
            out_shape=(obs_ds.height, obs_ds.width),
            transform=obs_ds.transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)
        obs &= das_mask

        scenario_arrays = {}
        for scenario in SCENARIOS:
            path = SCEN_DIR / f"{scenario}_HAZARD_CLASS.tif"
            with rasterio.open(path) as ds:
                if (
                    ds.width != obs_ds.width
                    or ds.height != obs_ds.height
                    or ds.crs != obs_ds.crs
                    or not ds.transform.almost_equals(obs_ds.transform)
                ):
                    raise RuntimeError(f"Raster alignment mismatch: {scenario}")
                cls = ds.read(1)

            pred = (cls > 0) & das_mask
            scenario_arrays[scenario] = (pred, cls)
            domain = "manual" if scenario.startswith("M") else "physical_WD_gt_0"

            row = {"scenario": scenario, "domain": domain}
            row.update(metrics(pred, obs, das_mask, cell_area))
            das_rows.append(row)

            obs_count = int(np.count_nonzero(obs))
            for code, label in ((1, "LOW"), (2, "MEDIUM"), (3, "HIGH")):
                n = int(np.count_nonzero(obs & (cls == code)))
                class_rows.append({
                    "scenario": scenario,
                    "class": label,
                    "observed_overlap_cells": n,
                    "observed_overlap_km2": n * cell_area / 1e6,
                    "pct_of_observed_extent": 100.0 * n / obs_count if obs_count else None,
                    "interpretation": "descriptive only; binary observed extent cannot validate modeled depth class",
                })

            for geom, props in kec_features:
                zone = raster_zone(geom, obs_ds, das_mask)
                rr = {"scenario": scenario, **props}
                rr.update(metrics(pred, obs, zone, cell_area))
                kec_rows.append(rr)

            for geom, props in kel_features:
                zone = raster_zone(geom, obs_ds, das_mask)
                if not np.any(zone):
                    continue
                rr = {"scenario": scenario, **props}
                rr.update(metrics(pred, obs, zone, cell_area))
                kel_rows.append(rr)

        p_same = bool(np.array_equal(scenario_arrays["P175"][0], scenario_arrays["P250"][0]))
        m_same = bool(np.array_equal(scenario_arrays["M175"][0], scenario_arrays["M250"][0]))

        write_confusion(
            RAS_OUT / "P_DOMAIN_CONFUSION.tif",
            scenario_arrays["P175"][0],
            obs,
            das_mask,
            obs_ds,
        )
        write_confusion(
            RAS_OUT / "M_DOMAIN_CONFUSION.tif",
            scenario_arrays["M175"][0],
            obs,
            das_mask,
            obs_ds,
        )

        profile = obs_ds.profile.copy()
        profile.update(dtype="uint8", count=1, nodata=0, compress="DEFLATE")
        with rasterio.open(RAS_OUT / "OBSERVED_BIG_BRIN_20251201.tif", "w", **profile) as dst:
            dst.write(obs.astype("uint8"), 1)

    write_csv(TAB_OUT / "validation_metrics_das.csv", das_rows)
    write_csv(TAB_OUT / "validation_metrics_kecamatan.csv", kec_rows)
    write_csv(TAB_OUT / "validation_metrics_kelurahan.csv", kel_rows)
    write_csv(TAB_OUT / "observed_class_composition.csv", class_rows)

    p = next(r for r in das_rows if r["scenario"] == "P175")
    m = next(r for r in das_rows if r["scenario"] == "M175")

    qc = {
        "observed_reference": {
            "provider": "BIG/BRIN via BIG 2025_BANJIRSUMATERA MapServer layer 3",
            "image_date": dates,
            "source": sources,
            "kabupaten": kabupaten,
            "observed_area_raster_km2": p["observed_km2"],
            "interpretation": "post-event observed flood-affected extent; may under-represent peak inundation",
        },
        "excluded_source": {
            "layer_id": 5,
            "layer_values": cand5.get("layer_values", []),
            "excluded": layer5_excluded,
            "reason": "attribute identifies kab_ac_tami_flood; provenance does not match Kuranji/Padang",
        },
        "binary_domain_equivalence": {
            "P175_equals_P250": p_same,
            "M175_equals_M250": m_same,
            "implication": "binary extent cannot select fuzzy spread 1.75 vs 2.50",
        },
        "headline_metrics": {
            "physical_domain_P": p,
            "manual_domain_M": m,
        },
        "cautions": [
            "WorldView image date is 1 Dec 2025, after the main 21-27 Nov event window.",
            "Model-only area is FP only relative to this observed reference and may include true peak-event flooding that had receded by 1 Dec.",
            "Binary flood extent validates flood-domain location, not modeled water-depth severity classes.",
            "No model parameter was tuned using the 2025 validation extent in this script.",
        ],
    }
    (QC_OUT / "stage3_validation_qc.json").write_text(
        json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    readme = "# Stage 3 Validation — BIG/BRIN WorldView 1 Dec 2025\n\n"
    readme += "Observed reference: BIG/BRIN layer 3, interpreted WorldView imagery dated 1 Dec 2025, Kota Padang.\n\n"
    readme += "Layer 5 was excluded because its attribute identifies `kab_ac_tami_flood`, inconsistent with Kuranji/Padang provenance.\n\n"
    readme += f"Observed area in DAS: {p['observed_km2']:.4f} km2.\n\n"
    readme += "Binary validation compares the physical P-domain against the manual M-domain. P175=P250 in extent and M175=M250 in extent.\n\n"
    readme += "Important: the observed source is post-event. Model-only areas are relative to the 1 Dec reference and are not proof that those cells were never flooded during the 21-27 Nov peak event.\n"
    (OUT / "README_STAGE3_VALIDATION_RESULTS.md").write_text(readme, encoding="utf-8")

    print("=== KURANJI STAGE 3 EXTERNAL VALIDATION ===")
    print("Observed source : BIG/BRIN WorldView interpretation")
    print("Image date      :", ", ".join(dates))
    print(f"Observed area   : {p['observed_km2']:.4f} km2")
    print("Layer 5 status  : EXCLUDED (kab_ac_tami_flood provenance mismatch)")
    print()
    print("scenario domain             pred_km2  TP_km2  FP_km2  FN_km2  precision  recall    F1       IoU")
    print("-------- ------------------  ---------  -------  -------  -------  ---------  --------  -------  -------")
    for r in das_rows:
        print(
            f"{r['scenario']:<8} {r['domain']:<18} {r['predicted_km2']:>9.3f} "
            f"{r['tp_km2']:>8.3f} {r['fp_km2']:>8.3f} {r['fn_km2']:>8.3f} "
            f"{fmt(r['precision']):>10} {fmt(r['recall']):>9} {fmt(r['f1']):>8} {fmt(r['iou']):>8}"
        )

    print("\nBinary extent equivalence:")
    print("P175 == P250:", p_same)
    print("M175 == M250:", m_same)
    print()
    print("CAUTION: observed image is dated 1 Dec 2025, so results measure agreement with the post-event mapped extent, not necessarily peak 21-27 Nov inundation.")
    print("Output:", OUT)


if __name__ == "__main__":
    main()
