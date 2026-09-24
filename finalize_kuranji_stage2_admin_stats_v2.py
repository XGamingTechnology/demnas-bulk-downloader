#!/usr/bin/env python3
"""Finalize Kuranji Stage-2 administrative statistics (robust V2).

Primary scenario: P175.

Key improvements over V1
------------------------
- optional explicit admin input: --admin /path/to/file.shp
- scans the whole repository, not only data/
- tolerates values such as 'Kecamatan Pauh', 'Kec. Pauh', etc.
- detects kecamatan/kelurahan fields from values as well as field names
- prints diagnostic candidate/field information when auto-detection fails
- creates DAS, kecamatan, kelurahan and sensitivity CSV outputs
- copies P175 rasters into the Stage-2 final-candidate package

Usage
-----
python finalize_kuranji_stage2_admin_stats_v2.py
python finalize_kuranji_stage2_admin_stats_v2.py --admin /path/to/Kecamatan.shp
python finalize_kuranji_stage2_admin_stats_v2.py --list-admin
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.features import rasterize
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform, unary_union

ROOT = Path(__file__).resolve().parent
PREP = ROOT / "data/work/kuranji/01_prepared"
SENS = ROOT / "data/work/kuranji/12_fuzzy_hazard_sensitivity"
RAS_SRC = SENS / "rasters"
OUT = ROOT / "data/work/kuranji/13_stage2_final_candidate"
OUT_RAS = OUT / "raster"
OUT_VEC = OUT / "vector"
OUT_TAB = OUT / "table"
OUT_QC = OUT / "qc"
for d in [OUT_RAS, OUT_VEC, OUT_TAB, OUT_QC]:
    d.mkdir(parents=True, exist_ok=True)

DAS_PATH = PREP / "DAS_KURANJI_UTM47S.geojson"
PRIMARY = "P175"
SCENARIOS = ["M175", "M250", "P175", "P250"]
VECTOR_EXTS = {".shp", ".geojson", ".json", ".gpkg"}
TARGETS = {"PAUH", "KURANJI"}

KEC_FIELD_CANDIDATES = {
    "kecamatan", "wadmkc", "namkec", "kec", "district", "nama_kec",
    "nm_kec", "kec_name", "name_2", "name2",
}
KEL_FIELD_CANDIDATES = {
    "kelurahan", "wadmkd", "namkel", "desa", "namdes", "village", "namobj",
    "nama_kel", "nm_kel", "kel_name", "name_3", "name3",
}


def norm_text(v) -> str:
    if v is None:
        return ""
    s = str(v).strip().upper()
    s = re.sub(r"[._,/\\-]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def canonical_kecamatan(v):
    s = norm_text(v)
    if not s:
        return None
    # Robust to KECAMATAN PAUH, KEC PAUH, PAUH DISTRICT, etc.
    words = set(re.findall(r"[A-Z]+", s))
    for target in TARGETS:
        if target in words or s == target or s.endswith(" " + target) or s.startswith(target + " "):
            return target
    return None


def read_geojson(path: Path):
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    feats = []
    for ft in data.get("features", []):
        if not ft.get("geometry"):
            continue
        feats.append({
            "geometry": shape(ft["geometry"]),
            "properties": dict(ft.get("properties") or {}),
        })
    crs = None
    c = data.get("crs")
    if c and c.get("type") == "name":
        crs = c.get("properties", {}).get("name")
    return feats, crs


def read_vector(path: Path):
    if path.suffix.lower() in {".geojson", ".json"}:
        return read_geojson(path)
    try:
        import fiona
    except ImportError:
        raise RuntimeError("Fiona required. Install with: pip install 'fiona>=1.9'")
    feats = []
    with fiona.open(path) as src:
        crs = src.crs_wkt or src.crs
        for ft in src:
            if not ft.get("geometry"):
                continue
            feats.append({
                "geometry": shape(ft["geometry"]),
                "properties": dict(ft.get("properties") or {}),
            })
    return feats, crs


def candidate_vectors():
    out = []
    skip_parts = {".git", ".venv", "__pycache__"}
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in VECTOR_EXTS:
            continue
        if any(part in skip_parts for part in p.parts):
            continue
        s = str(p).lower()
        if "13_stage2_final_candidate" in s:
            continue
        score = 0
        n = p.name.lower()
        if "kecamatan" in n: score += 20
        if "kelurahan" in n: score += 20
        if "admin" in n: score += 10
        if "pauh" in n: score += 8
        if "kuranji" in n: score += 8
        if "batas" in n: score += 4
        if "desa" in n: score += 4
        out.append((score, p))
    out.sort(key=lambda x: (-x[0], len(str(x[1])), str(x[1]).lower()))
    return [p for _, p in out]


def property_keys(props):
    keys=[]; seen=set()
    for p in props:
        for k in p.keys():
            if k not in seen:
                seen.add(k); keys.append(k)
    return keys


def detect_kecamatan_field(props):
    keys = property_keys(props)
    # First: field values actually identify both PAUH and KURANJI.
    scored=[]
    for k in keys:
        vals=[canonical_kecamatan(p.get(k)) for p in props]
        found={v for v in vals if v}
        exact_name = 1 if k.lower() in KEC_FIELD_CANDIDATES else 0
        scored.append((len(found), exact_name, k, found))
    scored.sort(reverse=True)
    if scored and scored[0][0] >= 2:
        return scored[0][2]
    # If field name is highly suggestive, allow it only if at least one target appears.
    for found_count, exact_name, k, found in scored:
        if exact_name and found_count >= 1:
            return k
    return None


def detect_kelurahan_field(props, kec_field):
    keys = property_keys(props)
    ranked=[]
    for k in keys:
        if k == kec_field:
            continue
        vals=[norm_text(p.get(k)) for p in props]
        nonempty=[v for v in vals if v]
        uniq=set(nonempty)
        if not uniq:
            continue
        name_bonus = 100 if k.lower() in KEL_FIELD_CANDIDATES else 0
        # Prefer a meaningful text field varying across features but not near-unique numeric IDs.
        textish=sum(any(ch.isalpha() for ch in v) for v in nonempty)
        if len(uniq) < 2:
            continue
        if textish < max(2, len(nonempty)//3):
            continue
        ranked.append((name_bonus + min(len(uniq), 50), len(uniq), k))
    ranked.sort(reverse=True)
    return ranked[0][2] if ranked else None


def summarize_vector(path: Path, max_values=8):
    try:
        feats, crs = read_vector(path)
    except Exception as e:
        return {"path":str(path), "error":str(e)}
    props=[f["properties"] for f in feats]
    keys=property_keys(props) if props else []
    fields={}
    for k in keys[:30]:
        vals=[]; seen=set()
        for p in props:
            v=norm_text(p.get(k))
            if v and v not in seen:
                seen.add(v); vals.append(v)
            if len(vals)>=max_values: break
        fields[k]=vals
    return {"path":str(path), "features":len(feats), "crs":str(crs), "fields":fields}


def find_admin_source(explicit: Path | None = None):
    paths=[explicit] if explicit else candidate_vectors()
    diagnostics=[]
    for path in paths:
        if path is None:
            continue
        path=Path(path)
        if not path.exists():
            diagnostics.append({"path":str(path),"status":"missing"})
            continue
        try:
            feats, crs=read_vector(path)
        except Exception as e:
            diagnostics.append({"path":str(path),"status":f"read-error: {e}"})
            continue
        if not feats:
            diagnostics.append({"path":str(path),"status":"empty"})
            continue
        props=[f["properties"] for f in feats]
        kf=detect_kecamatan_field(props)
        if not kf:
            diagnostics.append({"path":str(path),"status":"no field containing both Pauh/Kuranji","summary":summarize_vector(path)})
            continue
        found={canonical_kecamatan(p.get(kf)) for p in props}
        found.discard(None)
        if not TARGETS.issubset(found):
            diagnostics.append({"path":str(path),"status":f"field {kf} only found {sorted(found)}","summary":summarize_vector(path)})
            continue
        kel=detect_kelurahan_field(props,kf)
        return path, feats, crs, kf, kel, diagnostics
    return None, None, None, None, None, diagnostics


def transformer_for(src_crs, dst_crs):
    if not src_crs:
        return None, "missing"
    try:
        src=CRS.from_user_input(src_crs)
        dst=CRS.from_user_input(dst_crs)
    except Exception as e:
        return None, f"invalid: {e}"
    if src == dst:
        return None, src.to_string()
    return Transformer.from_crs(src,dst,always_xy=True).transform, src.to_string()


def load_das():
    with DAS_PATH.open(encoding="utf-8") as f:
        data=json.load(f)
    geoms=[shape(ft["geometry"]) for ft in data.get("features",[]) if ft.get("geometry")]
    if not geoms:
        raise RuntimeError("No DAS geometry")
    return unary_union(geoms)


def write_geojson(path, features, crs_name):
    fc={"type":"FeatureCollection","name":path.stem,
        "crs":{"type":"name","properties":{"name":crs_name}},"features":[]}
    for geom,props in features:
        fc["features"].append({"type":"Feature","geometry":mapping(geom),"properties":props})
    with path.open("w",encoding="utf-8") as f:
        json.dump(fc,f,ensure_ascii=False,indent=2)


def class_stats(arr, mask, cell_area):
    zone=int(np.count_nonzero(mask))
    counts={c:int(np.count_nonzero(mask & (arr==c))) for c in [1,2,3]}
    haz=sum(counts.values())
    km2=lambda n:n*cell_area/1e6
    ha=lambda n:n*cell_area/1e4
    return {
        "zone_cells":zone,"zone_area_km2":km2(zone),"zone_area_ha":ha(zone),
        "hazard_cells":haz,"hazard_area_km2":km2(haz),"hazard_area_ha":ha(haz),
        "hazard_coverage_pct_zone":100*haz/zone if zone else 0.0,
        "low_cells":counts[1],"low_km2":km2(counts[1]),"low_ha":ha(counts[1]),
        "medium_cells":counts[2],"medium_km2":km2(counts[2]),"medium_ha":ha(counts[2]),
        "high_cells":counts[3],"high_km2":km2(counts[3]),"high_ha":ha(counts[3]),
        "low_pct_hazard":100*counts[1]/haz if haz else 0.0,
        "medium_pct_hazard":100*counts[2]/haz if haz else 0.0,
        "high_pct_hazard":100*counts[3]/haz if haz else 0.0,
        "low_pct_zone":100*counts[1]/zone if zone else 0.0,
        "medium_pct_zone":100*counts[2]/zone if zone else 0.0,
        "high_pct_zone":100*counts[3]/zone if zone else 0.0,
    }


def raster_mask(geom, ds, das_mask):
    m=rasterize([(geom,1)],out_shape=(ds.height,ds.width),transform=ds.transform,
                fill=0,all_touched=False,dtype="uint8").astype(bool)
    return m & das_mask


def write_csv(path, rows):
    if not rows:
        return
    fields=[]; seen=set()
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k); fields.append(k)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)


def print_admin_candidates():
    paths=candidate_vectors()
    print("=== ADMIN VECTOR CANDIDATES ===")
    if not paths:
        print("No .shp/.gpkg/.geojson/.json vectors found in repository.")
        return
    for i,p in enumerate(paths[:30],1):
        s=summarize_vector(p,max_values=5)
        print(f"\n[{i}] {p}")
        if "error" in s:
            print("    ERROR:",s["error"]); continue
        print(f"    features={s['features']} crs={s['crs']}")
        for k,v in list(s["fields"].items())[:12]:
            print(f"    {k}: {v}")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--admin",help="Explicit administrative vector (.shp/.gpkg/.geojson)")
    ap.add_argument("--list-admin",action="store_true",help="List candidate vectors and sample attributes, then exit")
    args=ap.parse_args()

    if args.list_admin:
        print_admin_candidates(); return

    primary_cls=RAS_SRC/f"{PRIMARY}_HAZARD_CLASS.tif"
    primary_hz=RAS_SRC/f"{PRIMARY}_HAZARD_INDEX.tif"
    primary_wd=RAS_SRC/f"{PRIMARY}_WD_INPUT.tif"
    for p in [DAS_PATH,primary_cls,primary_hz,primary_wd]:
        if not p.exists():
            raise FileNotFoundError(p)

    explicit=Path(args.admin).expanduser().resolve() if args.admin else None
    admin_path,feats,admin_crs,kec_field,kel_field,diagnostics=find_admin_source(explicit)
    if admin_path is None:
        print("\nERROR: Could not identify a vector containing BOTH Pauh and Kuranji.")
        print("\nCandidates tested:")
        for d in diagnostics[:20]:
            print(" -",d.get("path"),"=>",d.get("status"))
            sm=d.get("summary") or {}
            for k,v in list((sm.get("fields") or {}).items())[:8]:
                print(f"      {k}: {v}")
        print("\nRun this diagnostic command:")
        print("  python finalize_kuranji_stage2_admin_stats_v2.py --list-admin")
        print("\nIf you recognize the correct file, rerun with:")
        print("  python finalize_kuranji_stage2_admin_stats_v2.py --admin /FULL/PATH/TO/Kecamatan.shp")
        sys.exit(3)

    print("=== ADMIN SOURCE DETECTED ===")
    print("Path            :",admin_path)
    print("Features        :",len(feats))
    print("Kecamatan field :",kec_field)
    print("Kelurahan field :",kel_field or "<not detected>")
    print("Source CRS      :",admin_crs)

    with rasterio.open(primary_cls) as cds:
        cls=cds.read(1)
        cell_area=abs(cds.res[0]*cds.res[1])
        if not cds.crs:
            raise RuntimeError("Primary hazard raster lacks CRS")
        das_geom=load_das()
        das_mask=rasterize([(das_geom,1)],out_shape=(cds.height,cds.width),transform=cds.transform,
                           fill=0,all_touched=False,dtype="uint8").astype(bool)
        tf,src_crs_status=transformer_for(admin_crs,cds.crs)
        if admin_crs is None:
            # Conservative inference only when coordinates are unmistakably lon/lat.
            bounds=[]
            for ft in feats[:100]:
                bounds.append(ft["geometry"].bounds)
            if bounds:
                xs=[b[0] for b in bounds]+[b[2] for b in bounds]
                ys=[b[1] for b in bounds]+[b[3] for b in bounds]
                if max(map(abs,xs)) <= 180 and max(map(abs,ys)) <= 90:
                    tf=Transformer.from_crs("EPSG:4326",cds.crs,always_xy=True).transform
                    src_crs_status="assumed EPSG:4326 from geographic coordinate range"
                else:
                    raise RuntimeError("Admin CRS is missing and coordinates are not safely inferable as lon/lat")

        prepared=[]
        for ft in feats:
            kec=canonical_kecamatan(ft["properties"].get(kec_field))
            if kec not in TARGETS:
                continue
            geom=ft["geometry"]
            if tf:
                geom=shp_transform(tf,geom)
            if geom.is_empty:
                continue
            kel=norm_text(ft["properties"].get(kel_field)) if kel_field else ""
            prepared.append({"kecamatan":kec,"kelurahan":kel,"geometry":geom})

        if not prepared:
            raise RuntimeError("Admin source was detected, but no Pauh/Kuranji geometries remained after preparation")

        by_kel=defaultdict(list)
        unnamed=0
        for ft in prepared:
            kel=ft["kelurahan"]
            if not kel:
                unnamed+=1; kel=f"UNNAMED_{unnamed:02d}"
            by_kel[(ft["kecamatan"],kel)].append(ft["geometry"])
        kel_features=[(unary_union(gs),{"kecamatan":k,"kelurahan":kel})
                      for (k,kel),gs in sorted(by_kel.items())]

        by_kec=defaultdict(list)
        for geom,p in kel_features:
            by_kec[p["kecamatan"]].append(geom)
        kec_features=[(unary_union(gs),{"kecamatan":k}) for k,gs in sorted(by_kec.items())]

        crs_name=cds.crs.to_string()
        write_geojson(OUT_VEC/"ADMIN_KELURAHAN_PAUH_KURANJI_UTM47S.geojson",kel_features,crs_name)
        write_geojson(OUT_VEC/"ADMIN_KECAMATAN_PAUH_KURANJI_UTM47S.geojson",kec_features,crs_name)

        das_row={"unit_type":"DAS","unit_name":"DAS KURANJI","scenario":PRIMARY}
        das_row.update(class_stats(cls,das_mask,cell_area))
        write_csv(OUT_TAB/"hazard_stats_das.csv",[das_row])

        kec_rows=[]
        for geom,p in kec_features:
            row={"unit_type":"KECAMATAN","kecamatan":p["kecamatan"],"scenario":PRIMARY}
            row.update(class_stats(cls,raster_mask(geom,cds,das_mask),cell_area))
            kec_rows.append(row)
        write_csv(OUT_TAB/"hazard_stats_kecamatan.csv",kec_rows)

        kel_rows=[]
        for geom,p in kel_features:
            row={"unit_type":"KELURAHAN","kecamatan":p["kecamatan"],"kelurahan":p["kelurahan"],"scenario":PRIMARY}
            row.update(class_stats(cls,raster_mask(geom,cds,das_mask),cell_area))
            kel_rows.append(row)
        write_csv(OUT_TAB/"hazard_stats_kelurahan.csv",kel_rows)

        sens_das=[]; sens_kec=[]
        for sc in SCENARIOS:
            pth=RAS_SRC/f"{sc}_HAZARD_CLASS.tif"
            if not pth.exists():
                continue
            with rasterio.open(pth) as sds:
                if sds.width!=cds.width or sds.height!=cds.height or sds.crs!=cds.crs or not sds.transform.almost_equals(cds.transform):
                    raise RuntimeError(f"Scenario raster {sc} is not aligned")
                arr=sds.read(1)
            r={"unit_type":"DAS","unit_name":"DAS KURANJI","scenario":sc}
            r.update(class_stats(arr,das_mask,cell_area)); sens_das.append(r)
            for geom,p in kec_features:
                rr={"unit_type":"KECAMATAN","kecamatan":p["kecamatan"],"scenario":sc}
                rr.update(class_stats(arr,raster_mask(geom,cds,das_mask),cell_area)); sens_kec.append(rr)
        write_csv(OUT_TAB/"sensitivity_das.csv",sens_das)
        write_csv(OUT_TAB/"sensitivity_kecamatan.csv",sens_kec)

    # Freeze/copy primary rasters only after all statistics succeed.
    for src,dst in [
        (primary_wd,OUT_RAS/"P175_WD_INPUT.tif"),
        (primary_hz,OUT_RAS/"P175_HAZARD_INDEX.tif"),
        (primary_cls,OUT_RAS/"P175_HAZARD_CLASS.tif"),
    ]:
        shutil.copy2(src,dst)

    qc={
        "primary_scenario":PRIMARY,
        "status":"baseline hazard candidate; external validation pending",
        "admin_source":str(admin_path),
        "admin_source_crs":str(admin_crs),
        "admin_crs_handling":src_crs_status,
        "kecamatan_field":kec_field,
        "kelurahan_field":kel_field,
        "input_features":len(feats),
        "prepared_pauh_kuranji_features":len(prepared),
        "kelurahan_units":len(kel_features),
        "kecamatan_units":[p["kecamatan"] for _,p in kec_features],
        "cell_area_m2":cell_area,
    }
    with (OUT_QC/"stage2_admin_stats_qc.json").open("w",encoding="utf-8") as f:
        json.dump(qc,f,indent=2,ensure_ascii=False)

    readme=f"""# KURANJI STAGE 2 FINAL CANDIDATE PACKAGE\n\nPrimary scenario: P175.\nStatus: baseline hazard candidate; external validation pending.\nAdministrative source: {admin_path}\nKecamatan field: {kec_field}\nKelurahan field: {kel_field}\nKelurahan units detected: {len(kel_features)}\n\nPrimary raster products and administrative tables are in raster/, vector/, table/, qc/.\nSensitivity scenarios remain in data/work/kuranji/12_fuzzy_hazard_sensitivity/.\n"""
    (OUT/"README_STAGE2_FINAL_CANDIDATE.md").write_text(readme,encoding="utf-8")

    print("\n=== DAS P175 ===")
    print(f"DAS area raster : {das_row['zone_area_km2']:.3f} km2")
    print(f"Hazard area     : {das_row['hazard_area_km2']:.3f} km2 ({das_row['hazard_coverage_pct_zone']:.2f}% DAS raster)")
    print(f"Low             : {das_row['low_km2']:.3f} km2 ({das_row['low_pct_hazard']:.2f}% hazard)")
    print(f"Medium          : {das_row['medium_km2']:.3f} km2 ({das_row['medium_pct_hazard']:.2f}% hazard)")
    print(f"High            : {das_row['high_km2']:.3f} km2 ({das_row['high_pct_hazard']:.2f}% hazard)")

    print("\n=== KECAMATAN P175 ===")
    for r in sorted(kec_rows,key=lambda x:x['kecamatan']):
        print(f"{r['kecamatan']:<10} zone={r['zone_area_km2']:.3f} km2 | hazard={r['hazard_area_km2']:.3f} | low={r['low_km2']:.3f} med={r['medium_km2']:.3f} high={r['high_km2']:.3f}")

    print("\n=== TOP KELURAHAN BY HIGH HAZARD AREA ===")
    for i,r in enumerate(sorted(kel_rows,key=lambda x:x['high_km2'],reverse=True)[:15],1):
        print(f"{i:>2}. {r['kecamatan']} / {r['kelurahan']}: high={r['high_km2']:.3f} km2 | hazard={r['hazard_area_km2']:.3f} km2 | high_zone={r['high_pct_zone']:.2f}%")

    print("\nOutput:",OUT)
    print("Admin source used:",admin_path)


if __name__ == "__main__":
    main()
