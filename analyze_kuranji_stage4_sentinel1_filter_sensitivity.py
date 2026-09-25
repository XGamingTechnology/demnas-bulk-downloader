#!/usr/bin/env python3
"""Stage-4 Sentinel-1 filter-sensitivity QC for DAS Batang Kuranji.

Compares RAW aligned dB change rasters against the existing 3x3 NaN-aware
median-filtered derivatives within the frozen Stage-4 zones:
- observed BIG/BRIN 2025-12-01
- non-observed reference
- Stage-3 TP
- Stage-3 FN

Purpose: test whether the observed spatial contrast persists after modest speckle
suppression. This is descriptive QC only. No flood/change threshold is selected.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent
S1 = ROOT / "data/work/kuranji/19_stage4_sentinel1_change"
CHANGE = S1 / "change"
OVERLAY = ROOT / "data/work/kuranji/20_stage4_sentinel1_overlay"
OUT = ROOT / "data/work/kuranji/21_stage4_sentinel1_filter_qc"
OUT.mkdir(parents=True, exist_ok=True)

MASKS = {
    "OBSERVED_BIG_BRIN": OVERLAY / "OBSERVED_BIG_BRIN_20251201_20m.tif",
    "NON_OBSERVED_REFERENCE": OVERLAY / "OBSERVED_BIG_BRIN_20251201_20m.tif",  # inverted below
    "STAGE3_TP": OVERLAY / "STAGE3_TP_20m.tif",
    "STAGE3_FN": OVERLAY / "STAGE3_FN_20m.tif",
}
COMMON = OVERLAY / "COMMON_VALID_S1_20m.tif"

COMPARISONS = ["EVENT_MINUS_PRE", "POST_MINUS_PRE", "POST_MINUS_EVENT"]
VARIABLES = ["VV", "VH", "VHminusVV"]


def read_mask(path: Path):
    with rasterio.open(path) as ds:
        a = ds.read(1)
        return a == 1, ds.profile


def read_float(path: Path):
    with rasterio.open(path) as ds:
        return ds.read(1, masked=True).astype("float32").filled(np.nan)


def describe(arr, mask):
    x = arr[mask & np.isfinite(arr)]
    q = np.percentile(x, [5, 25, 50, 75, 95])
    return {
        "n": int(x.size),
        "mean": float(np.mean(x)),
        "median": float(q[2]),
        "p05": float(q[0]),
        "p25": float(q[1]),
        "p75": float(q[3]),
        "p95": float(q[4]),
        "std": float(np.std(x)),
        "negative_pct": float(np.mean(x < 0) * 100.0),
        "positive_pct": float(np.mean(x > 0) * 100.0),
    }


def layer_path(comp, var, filtered):
    suffix = "_dB_med3_20m_DAS.tif" if filtered else "_dB_20m_DAS.tif"
    return CHANGE / f"{comp}_{var}{suffix}"


def main():
    common, _ = read_mask(COMMON)
    observed, _ = read_mask(MASKS["OBSERVED_BIG_BRIN"])
    tp, _ = read_mask(MASKS["STAGE3_TP"])
    fn, _ = read_mask(MASKS["STAGE3_FN"])
    nonobs = common & (~observed)

    zones = {
        "OBSERVED_BIG_BRIN": observed & common,
        "NON_OBSERVED_REFERENCE": nonobs,
        "STAGE3_TP": tp & common,
        "STAGE3_FN": fn & common,
    }

    rows = []
    contrasts = []

    print("=== KURANJI STAGE 4 SENTINEL-1 FILTER SENSITIVITY ===")

    for comp in COMPARISONS:
        print(f"\n=== {comp} ===")
        for var in VARIABLES:
            for filtered in [False, True]:
                mode = "MED3" if filtered else "RAW"
                path = layer_path(comp, var, filtered)
                if not path.exists():
                    raise FileNotFoundError(path)
                arr = read_float(path)
                zone_stats = {}
                for zone, mask in zones.items():
                    st = describe(arr, mask)
                    zone_stats[zone] = st
                    rows.append({"comparison": comp, "variable": var, "mode": mode, "zone": zone, **st})

                obs = zone_stats["OBSERVED_BIG_BRIN"]
                non = zone_stats["NON_OBSERVED_REFERENCE"]
                tp_s = zone_stats["STAGE3_TP"]
                fn_s = zone_stats["STAGE3_FN"]
                contrast = {
                    "comparison": comp,
                    "variable": var,
                    "mode": mode,
                    "observed_median": obs["median"],
                    "nonobserved_median": non["median"],
                    "observed_minus_nonobserved_median": obs["median"] - non["median"],
                    "tp_median": tp_s["median"],
                    "fn_median": fn_s["median"],
                    "fn_minus_tp_median": fn_s["median"] - tp_s["median"],
                    "observed_negative_pct": obs["negative_pct"],
                    "nonobserved_negative_pct": non["negative_pct"],
                }
                contrasts.append(contrast)

                print(
                    f"{var:<10} {mode:<4} | "
                    f"OBS med={obs['median']:+7.3f}  NON med={non['median']:+7.3f}  "
                    f"OBS-NON={contrast['observed_minus_nonobserved_median']:+7.3f} dB | "
                    f"TP={tp_s['median']:+7.3f} FN={fn_s['median']:+7.3f}"
                )

    fields = [
        "comparison", "variable", "mode", "zone", "n", "mean", "median",
        "p05", "p25", "p75", "p95", "std", "negative_pct", "positive_pct",
    ]
    with (OUT / "RAW_VS_MED3_BY_ZONE.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    cfields = list(contrasts[0].keys())
    with (OUT / "RAW_VS_MED3_CONTRASTS.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cfields)
        w.writeheader()
        w.writerows(contrasts)

    print("\n=== DONE ===")
    print("Detailed:", OUT / "RAW_VS_MED3_BY_ZONE.csv")
    print("Contrasts:", OUT / "RAW_VS_MED3_CONTRASTS.csv")
    print("Interpretation rule: if RAW and MED3 preserve the same contrast direction, the signal is more likely spatially coherent rather than single-pixel speckle.")


if __name__ == "__main__":
    main()
