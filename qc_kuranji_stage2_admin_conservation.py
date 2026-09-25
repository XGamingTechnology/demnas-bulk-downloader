#!/usr/bin/env python3
"""Conservation QC for Kuranji Stage-2 administrative statistics.

Checks whether P175 hazard/class area remains consistent when aggregated from:
DAS -> kabupaten/kota -> kecamatan -> kelurahan/desa.

Also compares Pauh+Kuranji focus totals from the whole-DAS master table against
focus-specific tables. No analysis raster is modified.

Important QC convention
-----------------------
The administrative coverage tolerance is expressed as a percentage of the full
DAS raster area, because the known source issue is a small administrative coverage
gap at the DAS boundary. Metric-relative percentages (for example, a hazard-area
difference divided by total hazard area) are reported separately for diagnostics
but do not determine PASS/REVIEW.
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


def pct_of_metric(d, ref):
    """Absolute difference as percent of each metric's own DAS total."""
    return {f: (100.0 * abs(d[f]) / ref[f] if ref[f] else 0.0) for f in FIELDS}


def pct_of_das_area(d, das_area_km2):
    """Absolute area differences as percent of the full DAS raster area."""
    return {f: (100.0 * abs(d[f]) / das_area_km2 if das_area_km2 else 0.0) for f in FIELDS}


def main():
    for p in FILES.values():
        if not p.exists():
            raise FileNotFoundError(p)

    das_rows = read_csv(FILES["das"])
    if len(das_rows) != 1:
        raise RuntimeError(f"Expected 1 DAS row, got {len(das_rows)}")

    das = {f: num(das_rows[0], f) for f in FIELDS}
    das_area = das["zone_area_km2"]

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

    comparisons = {}
    for key, agg in [("kab_vs_das", kab), ("kec_vs_das", kec), ("kel_vs_das", kel)]:
        d = diff(agg, das)
        comparisons[key] = {
            "difference_km2": d,
            "abs_pct_of_full_DAS_area": pct_of_das_area(d, das_area),
            "abs_pct_of_each_metric": pct_of_metric(d, das),
        }

    comparisons["focus_kec_vs_master"] = {"difference_km2": diff(focus_kec, focus_master)}
    comparisons["focus_kel18_vs_master_focus"] = {"difference_km2": diff(focus_kel, focus_master)}

    # Administrative source covered 99.9565% of the vector DAS in the preceding audit.
    # A tolerance of 0.10% of the FULL DAS area therefore safely accommodates the
    # known boundary coverage gap while still detecting meaningful aggregation loss.
    tolerance_pct_of_das = 0.10
    whole_checks = {}
    for key in ["kab_vs_das", "kec_vs_das", "kel_vs_das"]:
        ap = comparisons[key]["abs_pct_of_full_DAS_area"]
        whole_checks[key] = {
            "zone_ok": ap["zone_area_km2"] <= tolerance_pct_of_das,
            "hazard_ok": ap["hazard_area_km2"] <= tolerance_pct_of_das,
            "low_ok": ap["low_km2"] <= tolerance_pct_of_das,
            "medium_ok": ap["medium_km2"] <= tolerance_pct_of_das,
            "high_ok": ap["high_km2"] <= tolerance_pct_of_das,
        }

    outside_focus = [r for r in focus_kel_rows if str(r.get("intersects_DAS", "")).strip().lower() in {"false", "0", "no"}]

    # Exact agreement across administrative hierarchy is expected: kab/kota,
    # kecamatan and kelurahan should have the same deficit relative to the DAS if
    # the only cause is the master administrative boundary coverage gap.
    hierarchy_diff_consistent = all(
        abs(diff(kab, das)[f] - diff(kec, das)[f]) < 1e-9
        and abs(diff(kab, das)[f] - diff(kel, das)[f]) < 1e-9
        for f in FIELDS
    )

    focus_consistent = all(
        abs(focus_master[f] - focus_kec[f]) < 1e-9
        and abs(focus_master[f] - focus_kel[f]) < 1e-9
        for f in FIELDS
    )

    out = {
        "tolerance_pct_of_full_DAS_area": tolerance_pct_of_das,
        "das": das,
        "aggregate_sums": {"kabkota": kab, "kecamatan": kec, "kelurahan": kel},
        "focus_master": focus_master,
        "focus_kecamatan_table": focus_kec,
        "focus_kelurahan18_table": focus_kel,
        "comparisons": comparisons,
        "whole_das_checks": whole_checks,
        "hierarchy_difference_consistent": hierarchy_diff_consistent,
        "focus_consistent": focus_consistent,
        "focus_units_total": len(focus_kel_rows),
        "focus_units_outside_DAS": len(outside_focus),
        "focus_units_outside_DAS_names": [f"{r.get('WADMKC','')} / {r.get('WADMKD','')}" for r in outside_focus],
    }

    path = QC / "stage2_admin_conservation_qc.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("=== STAGE 2 ADMIN CONSERVATION QC ===")
    print(f"Tolerance: {tolerance_pct_of_das:.3f}% of FULL DAS raster area ({das_area:.3f} km2)")
    print("\nlevel      zone_diff   hazard_diff  low_diff    med_diff    high_diff   hazard%DAS  hazard%metric")
    print("---------  ----------  -----------  ----------  ----------  ----------  ----------  -------------")
    for name, agg in [("kab/kota", kab), ("kecamatan", kec), ("kelurahan", kel)]:
        d = diff(agg, das)
        p_das = pct_of_das_area(d, das_area)
        p_metric = pct_of_metric(d, das)
        print(
            f"{name:<9} {d['zone_area_km2']:>10.4f}  {d['hazard_area_km2']:>11.4f}  "
            f"{d['low_km2']:>10.4f}  {d['medium_km2']:>10.4f}  {d['high_km2']:>10.4f}  "
            f"{p_das['hazard_area_km2']:>9.4f}%  {p_metric['hazard_area_km2']:>12.4f}%"
        )

    print("\nHierarchy deficit identical across kab/kota -> kecamatan -> kelurahan:",
          "YES" if hierarchy_diff_consistent else "NO")

    print("\n=== FOCUS CONSISTENCY ===")
    for label, vals in [("Master Pauh+Kuranji", focus_master), ("Focus kec table", focus_kec), ("Focus kel 18 table", focus_kel)]:
        print(f"{label:<24} zone={vals['zone_area_km2']:.4f} hazard={vals['hazard_area_km2']:.4f} low={vals['low_km2']:.4f} med={vals['medium_km2']:.4f} high={vals['high_km2']:.4f}")
    print("Focus tables internally consistent:", "YES" if focus_consistent else "NO")

    print(f"\nFocus units: {len(focus_kel_rows)}, outside DAS: {len(outside_focus)}")
    for r in outside_focus:
        print(f"  OUTSIDE DAS: {r.get('WADMKC')} / {r.get('WADMKD')}")

    all_ok = (
        all(all(v.values()) for v in whole_checks.values())
        and hierarchy_diff_consistent
        and focus_consistent
    )
    print("\nWHOLE-DAS HAZARD CONSERVATION:", "PASS" if all_ok else "REVIEW")
    if all_ok:
        print("Interpretation: the small whole-DAS deficit is consistent with the known admin boundary coverage gap,")
        print("not with aggregation loss between kab/kota, kecamatan, and kelurahan levels.")
    print("JSON:", path)


if __name__ == "__main__":
    main()
