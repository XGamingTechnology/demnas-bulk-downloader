#!/usr/bin/env python3
"""Print compact Stage-3 validation diagnostics by kecamatan and kelurahan.

Reads outputs from validate_kuranji_stage3_big_layer3.py and does not modify data.
Focuses on the two unique binary domains: P175 (physical) and M175 (manual).
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TAB = ROOT / "data/work/kuranji/15_stage3_validation/results_big_layer3/table"


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def f(row, key):
    try:
        return float(row.get(key) or 0)
    except Exception:
        return 0.0


def metric(row, key):
    v = row.get(key)
    if v in (None, "", "None"):
        return None
    try:
        return float(v)
    except Exception:
        return None


def show_metric(v):
    return "NA" if v is None else f"{v:.3f}"


def main():
    kec_path = TAB / "validation_metrics_kecamatan.csv"
    kel_path = TAB / "validation_metrics_kelurahan.csv"
    comp_path = TAB / "observed_class_composition.csv"
    for p in [kec_path, kel_path, comp_path]:
        if not p.exists():
            raise FileNotFoundError(p)

    kec = read_csv(kec_path)
    kel = read_csv(kel_path)
    comp = read_csv(comp_path)

    print("=== STAGE 3 ADMINISTRATIVE VALIDATION SUMMARY ===")

    for sc in ["P175", "M175"]:
        print(f"\n=== {sc} — KECAMATAN ===")
        rows = [r for r in kec if r.get("scenario") == sc and f(r, "observed_km2") > 0]
        rows.sort(key=lambda r: f(r, "observed_km2"), reverse=True)
        print("kecamatan              obs_km2 pred_km2 TP_km2 FP_km2 FN_km2 precision recall   F1    IoU")
        print("---------------------- -------- -------- ------- ------- ------- --------- ------ ------ ------")
        for r in rows:
            print(
                f"{r.get('WADMKC',''):<22} "
                f"{f(r,'observed_km2'):>8.3f} {f(r,'predicted_km2'):>8.3f} "
                f"{f(r,'tp_km2'):>7.3f} {f(r,'fp_km2'):>7.3f} {f(r,'fn_km2'):>7.3f} "
                f"{show_metric(metric(r,'precision')):>9} {show_metric(metric(r,'recall')):>6} "
                f"{show_metric(metric(r,'f1')):>6} {show_metric(metric(r,'iou')):>6}"
            )

        print(f"\nTop 10 {sc} kelurahan by observed extent:")
        krows = [r for r in kel if r.get("scenario") == sc and f(r, "observed_km2") > 0]
        krows.sort(key=lambda r: f(r, "observed_km2"), reverse=True)
        for i, r in enumerate(krows[:10], 1):
            print(
                f"{i:>2}. {r.get('WADMKC','')} / {r.get('WADMKD','')}: "
                f"obs={f(r,'observed_km2'):.3f} TP={f(r,'tp_km2'):.3f} "
                f"FP={f(r,'fp_km2'):.3f} FN={f(r,'fn_km2'):.3f} "
                f"P={show_metric(metric(r,'precision'))} R={show_metric(metric(r,'recall'))} "
                f"F1={show_metric(metric(r,'f1'))}"
            )

        print(f"\nTop 10 {sc} kelurahan by false negative area:")
        fnrows = sorted(krows, key=lambda r: f(r, "fn_km2"), reverse=True)
        for i, r in enumerate(fnrows[:10], 1):
            print(
                f"{i:>2}. {r.get('WADMKC','')} / {r.get('WADMKD','')}: "
                f"FN={f(r,'fn_km2'):.3f} obs={f(r,'observed_km2'):.3f} TP={f(r,'tp_km2'):.3f}"
            )

    print("\n=== OBSERVED EXTENT COMPOSITION WITHIN MODELED CLASSES ===")
    for sc in ["P175", "P250", "M175", "M250"]:
        rows = [r for r in comp if r.get("scenario") == sc]
        print(f"\n{sc}:")
        for r in rows:
            print(
                f"  {r.get('class',''):<6} overlap={f(r,'observed_overlap_km2'):.3f} km2 "
                f"({f(r,'pct_of_observed_extent'):.2f}% of observed)"
            )

    print("\nNOTE: class composition is descriptive only. Binary observed extent does not validate water-depth severity class.")


if __name__ == "__main__":
    main()
