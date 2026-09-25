#!/usr/bin/env python3
"""Stage-3 external validation for DAS Batang Kuranji.

Observed reference
------------------
BIG/BRIN 2025_BANJIRSUMATERA MapServer layer 3, preflighted by
`acquire_kuranji_stage3_observed_big.py`:
- Tgl_citra  : 1/12/2025
- Sumber_dat : Hasil interpretasi citra WorldView
- Kabupaten  : Kota Padang

The source is treated as an independent POST-EVENT observed flood-affected extent.
Because the image date is 1 Dec 2025, after the main 21-27 Nov event window, it may
under-represent peak inundation. Therefore FP/FN terminology below is relative to
this reference, not proof that all model-only cells were dry during the event.

Layer 5 is deliberately excluded because its source attribute identifies
`kab_ac_tami_flood`, which is not a Kuranji/Padang flood reference.

Validation design
-----------------
Binary flood extent validates the model DOMAIN only:
- M175 and M250 have identical manual-mask extent.
- P175 and P250 have identical physical WD>0 extent.
Spread 1.75 vs 2.50 cannot be selected using binary flood extent alone.

Outputs
-------
data/work/kuranji/15_stage3_validation/results_big_layer3/
  raster/
    OBSERVED_BIG_BRIN_20251201.tif
    P_DOMAIN_CONFUSION.tif
    M_DOMAIN_CONFUSION.tif
  table/
    validation_metrics_das.csv
    validation_metrics_kecamatan.csv
    validation_metrics_kelurahan.csv
    observed_class_composition.csv
  qc/
    stage3_validation_qc.json
  README_STAGE3_VALIDATION_RESULTS.md

Confusion raster codes:
  0 outside DAS
  1 TN
  2 TP
  3 FP (predicted-only relative to observed reference)
  4 FN (observed-only relative to model)
"""

from __future__ import annotations

import csv
import json
import shutil
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
for d in [RAS_OUT, TAB_OUT, QC_OUT]:
    d.mkdir(parents=True, exist_ok=True)

OBS = SRC / "layer3_kuranji_aligned.tif"
OBS_VEC = SRC / "layer3_kuranji_clip_utm47s.geojson"
SOURCE_QC = SRC / "source_preflight_qc.json"
DAS = ROOT / "data/work/kuranji/01_prepared/DAS_KURANJI_UTM47S.geojson"
SCEN_DIR = ROOT / "data/work/kuranji/12_fuzzy_hazard_sensitivity/rasters"
ADMIN = ROOT / "data/work/kuranji/14_stage2_admin_final/vector/ADMIN_ALL_INTERSECTING_UTM47S.geojson"

SCENARIOS = ["M175", "M250", "P175", "P250"]


def read_fc(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows):
    if not rows:
        return
    fields = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def load_union(path: Path):
    fc = read_fc(path)
    gs = [shape(ft["geometry"]) for ft in fc.get("features", []) if ft.get("geometry")]
    if not gs:
        raise RuntimeError(f"No geometry in {path}")
    return unary_union(gs)


def norm(v):
    return " ".join(str(v or "").strip().upper().split())


def safe_div(a, b):
    return float(a / b) if b else None


def metrics(pred, obs, zone, cell_area):
    tp = int(np.count_nonzero(zone & pred & obs))
    fp = int(np.count_nonzero(zone & pred & ~obs))
    fn = int(np.count_nonzero(zone & ~pred & obs))
    tn = int(np.count_nonzero(zone & ~pred & ~obs))
    pred_n = tp + fp
    obs_n = tp + fn
    zone_n = tp + fp + fn + tn
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * tp, 2 * tp + fp + fn)
    iou = safe_div(tp, tp + fp + fn)
    specificity = safe_div(tn, tn + fp)
    balanced_accuracy = None
    if recall is not None and specificity is not None:
        balanced_accuracy = (recall + specificity) / 2.0
    km2 = lambda n: float(n * cell_area / 1e6)
    return {
        "zone_cells": zone_n,
        "zone_km2": km2(zone_n),
        "predicted_cells": pred_n,
        "predicted_km2": km2(pred_n),
        "observed_cells": obs_n,
        "observed_km2": km2(obs_n),
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


def write_confusion(path, pred, obs, das_mask, ref):
    arr = np.zeros(pred.shape, dtype="uint8")
    arr[das_mask & ~pred & ~obs] = 1
    arr[das_mask & pred & obs] = 2
    arr[das_mask & pred & ~obs] = 3
    arr[das_mask & ~pred & obs] = 4
    prof = ref.profile.copy()
    prof.update(dtype="uint8", count=1, nodata=0, compress="DEFLATE", tiled=True)
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(arr, 1)


def grouped_admin_features():
    fc = read_fc(ADMIN)
    kel = []
    by_kec = defaultdict(list)
    for ft in fc.get("features", []):
        if not ft.get("geometry"):
            continue
        p = ft.get("properties") or {}
        g = shape(ft["geometry"])
        kab = norm(p.get("WADMKK"))
        kec = norm(p.get("WADMKC"))
        desa = norm(p.get("WADMKD"))
        kel.append((g, {"WADMKK": kab, "WADMKC": kec, "WADMKD": desa}))
        by_kec[(kab, kec)].append(g)
    kecs = []
    for (kab, kec), gs in sorted(by_kec.items()):
        kecs.append((unary_union(gs), {"WADMKK": kab, "WADMKC": kec}))
    return kecs, kel


def zone_from_geom(g, ref, das_mask):
    z = rasterize([(g, 1)], out_shape=(ref.height, ref.width), transform=ref.transform,
                  fill=0, all_touched=False, dtype="uint8").astype(bool)
    return z & das_mask


def main():
    required = [OBS, OBS_VEC, SOURCE_QC, DAS, ADMIN]
    required += [SCEN_DIR / f"{s}_HAZARD_CLASS.tif" for s in SCENARIOS]
    for p in required:
        if not p.exists():
            raise FileNotFoundError(p)

    source_qc = json.loads(SOURCE_QC.read_text(encoding="utf-8"))
    cand3 = source_qc.get("candidates", {}).get("layer3", {})
    layer5 = source_qc.get("candidates", {}).get("layer5", {})

    # Provenance guardrails.
    dates = [str(x) for x in cand3.get("tgl_citra_values", [])]
    sources = [str(x) for x in cand3.get("sumber_data_values", [])]
    kab = [str(x).upper() for x in cand3.get("kabupaten_values", [])]
    if "1/12/2025" not in dates:
        raise RuntimeError(f"Unexpected layer-3 image date(s): {dates}")
    if not any("WORLDVIEW" in s.upper() for s in sources):
        raise RuntimeError(f"Unexpected layer-3 source: {sources}")
    if not any("PADANG" in x for x in kab):
        raise RuntimeError(f"Layer 3 is not identified as Kota Padang: {kab}")

    layer5_vals = [str(x).lower() for x in layer5.get("layer_values", [])]
    layer5_excluded = any("ac_tami" in x or "aceh" in x for x in layer5_vals)

    das_geom = load_union(DAS)

    das_rows = []
    kec_rows = []
    kel_rows = []
    comp_rows = []

    with rasterio.open(OBS) as ods:
        obs_arr = ods.read(1)
        obs = obs_arr == 1
        cell_area = abs(ods.res[0] * ods.res[1])
        das_mask = rasterize([(das_geom, 1)], out_shape=(ods.height, ods.width), transform=ods.transform,
                             fill=0, all_touched=False, dtype="uint8").astype(bool)
        obs &= das_mask

        kec_features, kel_features = grouped_admin_features()

        scenario_arrays = {}
        for sc in SCENARIOS:
            p = SCEN_DIR / f"{sc}_HAZARD_CLASS.tif"
            with rasterio.open(p) as ds:
                if ds.width != ods.width or ds.height != ods.height or ds.crs != ods.crs or not ds.transform.almost_equals(ods.transform):
                    raise RuntimeError(f"Raster alignment mismatch: {sc}")
                cls = ds.read(1)
            pred = (cls > 0) & das_mask
            scenario_arrays[sc] = (pred, cls)

            r = {"scenario": sc, "domain": "manual" if sc.startswith("M") else "physical_WD_gt_0"}
            r.update(metrics(pred, obs, das_mask, cell_area))
            das_rows.append(r)

            # Descriptive class composition of the observed extent, NOT depth validation.
            for c, label in [(1, "LOW"), (2, "MEDIUM"), (3, "HIGH")]:
                n = int(np.count_nonzero(obs & (cls == c)))
                comp_rows.append({
                    "scenario": sc,
                    "class": label,
                    "observed_overlap_cells": n,
                    "observed_overlap_km2": n * cell_area / 1e6,
                    "pct_of_observed_extent": 100.0 * n / np.count_nonzero(obs) if np.count_nonzero(obs) else None,
                    "interpretation": "descriptive only; binary observed extent cannot validate modeled depth class",
                })

            for g, pprops in kec_features:
                zone = zone_from_geom(g, ods, das_mask)
                rr = {"scenario": sc, **pprops}
                rr.update(metrics(pred, obs, zone, cell_area))
                kec_rows.append(rr)

            for g, pprops in kel_features:
                zone = zone_from_geom(g, ods, das_mask)
                if not np.any(zone):
                    continue
                rr = {"scenario": sc, **pprops}
                rr.update(metrics(pred, obs, zone, cell_area))
                kel_rows.append(rr)

        # Confirm identical binary domains by spread pair.
        p_same = bool(np.array_equal(scenario_arrays["P175"][0], scenario_arrays["P250"][0]))
        m_same = bool(np.array_equal(scenario_arrays["M175"][0], scenario_arrays["M250"][0]))

        write_confusion(RAS_OUT / "P_DOMAIN_CONFUSION.tif", scenario_arrays["P175"][0], obs, das_mask, ods)
        write_confusion(RAS_OUT / "M_DOMAIN_CONFUSION.tif", scenario_arrays["M175"][0], obs, das_mask, ods)

        # Preserve observed raster under explicit provenance name.
        prof = ods.profile.copy()
        with rasterio.open(RAS_OUT / "OBSERVED_BIG_BRIN_20251201.tif", "w", **prof) as dst:
            dst.write(obs.astype(ods.dtypes[0]), 1)

    write_csv(TAB_OUT / "validation_metrics_das.csv", das_rows)
    write_csv(TAB_OUT / "validation_metrics_kecamatan.csv", kec_rows)
    write_csv(TAB_OUT / "validation_metrics_kelurahan.csv", kel_rows)
    write_csv(TAB_OUT / "observed_class_composition.csv", comp_rows)

    # Pull the two unique-domain headline results.
    p = next(r for r in das_rows if r["scenario"] == "P175")
    m = next(r for r in das_rows if r["scenario"] == "M175")

    qc = {
        "observed_reference": {
            "provider": "BIG/BRIN via BIG 2025_BANJIRSUMATERA MapServer layer 3",
            "image_date": dates,
            "source": sources,
            "kabupaten": cand3.get("kabupaten_values", []),
            "observed_area_raster_km2": p["observed_km2"],
            "interpretation": "post-event observed flood-affected extent; may under-represent peak inundation",
        },
        "excluded_source": {
            "layer_id": 5,
            "layer_values": layer5.get("layer_values", []),
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
    (QC_OUT / "stage3_validation_qc.json").write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# Stage 3 Validation — BIG/BRIN WorldView 1 Dec 2025\n\n"
    readme += "Observed reference: BIG/BRIN layer 3, interpreted WorldView imagery dated 1 Dec 2025, Kota Padang.\n\n"
    readme += "Layer 5 was excluded because its attribute identifies `kab_ac_tami_flood`, inconsistent with Kuranji/Padang provenance.\n\n"
    readme += f"Observed area in DAS: {p['observed_km2']:.4f} km2.\n\n"
    readme += "Binary validation compares the physical P-domain against the manual M-domain. P175=P250 in extent and M175=M250 in extent.\n\n"
    readme += "Important: the observed source is post-event. False-positive/model-only areas are relative to the 1 Dec reference and are not proof that those cells were never flooded during the 21-27 Nov peak event.\n"
    (OUT / "README_STAGE3_VALIDATION_RESULTS.md").write_text(readme, encoding="utf-8")

    print("=== KURANJI STAGE 3 EXTERNAL VALIDATION ===")
    print("Observed source : BIG/BRIN WorldView interpretation")
    print("Image date      :", ", ".join(dates))
    print(f"Observed area   : {p['observed_km2']:.4f} km2")
    print("Layer 5 status  : EXCLUDED (kab_ac_tami_flood provenance mismatch)")
    print("\nscenario domain             pred_km2  TP_km2  FP_km2  FN_km2  precision  recall    F1       IoU")
    print("-------- ------------------  ---------  -------  -------  -------  ---------  --------  -------  -------")
    for r in das_rows:
        def f(v): return "NA" if v is None else f"{v:.4f}"
        print(f"{r['scenario']:<8} {r['domain']:<18} {r['predicted_km2']:>9.3f} {r['tp_km2']:>8.3f} {r['fp_km2']:>8.3f} {r['fn_km2']:>8.3f} {f(r['precision']):>10} {f(r['recall']):>9} {f(r['f1']):>8} {f(r['iou']):>8}")

    print("\nBinary extent equivalence:")
    print("P175 == P250:", p_same)
    print("M175 == M250:", m_same)
    print("\nCAUTION: observed image is dated 1 Dec 2025, so results measure agreement with the post-event mapped extent, not necessarily peak 21-27 Nov inundation.")
    print("Output:", OUT)


if __name__ == "__main__":
    main()
