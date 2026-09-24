#!/usr/bin/env python3
"""Finalize Stage-2 administrative statistics for DAS Batang Kuranji.

Primary reporting product
-------------------------
P175 = physical-positive flood-prone domain (WD > 0) + Fuzzy Large spread 1.75.
This is the Stage-2 baseline hazard candidate, not yet an externally calibrated
final hazard map.

The script:
1. loads P175 hazard class (1 low, 2 medium, 3 high);
2. finds the local administrative vector under data/ (the historical upload named
   Kecamatan.shp may actually contain kelurahan features);
3. identifies kecamatan/kelurahan attribute fields heuristically;
4. reprojects geometries to the hazard raster CRS if needed;
5. calculates full-DAS, Pauh, Kuranji, and per-kelurahan statistics;
6. creates map-ready GeoJSON boundaries for Pauh/Kuranji and kelurahan;
7. exports sensitivity summaries for M175/M250/P175/P250;
8. writes a Stage-2 final-candidate package directory.

Requirements already expected in this project:
- rasterio
- shapely
- pyproj

For Shapefile/GPKG input, Fiona is required. If it is not installed, the script
prints an exact installation command and exits without modifying analysis files.
GeoJSON input works without Fiona.

Outputs
-------
data/work/kuranji/13_stage2_final_candidate/
  raster/
    P175_WD_INPUT.tif
    P175_HAZARD_INDEX.tif
    P175_HAZARD_CLASS.tif
  vector/
    ADMIN_KELURAHAN_PAUH_KURANJI_UTM47S.geojson
    ADMIN_KECAMATAN_PAUH_KURANJI_UTM47S.geojson
  table/
    hazard_stats_das.csv
    hazard_stats_kecamatan.csv
    hazard_stats_kelurahan.csv
    sensitivity_das.csv
    sensitivity_kecamatan.csv
  qc/
    stage2_admin_stats_qc.json
  README_STAGE2_FINAL_CANDIDATE.md
"""

from __future__ import annotations

import csv
import json
import math
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from shapely.geometry import shape, mapping
from shapely.ops import transform as shp_transform, unary_union
from pyproj import CRS, Transformer

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

KEC_FIELD_CANDIDATES = [
    "KECAMATAN", "kecamatan", "WADMKC", "wadmkc", "NAMKEC", "namkec",
    "KEC", "kec", "DISTRICT", "district", "Kecamatan",
]
KEL_FIELD_CANDIDATES = [
    "KELURAHAN", "kelurahan", "WADMKD", "wadmkd", "NAMKEL", "namkel",
    "DESA", "desa", "NAMDES", "namdes", "VILLAGE", "village",
    "NAMOBJ", "namobj", "Kelurahan",
]
TARGET_KEC = {"PAUH", "KURANJI"}
VECTOR_EXTS = {".shp", ".geojson", ".json", ".gpkg"}


def read_geojson(path: Path):
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    feats = []
    for ft in data.get("features", []):
        if not ft.get("geometry"):
            continue
        feats.append({"geometry": shape(ft["geometry"]), "properties": dict(ft.get("properties") or {})})
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
        print("ERROR: Administrative input is a Shapefile/GPKG but Fiona is not installed.")
        print("Install once inside the venv with:")
        print("  pip install 'fiona>=1.9'")
        print("Then rerun this script.")
        sys.exit(2)
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


def norm_text(v):
    if v is None:
        return ""
    return " ".join(str(v).strip().upper().split())


def detect_field(properties_list, candidates, expected_values=None):
    keys = []
    seen = set()
    for p in properties_list:
        for k in p.keys():
            if k not in seen:
                seen.add(k); keys.append(k)
    # Exact candidate names first.
    lowmap = {k.lower(): k for k in keys}
    for c in candidates:
        if c.lower() in lowmap:
            return lowmap[c.lower()]
    # Then choose field containing expected values Pauh/Kuranji if requested.
    if expected_values:
        best = None
        best_count = 0
        for k in keys:
            vals = {norm_text(p.get(k)) for p in properties_list}
            count = len(set(expected_values) & vals)
            if count > best_count:
                best_count = count; best = k
        if best_count >= 1:
            return best
    return None


def candidate_admin_files():
    data = ROOT / "data"
    out = []
    if not data.exists():
        return out
    for p in data.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in VECTOR_EXTS:
            continue
        s = str(p).lower()
        if "13_stage2_final_candidate" in s:
            continue
        score = 0
        n = p.name.lower()
        if "kecamatan" in n: score += 8
        if "kelurahan" in n: score += 8
        if "admin" in n: score += 4
        if "kuranji" in n or "pauh" in n: score += 2
        out.append((score, p))
    out.sort(key=lambda x: (-x[0], len(str(x[1])), str(x[1])))
    return [p for _, p in out]


def find_admin_source():
    tested = []
    for path in candidate_admin_files():
        try:
            feats, crs = read_vector(path)
        except SystemExit:
            raise
        except Exception as e:
            tested.append((str(path), f"read-error: {e}"))
            continue
        if not feats:
            tested.append((str(path), "empty")); continue
        props = [f["properties"] for f in feats]
        kf = detect_field(props, KEC_FIELD_CANDIDATES, TARGET_KEC)
        if not kf:
            tested.append((str(path), "no kecamatan-like field")); continue
        vals = {norm_text(p.get(kf)) for p in props}
        if not TARGET_KEC.issubset(vals):
            tested.append((str(path), f"field {kf} missing Pauh/Kuranji")); continue
        kel = detect_field(props, KEL_FIELD_CANDIDATES)
        # Require a second varying field for kelurahan when possible.
        if kel == kf:
            kel = None
        if not kel:
            # pick a text-like field with many unique non-empty values.
            keys = list(props[0].keys())
            best, bestn = None, 0
            for k in keys:
                if k == kf: continue
                vv = {norm_text(p.get(k)) for p in props if norm_text(p.get(k))}
                if 5 <= len(vv) <= max(200, len(props)) and len(vv) > bestn:
                    best, bestn = k, len(vv)
            kel = best
        return path, feats, crs, kf, kel, tested
    raise RuntimeError("Could not automatically find an administrative vector containing both PAUH and KURANJI")


def transformer_for(src_crs, dst_crs):
    if not src_crs:
        return None
    try:
        src = CRS.from_user_input(src_crs)
        dst = CRS.from_user_input(dst_crs)
    except Exception:
        return None
    if src == dst:
        return None
    return Transformer.from_crs(src, dst, always_xy=True).transform


def write_geojson(path: Path, features, crs_name):
    fc = {
        "type": "FeatureCollection",
        "name": path.stem,
        "crs": {"type":"name", "properties":{"name":crs_name}},
        "features": [],
    }
    for geom, props in features:
        fc["features"].append({"type":"Feature", "geometry":mapping(geom), "properties":props})
    with path.open("w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=2)


def load_das():
    with DAS_PATH.open(encoding="utf-8") as f:
        data=json.load(f)
    geoms=[shape(ft["geometry"]) for ft in data.get("features",[]) if ft.get("geometry")]
    if not geoms: raise RuntimeError("No DAS geometry")
    return unary_union(geoms)


def class_stats(class_arr, zone_mask, cell_area):
    zone_cells = int(np.count_nonzero(zone_mask))
    counts = {c:int(np.count_nonzero(zone_mask & (class_arr == c))) for c in [1,2,3]}
    hazard_cells = sum(counts.values())
    def km2(n): return n*cell_area/1e6
    def ha(n): return n*cell_area/1e4
    return {
        "zone_cells": zone_cells,
        "zone_area_km2": km2(zone_cells),
        "zone_area_ha": ha(zone_cells),
        "hazard_cells": hazard_cells,
        "hazard_area_km2": km2(hazard_cells),
        "hazard_area_ha": ha(hazard_cells),
        "hazard_coverage_pct_zone": 100*hazard_cells/zone_cells if zone_cells else 0.0,
        "low_cells": counts[1], "low_km2": km2(counts[1]), "low_ha": ha(counts[1]),
        "medium_cells": counts[2], "medium_km2": km2(counts[2]), "medium_ha": ha(counts[2]),
        "high_cells": counts[3], "high_km2": km2(counts[3]), "high_ha": ha(counts[3]),
        "low_pct_hazard": 100*counts[1]/hazard_cells if hazard_cells else 0.0,
        "medium_pct_hazard": 100*counts[2]/hazard_cells if hazard_cells else 0.0,
        "high_pct_hazard": 100*counts[3]/hazard_cells if hazard_cells else 0.0,
        "low_pct_zone": 100*counts[1]/zone_cells if zone_cells else 0.0,
        "medium_pct_zone": 100*counts[2]/zone_cells if zone_cells else 0.0,
        "high_pct_zone": 100*counts[3]/zone_cells if zone_cells else 0.0,
    }


def raster_mask(geom, ref, das_mask):
    m = rasterize([(geom,1)], out_shape=(ref.height,ref.width), transform=ref.transform,
                  fill=0, all_touched=False, dtype="uint8").astype(bool)
    return m & das_mask


def write_csv(path, rows):
    if not rows:
        return
    fields=[]; seen=set()
    for row in rows:
        for k in row.keys():
            if k not in seen:
                seen.add(k); fields.append(k)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)


def main():
    primary_cls = RAS_SRC / f"{PRIMARY}_HAZARD_CLASS.tif"
    primary_hz = RAS_SRC / f"{PRIMARY}_HAZARD_INDEX.tif"
    primary_wd = RAS_SRC / f"{PRIMARY}_WD_INPUT.tif"
    for p in [DAS_PATH, primary_cls, primary_hz, primary_wd]:
        if not p.exists(): raise FileNotFoundError(p)

    admin_path, feats, admin_crs, kec_field, kel_field, tested = find_admin_source()

    with rasterio.open(primary_cls) as cds:
        cls = cds.read(1)
        cell_area = abs(cds.res[0]*cds.res[1])
        target_crs = cds.crs
        if not target_crs: raise RuntimeError("Primary hazard raster lacks CRS")
        das_geom = load_das()
        das_mask = rasterize([(das_geom,1)],out_shape=(cds.height,cds.width),transform=cds.transform,
                             fill=0,all_touched=False,dtype="uint8").astype(bool)
        tf = transformer_for(admin_crs, target_crs)

        prepared=[]
        for ft in feats:
            kec = norm_text(ft["properties"].get(kec_field))
            if kec not in TARGET_KEC:
                continue
            geom=ft["geometry"]
            if tf: geom=shp_transform(tf,geom)
            if geom.is_empty: continue
            kel = norm_text(ft["properties"].get(kel_field)) if kel_field else ""
            prepared.append({"kecamatan":kec,"kelurahan":kel,"geometry":geom,"properties":ft["properties"]})

        if not prepared:
            raise RuntimeError("No Pauh/Kuranji admin features found after preparation")

        # Dissolve repeated kelurahan features if any.
        by_kel=defaultdict(list)
        for ft in prepared:
            key=(ft["kecamatan"],ft["kelurahan"] or f"UNNAMED_{len(by_kel)+1}")
            by_kel[key].append(ft["geometry"])
        kel_features=[]
        for (kec,kel),gs in sorted(by_kel.items()):
            kel_features.append((unary_union(gs), {"kecamatan":kec,"kelurahan":kel}))

        by_kec=defaultdict(list)
        for geom,p in kel_features:
            by_kec[p["kecamatan"]].append(geom)
        kec_features=[]
        for kec,gs in sorted(by_kec.items()):
            kec_features.append((unary_union(gs),{"kecamatan":kec}))

        crs_name=target_crs.to_string()
        write_geojson(OUT_VEC/"ADMIN_KELURAHAN_PAUH_KURANJI_UTM47S.geojson",kel_features,crs_name)
        write_geojson(OUT_VEC/"ADMIN_KECAMATAN_PAUH_KURANJI_UTM47S.geojson",kec_features,crs_name)

        # Full DAS primary stats.
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

        # Sensitivity by DAS + kecamatan.
        sens_das=[]; sens_kec=[]
        for sc in SCENARIOS:
            pth=RAS_SRC/f"{sc}_HAZARD_CLASS.tif"
            if not pth.exists():
                continue
            with rasterio.open(pth) as ds:
                if ds.width!=cds.width or ds.height!=cds.height or ds.crs!=cds.crs or not ds.transform.almost_equals(cds.transform):
                    raise RuntimeError(f"Scenario grid mismatch: {sc}")
                a=ds.read(1)
            row={"scenario":sc,"unit_type":"DAS","unit_name":"DAS KURANJI"}
            row.update(class_stats(a,das_mask,cell_area)); sens_das.append(row)
            for geom,p in kec_features:
                rr={"scenario":sc,"unit_type":"KECAMATAN","kecamatan":p["kecamatan"]}
                rr.update(class_stats(a,raster_mask(geom,cds,das_mask),cell_area)); sens_kec.append(rr)
        write_csv(OUT_TAB/"sensitivity_das.csv",sens_das)
        write_csv(OUT_TAB/"sensitivity_kecamatan.csv",sens_kec)

        # Copy exact primary rasters to frozen package.
        shutil.copy2(primary_wd, OUT_RAS/"P175_WD_INPUT.tif")
        shutil.copy2(primary_hz, OUT_RAS/"P175_HAZARD_INDEX.tif")
        shutil.copy2(primary_cls, OUT_RAS/"P175_HAZARD_CLASS.tif")

        # QC / reconciliation.
        combined_admin = unary_union([g for g,_ in kec_features])
        combined_mask = raster_mask(combined_admin,cds,das_mask)
        qc={
            "status":"Stage-2 baseline hazard candidate package",
            "primary_scenario":PRIMARY,
            "validation_status":"not yet externally calibrated/validated; Stage 3 required",
            "admin_source":str(admin_path.relative_to(ROOT) if ROOT in admin_path.parents else admin_path),
            "admin_source_crs":str(admin_crs),
            "hazard_crs":crs_name,
            "kecamatan_field":kec_field,
            "kelurahan_field":kel_field,
            "selected_admin_features":len(prepared),
            "dissolved_kelurahan_count":len(kel_features),
            "dissolved_kecamatan_count":len(kec_features),
            "kecamatan_names":[p["kecamatan"] for _,p in kec_features],
            "das_area_raster_km2":float(np.count_nonzero(das_mask)*cell_area/1e6),
            "p17_hazard_area_das_km2":das_row["hazard_area_km2"],
            "p17_low_km2":das_row["low_km2"],
            "p17_medium_km2":das_row["medium_km2"],
            "p17_high_km2":das_row["high_km2"],
            "pauh_kuranji_combined_area_in_das_km2":float(np.count_nonzero(combined_mask)*cell_area/1e6),
            "admin_candidate_files_tested_before_selection":tested,
            "notes":[
                "Class 1=low, 2=medium, 3=high.",
                "Class percentages are reported both relative to hazard area and to the full administrative area within the DAS.",
                "P175 is a baseline hazard candidate and must be externally validated in Stage 3.",
            ],
        }
        with (OUT_QC/"stage2_admin_stats_qc.json").open("w",encoding="utf-8") as f:
            json.dump(qc,f,ensure_ascii=False,indent=2)

    readme=f"""# KURANJI STAGE 2 FINAL CANDIDATE PACKAGE

Primary scenario: P175

Status: baseline hazard candidate, pending Stage-3 external validation.

Primary method
- conditioned DEM: BREACH100
- drainage network: local channel_FAt, 6 km2 minimum contributing area
- GFI: ln(hr/H), following audited GFA active logic
- flood-prone primary domain: WD > 0 / GFI_raw > 0
- WD: hr - H
- Fuzzy Large midpoint: 1.125 m
- Fuzzy Large spread: 1.75
- hazard index classes: low <=0.333; medium >0.333 to <=0.666; high >0.666

Administrative source detected
- {admin_path}
- kecamatan field: {kec_field}
- kelurahan field: {kel_field}

Tables
- hazard_stats_das.csv
- hazard_stats_kecamatan.csv
- hazard_stats_kelurahan.csv
- sensitivity_das.csv
- sensitivity_kecamatan.csv

Map-ready vectors
- ADMIN_KECAMATAN_PAUH_KURANJI_UTM47S.geojson
- ADMIN_KELURAHAN_PAUH_KURANJI_UTM47S.geojson

Frozen primary rasters
- P175_WD_INPUT.tif
- P175_HAZARD_INDEX.tif
- P175_HAZARD_CLASS.tif

Do not call P175 a final calibrated hazard until Stage-3 validation against independent observed flood data is complete.
"""
    with (OUT/"README_STAGE2_FINAL_CANDIDATE.md").open("w",encoding="utf-8") as f:
        f.write(readme)

    print("=== KURANJI STAGE 2 ADMIN STATS ===")
    print(f"Admin source      : {admin_path}")
    print(f"Kecamatan field   : {kec_field}")
    print(f"Kelurahan field   : {kel_field}")
    print(f"Kelurahan selected: {len(kel_features)}")
    print()
    print("DAS P175")
    print(f"  hazard area : {das_row['hazard_area_km2']:.3f} km2 ({das_row['hazard_coverage_pct_zone']:.2f}% DAS raster area)")
    print(f"  low         : {das_row['low_km2']:.3f} km2 ({das_row['low_pct_hazard']:.2f}% hazard)")
    print(f"  medium      : {das_row['medium_km2']:.3f} km2 ({das_row['medium_pct_hazard']:.2f}% hazard)")
    print(f"  high        : {das_row['high_km2']:.3f} km2 ({das_row['high_pct_hazard']:.2f}% hazard)")
    print("\nKECAMATAN P175")
    for r in kec_rows:
        print(f"  {r['kecamatan']:<10} zone={r['zone_area_km2']:.3f} km2 hazard={r['hazard_area_km2']:.3f} km2 "
              f"low={r['low_km2']:.3f} med={r['medium_km2']:.3f} high={r['high_km2']:.3f}")
    print("\nTop kelurahan by HIGH hazard area")
    for r in sorted(kel_rows,key=lambda x:x['high_km2'],reverse=True)[:10]:
        print(f"  {r['kecamatan']:<8} | {r['kelurahan']:<25} high={r['high_km2']:.3f} km2 "
              f"({r['high_pct_zone']:.2f}% zone)")
    print("\nOutput:",OUT)
    print("QC    :",OUT_QC/"stage2_admin_stats_qc.json")


if __name__ == "__main__":
    main()
