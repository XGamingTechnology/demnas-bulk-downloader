#!/usr/bin/env python3
"""Compare full GFI/WD behaviour for GFA default channel_ASk versus local 6 km2 channel.

Purpose
-------
Stage-2 preflight showed that channel_ASk is much denser than the locally calibrated
6 km2 network when compared to RBI. However, GFI depends on the drainage definition
through H and Ariver. A denser drainage network may substantially alter H, hr, GFI,
and the resulting WD = hr - H.

This script therefore computes the same GFA-style H/Ariver/hr/GFI chain for BOTH:
  A. channel_ASk (module/plugin default logic)
  B. channel_FAt with 6 km2 contributing-area threshold (local adaptation)

It reports, for each method:
- routing resolution rate;
- H / hr / raw GFI statistics;
- normalized GFI using the same DAS analysis domain;
- manual -0.53 flood-prone area;
- WD = hr - H statistics inside that mask;
- positive/negative WD fractions;
- physical boundary threshold (normalized value where raw GFI=0).

No method is automatically declared final. The result is a methodological comparison
used before locking the Stage-2 hazard pipeline.
"""

from __future__ import annotations

import json
import math
import csv
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import label
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent
PREP = ROOT / "data/work/kuranji/01_prepared"
SENS = ROOT / "data/work/kuranji/05_validation/conditioning_sensitivity"
PREFLIGHT = ROOT / "data/work/kuranji/07_gfi_preflight"
OUT = ROOT / "data/work/kuranji/11_gfi_channel_method_comparison"
OUT.mkdir(parents=True, exist_ok=True)

DEM = SENS / "BREACH100_DEM.tif"
PTR = SENS / "BREACH100_D8_POINTER.tif"
ACC = SENS / "BREACH100_FLOW_ACCUM_CELLS.tif"
DAS = PREP / "DAS_KURANJI_UTM47S.geojson"

# Preflight ASk raster is clipped to DAS, so ASk is reconstructed on full valid grid here.
N_EXPONENT = 0.354429752
MANUAL_THRESHOLD = -0.53
MIN_COMPONENT_PIXELS = 8
STREAM_THRESHOLD_KM2 = 6.0
NODATA = -9999.0
STRUCT8 = np.ones((3, 3), dtype=np.uint8)

WBT_D8 = {
    1: (-1, 1), 2: (0, 1), 4: (1, 1), 8: (1, 0),
    16: (1, -1), 32: (0, -1), 64: (-1, -1), 128: (-1, 0),
}


def load_geojson(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def horn_slope_degree(z, valid, dx, dy):
    work = z.astype("float64", copy=True)
    med = float(np.nanmedian(work[valid]))
    work[~valid] = med
    p = np.pad(work, 1, mode="edge")
    z1,z2,z3 = p[:-2,:-2],p[:-2,1:-1],p[:-2,2:]
    z4,z6 = p[1:-1,:-2],p[1:-1,2:]
    z7,z8,z9 = p[2:,:-2],p[2:,1:-1],p[2:,2:]
    dzdx = ((z3 + 2*z6 + z9) - (z1 + 2*z4 + z7)) / (8.0*dx)
    dzdy = ((z7 + 2*z8 + z9) - (z1 + 2*z2 + z3)) / (8.0*dy)
    out = np.degrees(np.arctan(np.hypot(dzdx,dzdy)))
    out[~valid] = np.nan
    return out


def propagate(seed, ptr, valid):
    rows, cols = seed.shape
    out = seed.astype(bool).copy()
    rr,cc = np.where(seed)
    for r0,c0 in zip(rr.tolist(),cc.tolist()):
        r,c = r0,c0
        seen = 0
        while 0 <= r < rows and 0 <= c < cols and valid[r,c]:
            step = WBT_D8.get(int(ptr[r,c]))
            if step is None:
                break
            nr,nc = r+step[0], c+step[1]
            if nr < 0 or nr >= rows or nc < 0 or nc >= cols or not valid[nr,nc]:
                break
            out[nr,nc] = True
            r,c = nr,nc
            seen += 1
            if seen > rows*cols:
                raise RuntimeError("Unexpected D8 loop")
    return out


def resolve_targets(ptr, channel, valid, request):
    rows, cols = ptr.shape
    n = rows*cols
    target = np.full(n, -1, dtype=np.int64)
    vf = valid.ravel(); cf = channel.ravel(); pf = ptr.ravel()
    ch = np.flatnonzero(vf & cf)
    target[ch] = ch
    req = np.flatnonzero(request.ravel() & vf)

    def down(idx):
        r,c = divmod(idx, cols)
        step = WBT_D8.get(int(pf[idx]))
        if step is None:
            return -1
        nr,nc = r+step[0], c+step[1]
        if nr < 0 or nr >= rows or nc < 0 or nc >= cols:
            return -1
        j = nr*cols+nc
        return j if vf[j] else -1

    for start in req.tolist():
        if target[start] != -1:
            continue
        path=[]; seen=set(); cur=start; resolved=-2
        while True:
            tv=int(target[cur])
            if tv >= 0:
                resolved=tv; break
            if tv == -2 or cur in seen:
                resolved=-2; break
            seen.add(cur); path.append(cur)
            nxt=down(cur)
            if nxt < 0:
                resolved=-2; break
            cur=nxt
        for idx in path:
            target[idx]=resolved
    return target.reshape((rows,cols))


def stats(arr, mask):
    x = arr[mask & np.isfinite(arr)]
    if x.size == 0:
        return {"count":0}
    return {
        "count":int(x.size), "min":float(x.min()), "p05":float(np.percentile(x,5)),
        "median":float(np.median(x)), "mean":float(np.mean(x)),
        "p95":float(np.percentile(x,95)), "p99":float(np.percentile(x,99)),
        "max":float(x.max()),
    }


def clean(mask):
    lab,n = label(mask, structure=STRUCT8)
    counts=np.bincount(lab.ravel())
    keep=np.where(counts >= MIN_COMPONENT_PIXELS)[0]
    keep=keep[keep!=0]
    return np.isin(lab,keep), int(n), int(len(keep))


def evaluate(name, channel, dem, ptr, acc, valid, analysis, cell_area):
    target = resolve_targets(ptr, channel, valid, analysis)
    resolved = analysis & (target >= 0)
    unresolved = analysis & (target < 0)
    idx = np.flatnonzero(resolved.ravel())
    tgt = target.ravel()[idx].astype(np.int64)
    demf=dem.ravel(); accf=acc.ravel()

    H=np.full(dem.shape,np.nan,dtype="float64")
    Ar=np.full(dem.shape,np.nan,dtype="float64")
    H.ravel()[idx]=demf[idx]-demf[tgt]
    Ar.ravel()[idx]=accf[tgt]
    negH = resolved & (H < 0)
    zeroH = resolved & (H == 0)
    Hadj=H.copy(); Hadj[zeroH]=0.00001
    Akm2=((Ar+1.0)*cell_area)/1e6
    hr=np.power(Akm2,N_EXPONENT)
    with np.errstate(divide="ignore",invalid="ignore"):
        raw=np.log(hr/Hadj)
    gvalid=analysis & np.isfinite(raw)
    rmin=float(np.min(raw[gvalid])); rmax=float(np.max(raw[gvalid]))
    norm=np.full(raw.shape,np.nan,dtype="float64")
    norm[gvalid]=2*((raw[gvalid]-rmin)/(rmax-rmin)-0.5)
    prone0=gvalid & (norm > MANUAL_THRESHOLD)
    prone,cb,ca=clean(prone0)
    prone &= analysis
    wd=np.full(raw.shape,np.nan,dtype="float64")
    wd[prone]=hr[prone]-Hadj[prone]
    neg=prone & (wd < 0); pos=prone & (wd > 0)
    phys= gvalid & (raw > 0)
    # normalized raw=0 boundary
    zero_norm = 2*((0.0-rmin)/(rmax-rmin)-0.5)

    return {
        "name":name,
        "channel_cells_das":int(np.count_nonzero(channel & analysis)),
        "resolved":int(np.count_nonzero(resolved)),
        "unresolved":int(np.count_nonzero(unresolved)),
        "resolved_percent":100*np.count_nonzero(resolved)/np.count_nonzero(analysis),
        "negative_H_cells":int(np.count_nonzero(negH)),
        "zero_H_cells":int(np.count_nonzero(zeroH)),
        "H_stats":stats(Hadj,resolved & ~negH),
        "hr_stats":stats(hr,resolved),
        "gfi_raw_stats":stats(raw,gvalid),
        "gfi_raw_min":rmin,
        "gfi_raw_max":rmax,
        "raw_zero_norm_threshold":float(zero_norm),
        "manual_prone_area_km2":float(np.count_nonzero(prone)*cell_area/1e6),
        "manual_prone_components_before":cb,
        "manual_prone_components_after":ca,
        "manual_prone_negative_wd_cells":int(np.count_nonzero(neg)),
        "manual_prone_positive_wd_cells":int(np.count_nonzero(pos)),
        "manual_prone_negative_wd_percent":100*np.count_nonzero(neg)/np.count_nonzero(prone) if np.count_nonzero(prone) else 0,
        "manual_prone_positive_wd_percent":100*np.count_nonzero(pos)/np.count_nonzero(prone) if np.count_nonzero(prone) else 0,
        "wd_all_prone_stats":stats(wd,prone),
        "wd_positive_stats":stats(wd,pos),
        "physical_positive_wd_area_km2":float(np.count_nonzero(phys)*cell_area/1e6),
    }


def main():
    for p in [DEM,PTR,ACC,DAS]:
        if not p.exists(): raise FileNotFoundError(p)
    fc=load_geojson(DAS)
    geoms=[shape(ft["geometry"]) for ft in fc.get("features",[]) if ft.get("geometry")]
    if not geoms: raise RuntimeError("No DAS geometry")

    with rasterio.open(DEM) as dds, rasterio.open(PTR) as pds, rasterio.open(ACC) as ads:
        dem=dds.read(1).astype("float64"); ptr=pds.read(1); acc=ads.read(1).astype("float64")
        rx,ry=abs(dds.res[0]),abs(dds.res[1]); cell_area=rx*ry
        valid=np.isfinite(dem)&np.isfinite(acc)
        if dds.nodata is not None and np.isfinite(dds.nodata): valid &= ~np.isclose(dem,dds.nodata)
        if ads.nodata is not None and np.isfinite(ads.nodata): valid &= ~np.isclose(acc,ads.nodata)
        das=rasterize([(g,1) for g in geoms],out_shape=dem.shape,transform=dds.transform,fill=0,all_touched=False,dtype="uint8").astype(bool)
        analysis=valid&das

        # Local 6 km2 network on full valid buffer.
        thcells=int(math.ceil(STREAM_THRESHOLD_KM2*1e6/cell_area))
        fat6=valid & (acc >= thcells)

        # GFA default ASk network on full valid buffer.
        slope=horn_slope_degree(dem,valid,rx,ry)
        sr=np.deg2rad(slope)
        criterion=acc*cell_area*np.power(sr+0.0001,1.7)
        ask_seed=valid & np.isfinite(criterion) & (criterion > 100000.0)
        ask=propagate(ask_seed,ptr,valid)

        results=[
            evaluate("GFA_channel_ASk",ask,dem,ptr,acc,valid,analysis,cell_area),
            evaluate("Local_FAt_6km2",fat6,dem,ptr,acc,valid,analysis,cell_area),
        ]

    out_json=OUT/"gfi_channel_method_comparison.json"
    out_csv=OUT/"gfi_channel_method_comparison.csv"
    with out_json.open("w",encoding="utf-8") as f:
        json.dump({
            "purpose":"compare module-default ASk against local 6km drainage for GFI/WD behaviour",
            "manual_threshold_normalized":MANUAL_THRESHOLD,
            "n_exponent":N_EXPONENT,
            "results":results,
        },f,indent=2)

    fields=["name","channel_cells_das","resolved_percent","negative_H_cells","zero_H_cells","gfi_raw_min","gfi_raw_max","raw_zero_norm_threshold","manual_prone_area_km2","manual_prone_negative_wd_percent","manual_prone_positive_wd_percent","physical_positive_wd_area_km2"]
    with out_csv.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for r in results: w.writerow({k:r.get(k) for k in fields})

    print("=== KURANJI GFI CHANNEL METHOD COMPARISON ===")
    print("method             chCells  resolved%  raw0_norm  prone_km2  WD+%   WD-%  physicalWD+km2")
    print("-----------------  -------  ---------  ---------  ---------  -----  -----  --------------")
    for r in results:
        print(f"{r['name']:<17} {r['channel_cells_das']:>7,}  {r['resolved_percent']:>9.3f}  {r['raw_zero_norm_threshold']:>9.6f}  {r['manual_prone_area_km2']:>9.3f}  {r['manual_prone_positive_wd_percent']:>5.1f}  {r['manual_prone_negative_wd_percent']:>5.1f}  {r['physical_positive_wd_area_km2']:>14.3f}")
    print("\nJSON:",out_json)
    print("CSV :",out_csv)

if __name__=="__main__":
    main()
