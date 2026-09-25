#!/usr/bin/env python3
"""Finalize Kuranji Stage-2 administrative hazard statistics, V3.

Design
------
Whole-DAS administrative analysis uses the detailed Sumatera_Barat.shp master layer:
  WADMPR = province
  WADMKK = kabupaten/kota
  WADMKC = kecamatan
  WADMKD = desa/kelurahan

Focus-area analysis retains Pauh + Kuranji as the research focus because they cover
~77.74% of the official DAS. The secondary Kecamatan.shp is used to retain all
18 focus kelurahan features, including those with zero DAS intersection.

Primary hazard scenario: P175.
Sensitivity scenarios: M175, M250, P175, P250.

Outputs
-------
data/work/kuranji/14_stage2_admin_final/
  table/
    hazard_stats_das.csv
    hazard_stats_kabkota.csv
    hazard_stats_kecamatan_all.csv
    hazard_stats_kelurahan_all_intersecting.csv
    hazard_stats_focus_kecamatan.csv
    hazard_stats_focus_kelurahan_18.csv
    sensitivity_das.csv
    sensitivity_kecamatan_all.csv
  vector/
    ADMIN_ALL_INTERSECTING_UTM47S.geojson
    ADMIN_FOCUS_PAUH_KURANJI_18_UTM47S.geojson
  raster/
    P175_WD_INPUT.tif
    P175_HAZARD_INDEX.tif
    P175_HAZARD_CLASS.tif
  qc/
    stage2_admin_final_qc.json
  README_STAGE2_ADMIN_FINAL.md
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path

import fiona
import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.features import rasterize
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform, unary_union

ROOT = Path(__file__).resolve().parent
DAS_PATH = ROOT / "data/work/kuranji/01_prepared/DAS_KURANJI_UTM47S.geojson"
RAS_SRC = ROOT / "data/work/kuranji/12_fuzzy_hazard_sensitivity/rasters"
OUT = ROOT / "data/work/kuranji/14_stage2_admin_final"
OUT_TAB = OUT / "table"
OUT_VEC = OUT / "vector"
OUT_RAS = OUT / "raster"
OUT_QC = OUT / "qc"
for d in [OUT_TAB, OUT_VEC, OUT_RAS, OUT_QC]:
    d.mkdir(parents=True, exist_ok=True)

PRIMARY = "P175"
SCENARIOS = ["M175", "M250", "P175", "P250"]
TARGET_CRS = CRS.from_epsg(32747)
FOCUS_KEC = {"PAUH", "KURANJI"}


def norm(v):
    return " ".join(str(v or "").strip().upper().split())


def read_das():
    with DAS_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    geoms = [shape(ft["geometry"]) for ft in data.get("features", []) if ft.get("geometry")]
    if not geoms:
        raise RuntimeError("No DAS geometry")
    return unary_union(geoms)


def transformer(src_crs):
    src = CRS.from_user_input(src_crs)
    if src == TARGET_CRS:
        return None
    return Transformer.from_crs(src, TARGET_CRS, always_xy=True).transform


def read_admin(path: Path, require_master=False):
    with fiona.open(path) as src:
        fields = list(src.schema.get("properties", {}).keys())
        if require_master:
            missing = [x for x in ["WADMPR","WADMKK","WADMKC","WADMKD"] if x not in fields]
            if missing:
                raise RuntimeError(f"Master admin missing fields {missing}")
        tf = transformer(src.crs_wkt or src.crs)
        rows=[]
        for i,ft in enumerate(src,1):
            if not ft.get("geometry"):
                continue
            g=shape(ft["geometry"])
            if tf:
                g=shp_transform(tf,g)
            p=dict(ft.get("properties") or {})
            rows.append({"index":i,"geometry":g,"properties":p})
        return rows, fields, str(src.crs_wkt or src.crs)


def write_csv(path: Path, rows):
    if not rows:
        return
    fields=[]; seen=set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k); fields.append(k)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)


def write_geojson(path: Path, features):
    fc={"type":"FeatureCollection","name":path.stem,
        "crs":{"type":"name","properties":{"name":"EPSG:32747"}},"features":[]}
    for geom,props in features:
        fc["features"].append({"type":"Feature","geometry":mapping(geom),"properties":props})
    with path.open("w",encoding="utf-8") as f:
        json.dump(fc,f,ensure_ascii=False,indent=2)


def zone_mask(geom, ds, das_mask):
    m=rasterize([(geom,1)],out_shape=(ds.height,ds.width),transform=ds.transform,
                fill=0,all_touched=False,dtype="uint8").astype(bool)
    return m & das_mask


def class_stats(arr, mask, cell_area):
    zone=int(np.count_nonzero(mask))
    counts={c:int(np.count_nonzero(mask & (arr==c))) for c in [1,2,3]}
    hz=sum(counts.values())
    km2=lambda n:n*cell_area/1e6
    ha=lambda n:n*cell_area/1e4
    return {
        "zone_cells":zone,
        "zone_area_km2":km2(zone),
        "zone_area_ha":ha(zone),
        "hazard_cells":hz,
        "hazard_area_km2":km2(hz),
        "hazard_area_ha":ha(hz),
        "hazard_coverage_pct_zone":100*hz/zone if zone else 0.0,
        "low_cells":counts[1],"low_km2":km2(counts[1]),"low_ha":ha(counts[1]),
        "medium_cells":counts[2],"medium_km2":km2(counts[2]),"medium_ha":ha(counts[2]),
        "high_cells":counts[3],"high_km2":km2(counts[3]),"high_ha":ha(counts[3]),
        "low_pct_hazard":100*counts[1]/hz if hz else 0.0,
        "medium_pct_hazard":100*counts[2]/hz if hz else 0.0,
        "high_pct_hazard":100*counts[3]/hz if hz else 0.0,
        "low_pct_zone":100*counts[1]/zone if zone else 0.0,
        "medium_pct_zone":100*counts[2]/zone if zone else 0.0,
        "high_pct_zone":100*counts[3]/zone if zone else 0.0,
    }


def dissolve_master(master_rows, das):
    # Keep only polygon pieces intersecting official DAS.
    all_features=[]
    by_kel=defaultdict(list)
    for r in master_rows:
        p=r["properties"]
        g=r["geometry"]
        if g.is_empty or not g.intersects(das):
            continue
        inter=g.intersection(das)
        if inter.is_empty or inter.area <= 0:
            continue
        pr=norm(p.get("WADMPR")); kab=norm(p.get("WADMKK")); kec=norm(p.get("WADMKC")); kel=norm(p.get("WADMKD"))
        key=(pr,kab,kec,kel)
        by_kel[key].append(g)

    kel_features=[]
    for (pr,kab,kec,kel),gs in sorted(by_kel.items()):
        geom=unary_union(gs)
        kel_features.append((geom,{"WADMPR":pr,"WADMKK":kab,"WADMKC":kec,"WADMKD":kel}))

    by_kec=defaultdict(list)
    by_kab=defaultdict(list)
    for geom,p in kel_features:
        by_kec[(p["WADMPR"],p["WADMKK"],p["WADMKC"])].append(geom)
        by_kab[(p["WADMPR"],p["WADMKK"])].append(geom)

    kec_features=[]
    for (pr,kab,kec),gs in sorted(by_kec.items()):
        kec_features.append((unary_union(gs),{"WADMPR":pr,"WADMKK":kab,"WADMKC":kec}))
    kab_features=[]
    for (pr,kab),gs in sorted(by_kab.items()):
        kab_features.append((unary_union(gs),{"WADMPR":pr,"WADMKK":kab}))
    return kab_features,kec_features,kel_features


def focus_secondary_features(rows):
    # Preserve all focus features, even if they do not intersect the DAS.
    out=[]
    for r in rows:
        p=r["properties"]
        kec=norm(p.get("WADMKC")); kel=norm(p.get("WADMKD"))
        if kec not in FOCUS_KEC:
            continue
        out.append((r["geometry"],{
            "WADMPR":norm(p.get("WADMPR")),
            "WADMKK":norm(p.get("WADMKK")),
            "WADMKC":kec,
            "WADMKD":kel,
            "KDPPUM":norm(p.get("KDPPUM")),
            "KDEBPS":norm(p.get("KDEBPS")),
        }))
    out.sort(key=lambda x:(x[1]["WADMKC"],x[1]["WADMKD"]))
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--master",default=str(ROOT/"data shp/data_administrasi/Sumatera_Barat.shp"))
    ap.add_argument("--focus",default=str(ROOT/"data shp/data_administrasi/Kecamatan.shp"))
    args=ap.parse_args()

    master_path=Path(args.master); focus_path=Path(args.focus)
    for p in [master_path,focus_path,DAS_PATH]:
        if not p.exists(): raise FileNotFoundError(p)
    for sc in SCENARIOS:
        p=RAS_SRC/f"{sc}_HAZARD_CLASS.tif"
        if not p.exists(): raise FileNotFoundError(p)

    das=read_das()
    master_rows,master_fields,master_crs=read_admin(master_path,True)
    focus_rows,focus_fields,focus_crs=read_admin(focus_path,False)
    kab_features,kec_features,kel_features=dissolve_master(master_rows,das)
    focus_features=focus_secondary_features(focus_rows)

    if len(focus_features) != 18:
        print(f"WARNING: expected 18 focus features, found {len(focus_features)}")

    primary_path=RAS_SRC/f"{PRIMARY}_HAZARD_CLASS.tif"
    with rasterio.open(primary_path) as cds:
        if cds.crs != TARGET_CRS:
            raise RuntimeError(f"Primary raster CRS is {cds.crs}, expected EPSG:32747")
        cls=cds.read(1)
        cell_area=abs(cds.res[0]*cds.res[1])
        das_mask=rasterize([(das,1)],out_shape=(cds.height,cds.width),transform=cds.transform,
                           fill=0,all_touched=False,dtype="uint8").astype(bool)

        # DAS
        das_row={"unit_type":"DAS","unit_name":"DAS KURANJI","scenario":PRIMARY}
        das_row.update(class_stats(cls,das_mask,cell_area))
        write_csv(OUT_TAB/"hazard_stats_das.csv",[das_row])

        # kab/kota
        kab_rows=[]
        for geom,p in kab_features:
            m=zone_mask(geom,cds,das_mask)
            row={"unit_type":"KABKOTA","WADMPR":p["WADMPR"],"WADMKK":p["WADMKK"],"scenario":PRIMARY}
            row.update(class_stats(cls,m,cell_area)); kab_rows.append(row)
        kab_rows.sort(key=lambda r:r["zone_area_km2"],reverse=True)
        write_csv(OUT_TAB/"hazard_stats_kabkota.csv",kab_rows)

        # all intersecting kecamatan
        kec_rows=[]
        for geom,p in kec_features:
            m=zone_mask(geom,cds,das_mask)
            row={"unit_type":"KECAMATAN","WADMPR":p["WADMPR"],"WADMKK":p["WADMKK"],"WADMKC":p["WADMKC"],
                 "focus_area":p["WADMKC"] in FOCUS_KEC,"scenario":PRIMARY}
            row.update(class_stats(cls,m,cell_area)); kec_rows.append(row)
        kec_rows.sort(key=lambda r:r["zone_area_km2"],reverse=True)
        write_csv(OUT_TAB/"hazard_stats_kecamatan_all.csv",kec_rows)

        # all intersecting kelurahan/desa from master
        kel_rows=[]
        for geom,p in kel_features:
            m=zone_mask(geom,cds,das_mask)
            row={"unit_type":"KELURAHAN_DESA","WADMPR":p["WADMPR"],"WADMKK":p["WADMKK"],"WADMKC":p["WADMKC"],"WADMKD":p["WADMKD"],
                 "focus_area":p["WADMKC"] in FOCUS_KEC,"scenario":PRIMARY}
            row.update(class_stats(cls,m,cell_area)); kel_rows.append(row)
        kel_rows.sort(key=lambda r:(r["WADMKK"],r["WADMKC"],r["WADMKD"]))
        write_csv(OUT_TAB/"hazard_stats_kelurahan_all_intersecting.csv",kel_rows)

        # focus kecamatan from master (dissolved)
        focus_kec_rows=[r for r in kec_rows if r["WADMKC"] in FOCUS_KEC]
        write_csv(OUT_TAB/"hazard_stats_focus_kecamatan.csv",focus_kec_rows)

        # all 18 focus features from secondary, including zero-intersection units
        focus_kel_rows=[]
        for geom,p in focus_features:
            m=zone_mask(geom,cds,das_mask)
            row={"unit_type":"FOCUS_KELURAHAN","WADMPR":p["WADMPR"],"WADMKK":p["WADMKK"],"WADMKC":p["WADMKC"],"WADMKD":p["WADMKD"],
                 "KDPPUM":p["KDPPUM"],"KDEBPS":p["KDEBPS"],"scenario":PRIMARY}
            row.update(class_stats(cls,m,cell_area))
            row["intersects_DAS"] = row["zone_cells"] > 0
            focus_kel_rows.append(row)
        focus_kel_rows.sort(key=lambda r:(r["WADMKC"],r["WADMKD"]))
        write_csv(OUT_TAB/"hazard_stats_focus_kelurahan_18.csv",focus_kel_rows)

        # sensitivity: DAS + all kecamatan
        sens_das=[]; sens_kec=[]
        for sc in SCENARIOS:
            with rasterio.open(RAS_SRC/f"{sc}_HAZARD_CLASS.tif") as sds:
                if sds.width!=cds.width or sds.height!=cds.height or sds.crs!=cds.crs or not sds.transform.almost_equals(cds.transform):
                    raise RuntimeError(f"Scenario {sc} raster alignment mismatch")
                arr=sds.read(1)
            r={"unit_type":"DAS","unit_name":"DAS KURANJI","scenario":sc}
            r.update(class_stats(arr,das_mask,cell_area)); sens_das.append(r)
            for geom,p in kec_features:
                rr={"unit_type":"KECAMATAN","WADMKK":p["WADMKK"],"WADMKC":p["WADMKC"],
                    "focus_area":p["WADMKC"] in FOCUS_KEC,"scenario":sc}
                rr.update(class_stats(arr,zone_mask(geom,cds,das_mask),cell_area)); sens_kec.append(rr)
        write_csv(OUT_TAB/"sensitivity_das.csv",sens_das)
        write_csv(OUT_TAB/"sensitivity_kecamatan_all.csv",sens_kec)

    # vectors
    write_geojson(OUT_VEC/"ADMIN_ALL_INTERSECTING_UTM47S.geojson",kel_features)
    write_geojson(OUT_VEC/"ADMIN_FOCUS_PAUH_KURANJI_18_UTM47S.geojson",focus_features)

    # freeze primary rasters
    for name in ["WD_INPUT","HAZARD_INDEX","HAZARD_CLASS"]:
        src=RAS_SRC/f"P175_{name}.tif"
        shutil.copy2(src,OUT_RAS/src.name)

    focus_zone=sum(r["zone_area_km2"] for r in focus_kec_rows)
    qc={
        "status":"Stage-2 administrative final package; P175 remains baseline hazard candidate pending external validation",
        "official_DAS_area_vector_km2":das.area/1e6,
        "raster_DAS_area_km2":das_row["zone_area_km2"],
        "primary_hazard_area_km2":das_row["hazard_area_km2"],
        "master_admin":str(master_path),
        "master_crs":master_crs,
        "master_features":len(master_rows),
        "master_fields":master_fields,
        "focus_admin":str(focus_path),
        "focus_crs":focus_crs,
        "focus_features":len(focus_features),
        "intersecting_kabkota":len(kab_features),
        "intersecting_kecamatan":len(kec_features),
        "intersecting_kelurahan_desa":len(kel_features),
        "focus_kecamatan":[r["WADMKC"] for r in focus_kec_rows],
        "focus_zone_raster_km2":focus_zone,
        "focus_share_raster_DAS_pct":100*focus_zone/das_row["zone_area_km2"] if das_row["zone_area_km2"] else 0,
        "focus_kelurahan_intersecting_DAS":sum(1 for r in focus_kel_rows if r["intersects_DAS"]),
        "focus_kelurahan_zero_DAS_intersection":sum(1 for r in focus_kel_rows if not r["intersects_DAS"]),
    }
    with (OUT_QC/"stage2_admin_final_qc.json").open("w",encoding="utf-8") as f:
        json.dump(qc,f,ensure_ascii=False,indent=2)

    readme=f"""# Stage 2 Administrative Final Package — DAS Kuranji\n\nPrimary hazard candidate: P175.\n\nAdministrative design:\n- Whole-DAS statistics: Sumatera_Barat.shp master administration.\n- Focus area: Pauh + Kuranji.\n- Focus kelurahan table retains all {len(focus_features)} secondary features, including zero-DAS-intersection units.\n\nWhole-DAS intersections:\n- kabupaten/kota: {len(kab_features)}\n- kecamatan: {len(kec_features)}\n- kelurahan/desa: {len(kel_features)}\n\nP175 hazard area: {das_row['hazard_area_km2']:.3f} km2.\nExternal flood validation is still pending.\n"""
    (OUT/"README_STAGE2_ADMIN_FINAL.md").write_text(readme,encoding="utf-8")

    print("=== STAGE 2 ADMIN FINAL — P175 ===")
    print(f"DAS raster area      : {das_row['zone_area_km2']:.3f} km2")
    print(f"P175 hazard area     : {das_row['hazard_area_km2']:.3f} km2 ({das_row['hazard_coverage_pct_zone']:.2f}% DAS)")
    print(f"Low / Medium / High : {das_row['low_km2']:.3f} / {das_row['medium_km2']:.3f} / {das_row['high_km2']:.3f} km2")

    print("\n=== ALL INTERSECTING KECAMATAN ===")
    for r in kec_rows:
        mark=" <FOCUS>" if r["focus_area"] else ""
        print(f"{r['WADMKK']:<18} | {r['WADMKC']:<22} | zone={r['zone_area_km2']:>7.3f} | hazard={r['hazard_area_km2']:>6.3f} | high={r['high_km2']:>6.3f}{mark}")

    print("\n=== FOCUS KELURAHAN (ALL 18) ===")
    for r in focus_kel_rows:
        state="IN DAS" if r["intersects_DAS"] else "OUTSIDE DAS"
        print(f"{r['WADMKC']:<8} | {r['WADMKD']:<28} | zone={r['zone_area_km2']:>7.3f} | hazard={r['hazard_area_km2']:>6.3f} | high={r['high_km2']:>6.3f} | {state}")

    print("\n=== TOP 10 INTERSECTING KELURAHAN/DESA BY HIGH HAZARD ===")
    for i,r in enumerate(sorted(kel_rows,key=lambda x:x["high_km2"],reverse=True)[:10],1):
        print(f"{i:>2}. {r['WADMKK']} / {r['WADMKC']} / {r['WADMKD']}: high={r['high_km2']:.3f} km2, hazard={r['hazard_area_km2']:.3f} km2")

    print("\nOutput:",OUT)


if __name__ == "__main__":
    main()
