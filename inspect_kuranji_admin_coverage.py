#!/usr/bin/env python3
"""Audit administrative coverage of DAS Batang Kuranji.

Purpose
-------
Use the detailed Sumatera Barat village/kelurahan layer as the master administrative
source and determine which kabupaten/kota, kecamatan and kelurahan truly intersect
the official DAS Kuranji boundary.

This is a diagnostic/QC step only. It does NOT alter Stage-2 hazard rasters.

Expected detailed layer fields (BIG-style administrative data):
- WADMPR : province
- WADMKK : kabupaten/kota
- WADMKC : kecamatan
- WADMKD : desa/kelurahan

Optional Kecamatan.shp is inspected as a secondary/reference layer only.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import fiona
from pyproj import CRS, Transformer
from shapely.geometry import shape
from shapely.ops import transform as shp_transform, unary_union

ROOT = Path(__file__).resolve().parent
DAS_DEFAULT = ROOT / "data/work/kuranji/01_prepared/DAS_KURANJI_UTM47S.geojson"
SEARCH_ROOTS = [ROOT / "data shp", ROOT / "data"]
TARGET_CRS = CRS.from_epsg(32747)


def norm(v):
    return " ".join(str(v or "").strip().upper().split())


def locate(name: str):
    matches = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        matches.extend(root.rglob(name))
    return sorted(matches, key=lambda p: (len(str(p)), str(p)))


def read_das(path: Path):
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    gs = [shape(ft["geometry"]) for ft in data.get("features", []) if ft.get("geometry")]
    if not gs:
        raise RuntimeError(f"No DAS geometry in {path}")
    return unary_union(gs)


def src_transformer(src_crs):
    src = CRS.from_user_input(src_crs)
    if src == TARGET_CRS:
        return None
    return Transformer.from_crs(src, TARGET_CRS, always_xy=True).transform


def inspect_master(path: Path, das):
    required = ["WADMPR", "WADMKK", "WADMKC", "WADMKD"]
    with fiona.open(path) as src:
        fields = list(src.schema.get("properties", {}).keys())
        missing = [x for x in required if x not in fields]
        if missing:
            raise RuntimeError(f"Master admin missing required fields: {missing}; fields={fields}")
        crs = src.crs_wkt or src.crs
        tf = src_transformer(crs)
        total_features = len(src)

        rows = []
        union_parts = []
        for ft in src:
            if not ft.get("geometry"):
                continue
            g = shape(ft["geometry"])
            if tf:
                g = shp_transform(tf, g)
            if g.is_empty or not g.intersects(das):
                continue
            inter = g.intersection(das)
            if inter.is_empty or inter.area <= 0:
                continue
            p = dict(ft.get("properties") or {})
            area_km2 = inter.area / 1e6
            rows.append({
                "WADMPR": norm(p.get("WADMPR")),
                "WADMKK": norm(p.get("WADMKK")),
                "WADMKC": norm(p.get("WADMKC")),
                "WADMKD": norm(p.get("WADMKD")),
                "KDPPUM": norm(p.get("KDPPUM")),
                "KDEBPS": norm(p.get("KDEBPS")),
                "intersection_km2": area_km2,
                "intersection_ha": area_km2 * 100.0,
            })
            union_parts.append(inter)

    rows.sort(key=lambda r: (r["WADMKK"], r["WADMKC"], r["WADMKD"]))
    union = unary_union(union_parts) if union_parts else None
    covered = union.area if union and not union.is_empty else 0.0
    das_area = das.area

    by_kec = defaultdict(float)
    by_kab = defaultdict(float)
    by_kel_count = defaultdict(int)
    for r in rows:
        kab = r["WADMKK"]
        kec = r["WADMKC"]
        by_kab[kab] += r["intersection_km2"]
        by_kec[(kab, kec)] += r["intersection_km2"]
        by_kel_count[(kab, kec)] += 1

    return {
        "path": str(path),
        "feature_count_total": total_features,
        "crs": str(crs),
        "fields": fields,
        "rows": rows,
        "by_kab": by_kab,
        "by_kec": by_kec,
        "by_kel_count": by_kel_count,
        "das_area_km2": das_area / 1e6,
        "admin_union_covered_km2": covered / 1e6,
        "admin_union_coverage_pct": 100.0 * covered / das_area if das_area else 0.0,
        "uncovered_km2": max(0.0, das_area - covered) / 1e6,
    }


def inspect_secondary(path: Path, das):
    with fiona.open(path) as src:
        fields = list(src.schema.get("properties", {}).keys())
        crs = src.crs_wkt or src.crs
        tf = src_transformer(crs)
        vals = []
        for i, ft in enumerate(src):
            if not ft.get("geometry"):
                continue
            g = shape(ft["geometry"])
            if tf:
                g = shp_transform(tf, g)
            inter = g.intersection(das) if g.intersects(das) else None
            p = dict(ft.get("properties") or {})
            vals.append({
                "index": i + 1,
                "WADMKK": norm(p.get("WADMKK")),
                "WADMKC": norm(p.get("WADMKC")),
                "WADMKD": norm(p.get("WADMKD")),
                "intersection_km2": (inter.area / 1e6) if inter and not inter.is_empty else 0.0,
                "properties": {k: p.get(k) for k in fields},
            })
        return {"path": str(path), "features": len(src), "fields": fields, "crs": str(crs), "rows": vals}


def write_csv(path: Path, rows):
    if not rows:
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", help="Path to Sumatera_Barat.shp")
    ap.add_argument("--kecamatan", help="Optional path to Kecamatan.shp")
    ap.add_argument("--das", default=str(DAS_DEFAULT))
    args = ap.parse_args()

    das_path = Path(args.das)
    if not das_path.exists():
        raise FileNotFoundError(das_path)
    das = read_das(das_path)

    if args.master:
        master = Path(args.master)
    else:
        found = locate("Sumatera_Barat.shp")
        if not found:
            raise FileNotFoundError("Sumatera_Barat.shp not found. Extract data_administrasi.rar first.")
        master = found[0]

    secondary = None
    if args.kecamatan:
        secondary = Path(args.kecamatan)
    else:
        found = locate("Kecamatan.shp")
        if found:
            secondary = found[0]

    res = inspect_master(master, das)

    out_dir = ROOT / "data/work/kuranji/13_admin_coverage_audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "admin_kelurahan_intersections.csv", res["rows"])

    kec_rows = []
    for (kab, kec), area in sorted(res["by_kec"].items(), key=lambda x: -x[1]):
        kec_rows.append({
            "WADMKK": kab,
            "WADMKC": kec,
            "kelurahan_count_intersecting": res["by_kel_count"][(kab, kec)],
            "intersection_km2": area,
            "intersection_pct_of_DAS": 100.0 * area / res["das_area_km2"] if res["das_area_km2"] else 0.0,
        })
    write_csv(out_dir / "admin_kecamatan_intersections.csv", kec_rows)

    kab_rows = []
    for kab, area in sorted(res["by_kab"].items(), key=lambda x: -x[1]):
        kab_rows.append({
            "WADMKK": kab,
            "intersection_km2": area,
            "intersection_pct_of_DAS": 100.0 * area / res["das_area_km2"] if res["das_area_km2"] else 0.0,
        })
    write_csv(out_dir / "admin_kabkota_intersections.csv", kab_rows)

    sec = inspect_secondary(secondary, das) if secondary and secondary.exists() else None

    qc = {
        "master": {k: v for k, v in res.items() if k not in {"rows", "by_kab", "by_kec", "by_kel_count"}},
        "kecamatan_summary": kec_rows,
        "kabkota_summary": kab_rows,
        "secondary_kecamatan_layer": sec,
    }
    with (out_dir / "admin_coverage_qc.json").open("w", encoding="utf-8") as f:
        json.dump(qc, f, indent=2, ensure_ascii=False, default=str)

    print("=== KURANJI ADMIN COVERAGE AUDIT ===")
    print("Master admin       :", master)
    print(f"Master features    : {res['feature_count_total']:,}")
    print("Master CRS         :", res["crs"])
    print(f"Official DAS area  : {res['das_area_km2']:.3f} km2")
    print(f"Admin union cover  : {res['admin_union_covered_km2']:.3f} km2 ({res['admin_union_coverage_pct']:.4f}%)")
    print(f"Uncovered area     : {res['uncovered_km2']:.6f} km2")

    print("\n=== KABUPATEN/KOTA INTERSECTING DAS ===")
    for r in kab_rows:
        print(f"{r['WADMKK']:<28} {r['intersection_km2']:>9.3f} km2  {r['intersection_pct_of_DAS']:>7.3f}%")

    print("\n=== KECAMATAN INTERSECTING DAS ===")
    for r in kec_rows:
        flag = "  <FOCUS>" if r["WADMKC"] in {"PAUH", "KURANJI"} else ""
        print(f"{r['WADMKK']:<22} | {r['WADMKC']:<24} | {r['intersection_km2']:>8.3f} km2 | {r['intersection_pct_of_DAS']:>6.2f}% | kel={r['kelurahan_count_intersecting']:>2}{flag}")

    print(f"\nIntersecting kelurahan/desa: {len(res['rows'])}")
    print("\n=== FOCUS: PAUH + KURANJI ===")
    focus_area = 0.0
    for r in kec_rows:
        if r["WADMKC"] in {"PAUH", "KURANJI"}:
            focus_area += r["intersection_km2"]
            print(f"{r['WADMKC']:<10} {r['intersection_km2']:.3f} km2 ({r['intersection_pct_of_DAS']:.2f}% DAS)")
    print(f"Combined focus     : {focus_area:.3f} km2 ({100*focus_area/res['das_area_km2'] if res['das_area_km2'] else 0:.2f}% DAS)")

    if sec:
        print("\n=== SECONDARY Kecamatan.shp ===")
        print("Path               :", sec["path"])
        print("Features           :", sec["features"])
        print("Fields             :", ", ".join(sec["fields"]))
        for r in sec["rows"][:20]:
            label = r.get("WADMKC") or r.get("WADMKD") or f"feature {r['index']}"
            print(f"{r['index']:>2}. {label:<30} intersect_DAS={r['intersection_km2']:.3f} km2")

    print("\nOutputs:", out_dir)
    print(" - admin_kabkota_intersections.csv")
    print(" - admin_kecamatan_intersections.csv")
    print(" - admin_kelurahan_intersections.csv")
    print(" - admin_coverage_qc.json")


if __name__ == "__main__":
    main()
