#!/usr/bin/env python3
"""Conservation QC for Kuranji Stage-2 administrative statistics.

Checks whether P175 hazard/class area remains consistent when aggregated from:
DAS -> kabupaten/kota -> kecamatan -> kelurahan/desa.

Also compares Pauh+Kuranji focus totals from the whole-DAS master table against
focus-specific tables. No analysis raster is modified.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "data/work/kuranji/14_stage2_admin_final"
TAB = BASE / "table"
QC = BASE / "qc"
QC.mkdir(parents=True, exist_ok=True)

FILES = {
    "das": TAB / "hazard_stats_das.csv",
    "kab": TAB / "hazard_stats_kabkota.csv",
    "kec": TAB / "hazard_stats_kecamatan_all.csv",
    "kel": TAB / "hazard_stats_kelurahan_all_intersecting.csv",
    "focus_kec": TAB / "hazard_stats_focus_kecamatan.csv",
    "focus_kel": TAB / "hazard_stats_focus_kelurahan_18.csv",
}

FIELDS = ["zone_area_km2", "hazard_area_km2", "low_km2", "medium_km2", "high_km2"]
FOCUS = {"PAUH", "KURANJI"}


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def num(row, field):
    try:
        return float(row.get(field, 0) or 0)
    except Exception:
        return 0.0


def sums(rows):
    return {f: sum(num(r, f) for r in rows) for f in FIELDS}


def diff(a, b):
    return {f: a[f] - b[f] for f in FIELDS}


def pct_abs(d, ref):
    return {f: (100.0 * abs(d[f]) / ref[f] if ref[f] else 0.0) for f in FIELDS}


def main():
    for p in FILES.values():
        if not p.exists():
            raise FileNotFoundError(p)

    das_rows = read_csv(FILES["das"])
    if len(das_rows) != 1:
        raise RuntimeError(f"Expected 1 DAS row, got {len(das_rows)}")

    das = {f: num(das_rows[0], f) for f in FIELDS}
    kab_rows = read_csv(FILES["kab"])
    kec_rows = read_csv(FILES["kec"])
    kel_rows = read_csv(FILES["kel"])
    focus_kec_rows = read_csv(FILES["focus_kec"])
    focus_kel_rows = read_csv(FILES["focus_kel"])

    kab = sums(kab_rows)
    kec = sums(kec_rows)
    kel = sums(kel_rows)

    focus_master_rows = [r for r in kec_rows if (r.get("WADMKC") or "").strip().upper() in FOCUS]
    focus_master = sums(focus_master_rows)
    focus_kec = sums(focus_kec_rows)
    focus_kel = sums(focus_kel_rows)

    comparisons = {
        "kab_vs_das": {"difference_km2": diff(kab, das), "abs_pct_of_das": pct_abs(diff(kab, das), das)},
        "kec_vs_das": {"difference_km2": diff(kec, das), "abs_pct_of_das": pct_abs(diff(kec, das), das)},
        "kel_vs_das": {"difference_km2": diff(kel, das), "abs_pct_of_das": pct_abs(diff(kel, das), das)},
        "focus_kec_vs_master": {"difference_km2": diff(focus_kec, focus_master)},
        "focus_kel18_vs_master_focus": {"difference_km2": diff(focus_kel, focus_master)},
    }

    # Conservation tolerance: administrative source previously covered 99.9565% of DAS.
    # Therefore sub-0.1% whole-DAS difference is expected/acceptable if spatially explained.
    tolerance_pct = 0.10
    whole_checks = {}
    for key in ["kab_vs_das", "kec_vs_das", "kel_vs_das"]:
        ap = comparisons[key]["abs_pct_of_das"]
        whole_checks[key] = {
            "hazard_ok": ap["hazard_area_km2"] <= tolerance_pct,
            "low_ok": ap["low_km2"] <= tolerance_pct,
            "medium_ok": ap["medium_km2"] <= tolerance_pct,
            "high_ok": ap["high_km2"] <= tolerance_pct,
        }

    outside_focus = [r for r in focus_kel_rows if str(r.get("intersects_DAS", "")).strip().lower() in {"false", "0", "no"}]

    out = {
        "tolerance_pct": tolerance_pct,
        "das": das,
        "aggregate_sums": {"kabkota": kab, "kecamatan": kec, "kelurahan": kel},
        "focus_master": focus_master,
        "focus_kecamatan_table": focus_kec,
        "focus_kelurahan18_table": focus_kel,
        "comparisons": comparisons,
        "whole_das_checks": whole_checks,
        "focus_units_total": len(focus_kel_rows),
        "focus_units_outside_DAS": len(outside_focus),
        "focus_units_outside_DAS_names": [f"{r.get('WADMKC','')} / {r.get('WADMKD','')}" for r in outside_focus],
    }

    path = QC / "stage2_admin_conservation_qc.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("=== STAGE 2 ADMIN CONSERVATION QC ===")
    print(f"Tolerance: {tolerance_pct:.3f}% of DAS reference aggregation")
    print("\nlevel      zone_diff   hazard_diff  low_diff    med_diff    high_diff   hazard_diff%")
    print("---------  ----------  -----------  ----------  ----------  ----------  ------------")
    for name, agg in [("kab/kota", kab), ("kecamatan", kec), ("kelurahan", kel)]:
        d = diff(agg, das)
        p = pct_abs(d, das)
        print(f"{name:<9} {d['zone_area_km2']:>10.4f}  {d['hazard_area_km2']:>11.4f}  {d['low_km2']:>10.4f}  {d['medium_km2']:>10.4f}  {d['high_km2']:>10.4f}  {p['hazard_area_km2']:>11.4f}%")

    print("\n=== FOCUS CONSISTENCY ===")
    for label, vals in [("Master Pauh+Kuranji", focus_master), ("Focus kec table", focus_kec), ("Focus kel 18 table", focus_kel)]:
        print(f"{label:<24} zone={vals['zone_area_km2']:.4f} hazard={vals['hazard_area_km2']:.4f} low={vals['low_km2']:.4f} med={vals['medium_km2']:.4f} high={vals['high_km2']:.4f}")

    print(f"\nFocus units: {len(focus_kel_rows)}, outside DAS: {len(outside_focus)}")
    for r in outside_focus:
        print(f"  OUTSIDE DAS: {r.get('WADMKC')} / {r.get('WADMKD')}")

    all_ok = all(all(v.values()) for v in whole_checks.values())
    print("\nWHOLE-DAS HAZARD CONSERVATION:", "PASS" if all_ok else "REVIEW")
    print("JSON:", path)


if __name__ == "__main__":
    main()
