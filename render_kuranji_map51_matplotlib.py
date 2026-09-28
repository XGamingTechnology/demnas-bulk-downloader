#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic bilingual renderer for Kuranji Map 5.1 using GDAL/OGR + Matplotlib.

This script is cartographic only: it reads frozen Stage 1-2 vectors and does not
recalculate any analytical product.

Outputs:
  artifacts/KURANJI_FINAL_PYTHON_MAPS/05_STAGE1/ID/
  artifacts/KURANJI_FINAL_PYTHON_MAPS/05_STAGE1/EN/

Each language receives PNG + PDF plus a small JSON render summary.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import textwrap
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch, Polygon as MplPolygon
except Exception as exc:
    raise SystemExit(
        "Matplotlib is required. Install with: sudo apt-get install -y python3-matplotlib\n"
        f"IMPORT_ERROR={exc!r}"
    )

try:
    from osgeo import gdal, ogr, osr
except Exception as exc:
    raise SystemExit(
        "GDAL Python bindings are required. Install with: sudo apt-get install -y python3-gdal\n"
        f"IMPORT_ERROR={exc!r}"
    )


gdal.UseExceptions()
gdal.SetConfigOption("OGR_GEOMETRY_ACCEPT_UNCLOSED_RING", "YES")


# -----------------------------------------------------------------------------
# CLI / PATHS
# -----------------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--root", default="/opt/demnas-bulk-downloader")
parser.add_argument("--dpi", type=int, default=180)
parser.add_argument("--lang", default="id,en", help="Comma-separated: id,en")
args = parser.parse_args()

ROOT = Path(args.root).resolve()
K = ROOT / "data/work/kuranji"
A2 = ROOT / "artifacts/KURANJI_TAHAP2_SPATIAL_LAYOUT"
OUT = ROOT / "artifacts/KURANJI_FINAL_PYTHON_MAPS/05_STAGE1"

SRC = {
    "das": K / "01_prepared/DAS_KURANJI_UTM47S.geojson",
    "rbi": K / "01_prepared/SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson",
    "admin_all": A2 / "05_ADMIN_VECTOR/ADMIN_ALL_INTERSECTING_UTM47S.geojson",
    "admin_focus": A2 / "05_ADMIN_VECTOR/ADMIN_FOCUS_PAUH_KURANJI_18_UTM47S.geojson",
    "sumbar": ROOT / "data shp/data_administrasi/Sumatera_Barat.shp",
}

TEXT = {
    "id": {
        "title": "Peta 5.1. Lokasi Penelitian DAS Batang Kuranji",
        "subtitle": "Konteks DAS dan fokus administratif Pauh–Kuranji",
        "inset_title": "Lokasi dalam Sumatera Barat",
        "legend_title": "LEGENDA",
        "summary_title": "RINGKASAN HASIL",
        "summary": (
            "Pemodelan fisik menggunakan seluruh DAS Batang Kuranji. "
            "Pauh dan Kuranji ditampilkan sebagai fokus administratif; "
            "keduanya bukan batas proses hidrologi."
        ),
        "science_title": "CATATAN ILMIAH",
        "science": (
            "Batas administratif digunakan untuk memberi konteks spasial pada hasil. "
            "Unit analisis hidrologi utama tetap seluruh DAS Batang Kuranji."
        ),
        "footer": (
            "Sumber: dataset penelitian Stage 1–2 (DAS, RBI, administrasi) | "
            "CRS utama: WGS 84 / UTM zone 47S (EPSG:32747) | "
            "Tahun data: mengikuti metadata sumber."
        ),
        "das": "Batas DAS Batang Kuranji",
        "rbi": "Sungai RBI",
        "admin": "Batas administrasi",
        "focus": "Fokus Pauh–Kuranji",
        "inset_das": "DAS Kuranji",
        "scale": "km",
    },
    "en": {
        "title": "Map 5.1. Study Area of the Batang Kuranji Watershed",
        "subtitle": "Watershed context and the Pauh–Kuranji administrative focus",
        "inset_title": "Location within West Sumatra",
        "legend_title": "LEGEND",
        "summary_title": "RESULT SUMMARY",
        "summary": (
            "Physical modelling uses the full Batang Kuranji watershed. "
            "Pauh and Kuranji are shown as an administrative focus; "
            "they are not hydrological process boundaries."
        ),
        "science_title": "SCIENTIFIC NOTE",
        "science": (
            "Administrative boundaries provide spatial context for the results. "
            "The primary hydrological analysis unit remains the full Batang Kuranji watershed."
        ),
        "footer": (
            "Source: Stage 1–2 research datasets (watershed, RBI rivers, administration) | "
            "Main CRS: WGS 84 / UTM zone 47S (EPSG:32747) | "
            "Data year: according to source metadata."
        ),
        "das": "Batang Kuranji watershed",
        "rbi": "RBI river network",
        "admin": "Administrative boundary",
        "focus": "Pauh–Kuranji focus",
        "inset_das": "Kuranji watershed",
        "scale": "km",
    },
}

SLUG = {
    "id": "PETA_5_1_LOKASI_DAS_KURANJI",
    "en": "MAP_5_1_BATANG_KURANJI_STUDY_AREA",
}


# -----------------------------------------------------------------------------
# VECTOR HELPERS
# -----------------------------------------------------------------------------
def srs_epsg(epsg: int):
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    try:
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    except Exception:
        pass
    return srs


def clone_srs(srs):
    if srs is None:
        return None
    out = srs.Clone()
    try:
        out.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    except Exception:
        pass
    return out


def open_layer(path: Path):
    ds = ogr.Open(str(path), 0)
    if ds is None:
        raise RuntimeError(f"Cannot open vector: {path}")
    lyr = ds.GetLayer(0)
    if lyr is None:
        raise RuntimeError(f"No vector layer in: {path}")
    return ds, lyr


def transform_geometry(geom, src_srs, target_epsg: int):
    g = geom.Clone()
    if src_srs is None:
        return g
    src = clone_srs(src_srs)
    dst = srs_epsg(target_epsg)
    if src.IsSame(dst):
        return g
    ct = osr.CoordinateTransformation(src, dst)
    err = g.Transform(ct)
    if err != 0:
        raise RuntimeError(f"Geometry transform failed with code {err}")
    return g


def iter_transformed(path: Path, target_epsg: int):
    ds, lyr = open_layer(path)
    src_srs = lyr.GetSpatialRef()
    fields = [lyr.GetLayerDefn().GetFieldDefn(i).GetName() for i in range(lyr.GetLayerDefn().GetFieldCount())]
    lyr.ResetReading()
    for feat in lyr:
        geom = feat.GetGeometryRef()
        if geom is None or geom.IsEmpty():
            continue
        try:
            g = transform_geometry(geom, src_srs, target_epsg)
        except Exception:
            continue
        attrs = {f: feat.GetField(f) for f in fields}
        yield g, attrs
    ds = None


def extent_from_layer(path: Path, target_epsg: int, margin=0.05):
    xmin = ymin = float("inf")
    xmax = ymax = float("-inf")
    count = 0
    for g, _ in iter_transformed(path, target_epsg):
        env = g.GetEnvelope()  # minX, maxX, minY, maxY
        xmin = min(xmin, env[0])
        xmax = max(xmax, env[1])
        ymin = min(ymin, env[2])
        ymax = max(ymax, env[3])
        count += 1
    if count == 0:
        raise RuntimeError(f"No geometries for extent: {path}")
    w = max(xmax - xmin, 1.0)
    h = max(ymax - ymin, 1.0)
    pad = max(w, h) * margin
    return xmin - pad, xmax + pad, ymin - pad, ymax + pad


def draw_geom(ax, geom, *, facecolor="none", edgecolor="#333333", linewidth=0.7,
              alpha=1.0, zorder=1, point_size=12):
    gt = ogr.wkbFlatten(geom.GetGeometryType())

    if gt == ogr.wkbPolygon:
        if geom.GetGeometryCount() == 0:
            return
        ring = geom.GetGeometryRef(0)
        if ring is None or ring.GetPointCount() < 3:
            return
        xy = [(ring.GetX(i), ring.GetY(i)) for i in range(ring.GetPointCount())]
        ax.add_patch(MplPolygon(
            xy, closed=True, facecolor=facecolor, edgecolor=edgecolor,
            linewidth=linewidth, alpha=alpha, zorder=zorder
        ))
        return

    if gt in (ogr.wkbLineString, ogr.wkbLinearRing):
        if geom.GetPointCount() < 2:
            return
        xs = [geom.GetX(i) for i in range(geom.GetPointCount())]
        ys = [geom.GetY(i) for i in range(geom.GetPointCount())]
        ax.plot(xs, ys, color=edgecolor, linewidth=linewidth, alpha=alpha, zorder=zorder)
        return

    if gt == ogr.wkbPoint:
        ax.scatter([geom.GetX()], [geom.GetY()], s=point_size, c=edgecolor, alpha=alpha, zorder=zorder)
        return

    if gt in (
        ogr.wkbMultiPolygon,
        ogr.wkbMultiLineString,
        ogr.wkbMultiPoint,
        ogr.wkbGeometryCollection,
    ):
        for i in range(geom.GetGeometryCount()):
            sub = geom.GetGeometryRef(i)
            if sub is not None:
                draw_geom(
                    ax, sub, facecolor=facecolor, edgecolor=edgecolor,
                    linewidth=linewidth, alpha=alpha, zorder=zorder,
                    point_size=point_size
                )
        return


def draw_layer(ax, path: Path, target_epsg: int, **style):
    n = 0
    for geom, _ in iter_transformed(path, target_epsg):
        draw_geom(ax, geom, **style)
        n += 1
    return n


def detect_focus_labels(path: Path, target_epsg: int):
    candidates = ["WADMKC", "KECAMATAN", "NAMA_KEC", "NAME_3", "name", "NAME"]
    acc = {}
    for geom, attrs in iter_transformed(path, target_epsg):
        name = None
        for fld in candidates:
            val = attrs.get(fld)
            if val not in (None, ""):
                name = str(val).strip()
                break
        if not name:
            continue
        low = name.lower()
        if "pauh" not in low and "kuranji" not in low:
            continue
        c = geom.Centroid()
        if c is None or c.IsEmpty():
            continue
        x, y = c.GetX(), c.GetY()
        acc.setdefault(name, []).append((x, y))
    labels = []
    for name, pts in acc.items():
        x = sum(p[0] for p in pts) / len(pts)
        y = sum(p[1] for p in pts) / len(pts)
        labels.append((name, x, y))
    return labels


# -----------------------------------------------------------------------------
# CARTOGRAPHIC HELPERS
# -----------------------------------------------------------------------------
def nice_number(value):
    if value <= 0:
        return 1.0
    exp = math.floor(math.log10(value))
    frac = value / (10 ** exp)
    if frac < 1.5:
        nice = 1
    elif frac < 3.5:
        nice = 2
    elif frac < 7.5:
        nice = 5
    else:
        nice = 10
    return nice * (10 ** exp)


def add_scalebar(ax, extent, label="km"):
    xmin, xmax, ymin, ymax = extent
    width = xmax - xmin
    height = ymax - ymin
    target = width * 0.20
    length_m = nice_number(target)
    if length_m > width * 0.32:
        length_m = nice_number(width * 0.15)
    x0 = xmin + width * 0.07
    y0 = ymin + height * 0.065
    x1 = x0 + length_m
    ax.plot([x0, x1], [y0, y0], color="black", linewidth=2.5, zorder=20)
    ax.plot([x0, x0], [y0 - height*0.006, y0 + height*0.006], color="black", linewidth=1.5, zorder=20)
    ax.plot([x1, x1], [y0 - height*0.006, y0 + height*0.006], color="black", linewidth=1.5, zorder=20)
    ax.text(x0, y0 + height*0.017, "0", ha="center", va="bottom", fontsize=9, zorder=20)
    ax.text(x1, y0 + height*0.017, f"{length_m/1000:g} {label}", ha="center", va="bottom", fontsize=9, zorder=20)


def add_north_arrow(ax):
    ax.annotate(
        "N",
        xy=(0.065, 0.91), xycoords="axes fraction",
        xytext=(0.065, 0.80), textcoords="axes fraction",
        ha="center", va="center", fontsize=13, fontweight="bold",
        arrowprops=dict(facecolor="black", edgecolor="black", width=2.2, headwidth=10, headlength=12),
        zorder=30,
    )


def style_map_axes(ax, extent):
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_linewidth(0.9)
        s.set_color("#4a4a4a")


def add_panel_border(ax):
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#8b8b8b")
        s.set_linewidth(0.8)


# -----------------------------------------------------------------------------
# RENDER
# -----------------------------------------------------------------------------
def render(lang: str, dpi: int):
    if lang not in TEXT:
        raise ValueError(f"Unsupported language: {lang}")
    t = TEXT[lang]

    outdir = OUT / lang.upper()
    outdir.mkdir(parents=True, exist_ok=True)
    png = outdir / f"{SLUG[lang]}.png"
    pdf = outdir / f"{SLUG[lang]}.pdf"
    summary_json = outdir / f"{SLUG[lang]}_RENDER.json"

    for p in (png, pdf, summary_json):
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass

    main_extent = extent_from_layer(SRC["das"], 32747, margin=0.055)
    inset_extent = extent_from_layer(SRC["sumbar"], 4326, margin=0.035)

    fig = plt.figure(figsize=(16.54, 11.69), facecolor="white")

    # Title block
    fig.text(0.5, 0.955, t["title"], ha="center", va="top", fontsize=21, fontweight="bold", color="#1f1f1f")
    fig.text(0.5, 0.922, t["subtitle"], ha="center", va="top", fontsize=11.5, color="#5a5a5a")

    # Main map
    ax = fig.add_axes([0.045, 0.205, 0.675, 0.675])
    ax.set_facecolor("#fbfbfb")
    draw_layer(ax, SRC["admin_all"], 32747, facecolor="none", edgecolor="#b6b6b6", linewidth=0.45, alpha=1.0, zorder=2)
    draw_layer(ax, SRC["admin_focus"], 32747, facecolor="#f59e0b", edgecolor="#d97706", linewidth=0.75, alpha=0.18, zorder=3)
    draw_layer(ax, SRC["rbi"], 32747, facecolor="none", edgecolor="#1769aa", linewidth=0.85, alpha=0.95, zorder=5)
    draw_layer(ax, SRC["das"], 32747, facecolor="none", edgecolor="#111111", linewidth=1.8, alpha=1.0, zorder=8)
    style_map_axes(ax, main_extent)
    add_north_arrow(ax)
    add_scalebar(ax, main_extent, t["scale"])

    for name, x, y in detect_focus_labels(SRC["admin_focus"], 32747):
        ax.text(
            x, y, name, ha="center", va="center", fontsize=8.8, fontweight="bold", color="#7c2d12",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="#f59e0b", alpha=0.82, linewidth=0.7),
            zorder=12,
        )

    # Inset in geographic coordinates to avoid unnecessary UTM reprojection of the entire province.
    ax_in = fig.add_axes([0.755, 0.655, 0.215, 0.225])
    ax_in.set_facecolor("#fafafa")
    draw_layer(ax_in, SRC["sumbar"], 4326, facecolor="#ececec", edgecolor="#808080", linewidth=0.30, alpha=1.0, zorder=1)
    draw_layer(ax_in, SRC["das"], 4326, facecolor="#dc2626", edgecolor="#991b1b", linewidth=0.9, alpha=0.65, zorder=5)
    style_map_axes(ax_in, inset_extent)
    ax_in.set_title(t["inset_title"], fontsize=10.5, fontweight="bold", pad=7)

    # Legend
    ax_leg = fig.add_axes([0.755, 0.445, 0.215, 0.175])
    ax_leg.set_facecolor("white")
    add_panel_border(ax_leg)
    ax_leg.text(0.045, 0.91, t["legend_title"], transform=ax_leg.transAxes, ha="left", va="top", fontsize=12.2, fontweight="bold")
    handles = [
        Line2D([0], [0], color="#111111", linewidth=2.0, label=t["das"]),
        Line2D([0], [0], color="#1769aa", linewidth=1.6, label=t["rbi"]),
        Line2D([0], [0], color="#b6b6b6", linewidth=1.0, label=t["admin"]),
        Patch(facecolor="#f59e0b", edgecolor="#d97706", alpha=0.25, label=t["focus"]),
    ]
    ax_leg.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.035, 0.73), frameon=False, fontsize=10.2, handlelength=2.5, labelspacing=1.0)

    # Summary panel
    ax_sum = fig.add_axes([0.755, 0.205, 0.215, 0.195])
    ax_sum.set_facecolor("#f7f7f7")
    add_panel_border(ax_sum)
    ax_sum.text(0.045, 0.90, t["summary_title"], transform=ax_sum.transAxes, ha="left", va="top", fontsize=11.5, fontweight="bold")
    ax_sum.text(
        0.045, 0.72,
        textwrap.fill(t["summary"], width=39),
        transform=ax_sum.transAxes, ha="left", va="top", fontsize=9.4, color="#2f2f2f", linespacing=1.35,
    )

    # Scientific note + footer
    fig.text(0.047, 0.155, t["science_title"], ha="left", va="top", fontsize=10.8, fontweight="bold", color="#272727")
    fig.text(
        0.047, 0.135,
        textwrap.fill(t["science"], width=145),
        ha="left", va="top", fontsize=9.4, color="#333333",
        bbox=dict(boxstyle="round,pad=0.42", facecolor="#f8f8f8", edgecolor="#b0b0b0", linewidth=0.7),
    )
    fig.text(0.047, 0.070, t["footer"], ha="left", va="top", fontsize=8.4, color="#555555")

    fig.savefig(png, dpi=dpi, facecolor="white")
    fig.savefig(pdf, dpi=dpi, facecolor="white")
    plt.close(fig)

    result = {
        "map_id": "5.1",
        "language": lang,
        "dpi": dpi,
        "png": str(png),
        "pdf": str(pdf),
        "png_bytes": png.stat().st_size if png.exists() else 0,
        "pdf_bytes": pdf.stat().st_size if pdf.exists() else 0,
        "main_extent_epsg32747": list(main_extent),
        "inset_extent_epsg4326": list(inset_extent),
        "sources": {k: str(v) for k, v in SRC.items()},
        "scientific_guardrail": "cartographic rendering only; no Stage 1-2 recalculation",
    }
    summary_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"RENDER_OK lang={lang} png={png} bytes={result['png_bytes']}")
    print(f"RENDER_OK lang={lang} pdf={pdf} bytes={result['pdf_bytes']}")
    return result


def main():
    missing = [str(p) for p in SRC.values() if not p.exists()]
    if missing:
        print("SOURCE_PREFLIGHT=FAIL")
        for p in missing:
            print(f"MISSING={p}")
        raise SystemExit(2)

    print("SOURCE_PREFLIGHT=PASS")
    langs = [x.strip().lower() for x in args.lang.split(",") if x.strip()]
    results = [render(lang, args.dpi) for lang in langs]
    print(f"FINAL_STATUS=COMPLETE rendered={len(results)}")


if __name__ == "__main__":
    main()
