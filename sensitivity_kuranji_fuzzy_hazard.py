#!/usr/bin/env python3
"""Stage-2 fuzzy-hazard sensitivity for DAS Kuranji.

Compares four diagnostic scenarios:
- M175: module manual GFI threshold (-0.53 normalized), FuzzyLarge spread 1.75
- M250: module manual GFI threshold (-0.53 normalized), FuzzyLarge spread 2.5
- P175: physical-positive mask (GFI_raw > 0 / WD > 0), spread 1.75
- P250: physical-positive mask (GFI_raw > 0 / WD > 0), spread 2.5

The purpose is sensitivity/QC, not automatic final calibration.

Outputs
-------
data/work/kuranji/12_fuzzy_hazard_sensitivity/
  scenario_summary.csv
  scenario_summary.json
  rasters/<scenario>_WD_INPUT.tif
  rasters/<scenario>_HAZARD_INDEX.tif
  rasters/<scenario>_HAZARD_CLASS.tif
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "data/work/kuranji/08_gfi_baseline"
OUT = ROOT / "data/work/kuranji/12_fuzzy_hazard_sensitivity"
RAS = OUT / "rasters"
RAS.mkdir(parents=True, exist_ok=True)

H_PATH = BASE / "02_H_CONNECTED_DRAINAGE_M.tif"
HR_PATH = BASE / "05_HR_M.tif"
RAW_PATH = BASE / "06_GFI_RAW.tif"
NORM_PATH = BASE / "07_GFI_NORMALIZED.tif"

MIDPOINT = 1.125
MANUAL_THRESHOLD = -0.53
NODATA = -9999.0

SCENARIOS = {
    "M175": {"mask":"manual", "spread":1.75},
    "M250": {"mask":"manual", "spread":2.5},
    "P175": {"mask":"physical", "spread":1.75},
    "P250": {"mask":"physical", "spread":2.5},
}


def write_raster(path, arr, ref, dtype="float32", nodata=NODATA):
    profile = ref.profile.copy()
    profile.update(driver="GTiff", dtype=dtype, count=1, nodata=nodata,
                   compress="DEFLATE", tiled=True, blockxsize=512, blockysize=512)
    out = np.where(np.isfinite(arr), arr, nodata).astype(dtype)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(out, 1)


def fuzzy_large(x, midpoint, spread):
    out = np.zeros_like(x, dtype="float64")
    pos = np.isfinite(x) & (x > 0)
    out[pos] = 1.0 / (1.0 + np.power(x[pos] / midpoint, -spread))
    out[np.isfinite(x) & (x <= 0)] = 0.0
    out[~np.isfinite(x)] = np.nan
    return out


def stat(x, mask):
    v = x[mask & np.isfinite(x)]
    if v.size == 0:
        return {"count":0}
    return {
        "count":int(v.size), "min":float(v.min()), "p05":float(np.percentile(v,5)),
        "median":float(np.median(v)), "mean":float(np.mean(v)),
        "p95":float(np.percentile(v,95)), "p99":float(np.percentile(v,99)),
        "max":float(v.max())
    }


def main():
    for p in [H_PATH, HR_PATH, RAW_PATH, NORM_PATH]:
        if not p.exists():
            raise FileNotFoundError(p)

    with rasterio.open(H_PATH) as hds, rasterio.open(HR_PATH) as rds, \
         rasterio.open(RAW_PATH) as rawds, rasterio.open(NORM_PATH) as nds:
        for ds in [rds, rawds, nds]:
            if ds.width != hds.width or ds.height != hds.height or ds.crs != hds.crs or not ds.transform.almost_equals(hds.transform):
                raise RuntimeError("Input rasters are not aligned")

        H = hds.read(1).astype("float64")
        hr = rds.read(1).astype("float64")
        raw = rawds.read(1).astype("float64")
        norm = nds.read(1).astype("float64")

        for arr, ds in [(H,hds),(hr,rds),(raw,rawds),(norm,nds)]:
            if ds.nodata is not None and np.isfinite(ds.nodata):
                arr[np.isclose(arr, ds.nodata)] = np.nan

        valid = np.isfinite(H) & np.isfinite(hr) & np.isfinite(raw) & np.isfinite(norm)
        cell_area = abs(hds.res[0] * hds.res[1])

        wd_raw = np.full(H.shape, np.nan, dtype="float64")
        wd_raw[valid] = hr[valid] - H[valid]

        results = []
        for name, cfg in SCENARIOS.items():
            if cfg["mask"] == "manual":
                mask = valid & (norm > MANUAL_THRESHOLD)
            else:
                mask = valid & (raw > 0)

            wd_input = np.full(H.shape, np.nan, dtype="float64")
            wd_input[mask] = np.maximum(wd_raw[mask], 0.0)

            hz = np.full(H.shape, np.nan, dtype="float64")
            hz[mask] = fuzzy_large(wd_input[mask], MIDPOINT, cfg["spread"])

            cls = np.full(H.shape, np.nan, dtype="float64")
            cls[mask & (hz <= 0.333)] = 1
            cls[mask & (hz > 0.333) & (hz <= 0.666)] = 2
            cls[mask & (hz > 0.666)] = 3

            low = int(np.count_nonzero(cls == 1))
            med = int(np.count_nonzero(cls == 2))
            high = int(np.count_nonzero(cls == 3))
            total = low + med + high

            res = {
                "scenario":name,
                "mask_type":cfg["mask"],
                "spread":cfg["spread"],
                "area_km2":float(total*cell_area/1e6),
                "wd_negative_raw_cells":int(np.count_nonzero(mask & (wd_raw < 0))),
                "wd_positive_raw_cells":int(np.count_nonzero(mask & (wd_raw > 0))),
                "low_km2":float(low*cell_area/1e6),
                "medium_km2":float(med*cell_area/1e6),
                "high_km2":float(high*cell_area/1e6),
                "low_percent":100*low/total if total else 0,
                "medium_percent":100*med/total if total else 0,
                "high_percent":100*high/total if total else 0,
                "hazard_stats":stat(hz,mask),
                "wd_input_stats":stat(wd_input,mask),
            }
            results.append(res)

            write_raster(RAS / f"{name}_WD_INPUT.tif", wd_input, hds)
            write_raster(RAS / f"{name}_HAZARD_INDEX.tif", hz, hds)
            write_raster(RAS / f"{name}_HAZARD_CLASS.tif", cls, hds, dtype="uint8", nodata=0)

    out_json = OUT / "scenario_summary.json"
    out_csv = OUT / "scenario_summary.csv"
    with out_json.open("w", encoding="utf-8") as f:
        json.dump({"midpoint":MIDPOINT,"manual_threshold":MANUAL_THRESHOLD,"results":results}, f, indent=2)

    fields = ["scenario","mask_type","spread","area_km2","wd_negative_raw_cells","wd_positive_raw_cells",
              "low_km2","medium_km2","high_km2","low_percent","medium_percent","high_percent"]
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in results: w.writerow({k:r.get(k) for k in fields})

    print("=== KURANJI FUZZY HAZARD SENSITIVITY ===")
    print("scenario mask      spread area_km2 low%   med%   high%  negWD_raw")
    print("-------- --------- ------ --------- ------ ------ ------ ---------")
    for r in results:
        print(f"{r['scenario']:<8} {r['mask_type']:<9} {r['spread']:>6.2f} {r['area_km2']:>9.3f} "
              f"{r['low_percent']:>6.2f} {r['medium_percent']:>6.2f} {r['high_percent']:>6.2f} {r['wd_negative_raw_cells']:>9,}")
    print("\nJSON:",out_json)
    print("CSV :",out_csv)
    print("Rasters:",RAS)

if __name__ == "__main__":
    main()
