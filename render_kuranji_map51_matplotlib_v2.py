#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Publication-style bilingual renderer for Kuranji Map 5.1.

Design goal: follow the user's reference layout more closely while keeping the
cartography deterministic and scientifically conservative. This script only
renders existing frozen vectors; it does not recalculate Stage 1-4 analysis.

It reuses source/transform helpers from render_kuranji_map51_matplotlib.py but
implements its own drawing stack, so it is compatible with GDAL builds that
provide ogr.GT_Flatten rather than ogr.wkbFlatten.
"""

from __future__ import annotations

import math
import json
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Polygon as MplPolygon
from osgeo import ogr, osr

import render_kuranji_map51_matplotlib as base

ROOT = base.ROOT
SRC = dict(base.SRC)
SRC["kecamatan_raw"] = ROOT / "data shp/data_administrasi/Kecamatan.shp"
OUT = ROOT / "artifacts/KURANJI_FINAL_PYTHON_MAPS_V2/05_STAGE1"

TEXT = {
    "id": {
        "title": "PETA LOKASI PENELITIAN DAS BATANG KURANJI",
        "inset": "LOKASI DALAM SUMATERA BARAT",
        "legend": "LEGENDA",
        "summary": "RINGKASAN HASIL",
        "note": "CATATAN ILMIAH",
        "source": "SUMBER / CRS / CAPTION",
        "das": "DAS Batang Kuranji",
        "rbi": "Sungai RBI",
        "kec": "Batas kecamatan",
        "kuranji": "Kecamatan Kuranji",
        "pauh": "Kecamatan Pauh",
        "summary_lines": [
            "DAS Batang Kuranji berada di Sumatera Barat; Pauh dan Kuranji digunakan sebagai fokus administratif.",
            "Luas DAS referensi vektor sekitar 224,696 km².",
            "Fokus Pauh + Kuranji sekitar 174,680 km² atau 77,74% luas DAS.",
            "Domain proses hidrologi tetap seluruh DAS, bukan batas administrasi.",
            "CRS analisis utama: WGS 84 / UTM Zone 47S (EPSG:32747).",
        ],
        "note_text": (
            "Peta menunjukkan lokasi dan konteks administratif DAS Batang Kuranji sebagai dasar analisis hidrologi Tahap 1. "
            "Batas administratif digunakan sebagai konteks spasial, sedangkan unit analisis hidrologi utama tetap seluruh DAS."
        ),
        "source_lines": [
            "• DAS Batang Kuranji: dataset prepared Stage 1",
            "• Sungai RBI: BIG",
            "• Administrasi Sumatera Barat: paket data penelitian",
            "• Fokus Pauh–Kuranji: vector administrasi Stage 2",
            "CRS: WGS 84 / UTM Zone 47S (EPSG:32747)",
            "Tahun data: mengikuti metadata masing-masing sumber",
        ],
        "caption": "Lokasi DAS Batang Kuranji dan konteks administratif wilayah penelitian di Sumatera Barat.",
        "scale": "SKALA",
    },
    "en": {
        "title": "STUDY AREA OF THE BATANG KURANJI WATERSHED",
        "inset": "LOCATION WITHIN WEST SUMATRA",
        "legend": "LEGEND",
        "summary": "RESULT SUMMARY",
        "note": "SCIENTIFIC NOTE",
        "source": "SOURCE / CRS / CAPTION",
        "das": "Batang Kuranji watershed",
        "rbi": "RBI river network",
        "kec": "Subdistrict boundary",
        "kuranji": "Kuranji Subdistrict",
        "pauh": "Pauh Subdistrict",
        "summary_lines": [
            "The Batang Kuranji watershed is located in West Sumatra; Pauh and Kuranji are used as the administrative focus.",
            "Reference watershed vector area is approximately 224.696 km².",
            "The Pauh + Kuranji focus covers about 174.680 km² or 77.74% of the watershed.",
            "The hydrological process domain remains the full watershed rather than administrative boundaries.",
            "Main analysis CRS: WGS 84 / UTM Zone 47S (EPSG:32747).",
        ],
        "note_text": (
            "This map presents the location and administrative context of the Batang Kuranji watershed as the spatial basis for Stage 1 hydrological analysis. "
            "Administrative boundaries provide context, while the primary hydrological analysis unit remains the complete watershed."
        ),
        "source_lines": [
            "• Batang Kuranji watershed: Stage 1 prepared dataset",
            "• RBI river network: BIG",
            "• West Sumatra administration: research data package",
            "• Pauh–Kuranji focus: Stage 2 administrative vector",
            "CRS: WGS 84 / UTM Zone 47S (EPSG:32747)",
            "Data year: according to metadata for each source",
        ],
        "caption": "Batang Kuranji watershed and the administrative context of the study area in West Sumatra.",
        "scale": "SCALE",
    },
}

SLUG = {
    "id": "PETA_5_1_LOKASI_DAS_KURANJI_V2",
    "en": "MAP_5_1_BATANG_KURANJI_STUDY_AREA_V2",
}


def flat_type(g):
    return ogr.GT_Flatten(g.GetGeometryType())


def draw_geom(ax, geom, *, facecolor="none", edgecolor="#333333", linewidth=0.7,
              alpha=1.0, zorder=1, hatch=None):
    gt = flat_type(geom)
    if gt == ogr.wkbPolygon:
        if geom.GetGeometryCount() == 0:
            return
        ring = geom.GetGeometryRef(0)
        if ring is None or ring.GetPointCount() < 3:
            return
        xy = [(ring.GetX(i), ring.GetY(i)) for i in range(ring.GetPointCount())]
        ax.add_patch(MplPolygon(
            xy, closed=True, facecolor=facecolor, edgecolor=edgecolor,
            linewidth=linewidth, alpha=alpha, zorder=zorder, hatch=hatch,
        ))
    elif gt in (ogr.wkbLineString, ogr.wkbLinearRing):
        if geom.GetPointCount() < 2:
            return
        xs = [geom.GetX(i) for i in range(geom.GetPointCount())]
        ys = [geom.GetY(i) for i in range(geom.GetPointCount())]
        ax.plot(xs, ys, color=edgecolor, linewidth=linewidth, alpha=alpha, zorder=zorder)
    elif gt in (ogr.wkbMultiPolygon, ogr.wkbMultiLineString, ogr.wkbGeometryCollection):
        for i in range(geom.GetGeometryCount()):
            sub = geom.GetGeometryRef(i)
            if sub is not None:
                draw_geom(ax, sub, facecolor=facecolor, edgecolor=edgecolor,
                          linewidth=linewidth, alpha=alpha, zorder=zorder, hatch=hatch)


def draw_layer(ax, path, epsg, **style):
    n = 0
    for g, _ in base.iter_transformed(path, epsg):
        draw_geom(ax, g, **style)
        n += 1
    return n


def attr_value(attrs, names):
    lower = {str(k).lower(): v for k, v in attrs.items()}
    for name in names:
        v = lower.get(name.lower())
        if v not in (None, ""):
            return str(v).strip()
    return None


def classify_focus(attrs):
    val = attr_value(attrs, ["WADMKC", "KECAMATAN", "NAMA_KEC", "NAME_3", "kecamatan", "name"])
    low = (val or "").lower()
    if "kuranji" in low:
        return "kuranji"
    if "pauh" in low:
        return "pauh"
    # Some Stage-2 focus files may carry only village names. Keep a neutral focus colour
    # instead of inventing an administrative class.
    return "other"


def draw_focus(ax):
    counts = {"kuranji": 0, "pauh": 0, "other": 0}
    styles = {
        "kuranji": dict(facecolor="#c7df00", edgecolor="#718c00", linewidth=0.65, alpha=0.92, zorder=5),
        "pauh": dict(facecolor="#93c95b", edgecolor="#4f7f32", linewidth=0.65, alpha=0.92, zorder=5),
        "other": dict(facecolor="#eadf92", edgecolor="#b2a65e", linewidth=0.55, alpha=0.65, zorder=4),
    }
    for g, attrs in base.iter_transformed(SRC["admin_focus"], 32747):
        cls = classify_focus(attrs)
        draw_geom(ax, g, **styles[cls])
        counts[cls] += 1
    return counts


def geom_centroid_xy(g):
    c = g.Centroid()
    if c is None or c.IsEmpty():
        return None
    return c.GetX(), c.GetY()


def labels_from_layer(path, epsg, field_candidates, extent, unique=True, max_labels=30):
    xmin, xmax, ymin, ymax = extent
    seen = set()
    out = []
    for g, attrs in base.iter_transformed(path, epsg):
        name = attr_value(attrs, field_candidates)
        if not name:
            continue
        key = name.lower()
        if unique and key in seen:
            continue
        xy = geom_centroid_xy(g)
        if not xy:
            continue
        x, y = xy
        if not (xmin <= x <= xmax and ymin <= y <= ymax):
            continue
        seen.add(key)
        out.append((name, x, y))
        if len(out) >= max_labels:
            break
    return out


def draw_context_labels(ax, extent):
    # Neighbouring subdistricts
    kec = labels_from_layer(
        SRC["kecamatan_raw"], 32747,
        ["WADMKC", "KECAMATAN", "NAMA_KEC", "NAME_3", "name", "NAME"],
        extent, unique=True, max_labels=14,
    )
    for name, x, y in kec:
        if name.lower() in ("pauh", "kuranji"):
            continue
        ax.text(x, y, f"KEC {name}", ha="center", va="center", fontsize=7.2,
                color="#333333", fontstyle="italic", zorder=9,
                path_effects=[pe.withStroke(linewidth=2.1, foreground="white", alpha=0.95)])

    # Village / kelurahan names inside the focus area
    villages = labels_from_layer(
        SRC["admin_focus"], 32747,
        ["WADMKD", "KELURAHAN", "DESA", "NAMA_DESA", "NAMA_KEL", "NAME_4", "NAMOBJ", "name"],
        extent, unique=True, max_labels=22,
    )
    for name, x, y in villages:
        ax.text(x, y, name, ha="center", va="center", fontsize=6.1,
                color="#27311e", fontstyle="italic", zorder=10,
                path_effects=[pe.withStroke(linewidth=1.6, foreground="white", alpha=0.92)])


def srs_epsg(epsg):
    s = osr.SpatialReference()
    s.ImportFromEPSG(epsg)
    try:
        s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    except Exception:
        pass
    return s


def transformer(src_epsg, dst_epsg):
    return osr.CoordinateTransformation(srs_epsg(src_epsg), srs_epsg(dst_epsg))


def xy_transform(ct, x, y):
    p = ct.TransformPoint(float(x), float(y))
    return p[0], p[1]


def nice_degree_step(span):
    for step in (0.02, 0.05, 0.1, 0.2, 0.5, 1.0):
        if span / step <= 6.5:
            return step
    return 2.0


def add_graticule(ax, extent):
    xmin, xmax, ymin, ymax = extent
    to_ll = transformer(32747, 4326)
    to_xy = transformer(4326, 32747)
    corners = [xy_transform(to_ll, x, y) for x, y in ((xmin,ymin),(xmin,ymax),(xmax,ymin),(xmax,ymax))]
    lons = [p[0] for p in corners]
    lats = [p[1] for p in corners]
    lon_min, lon_max = min(lons), max(lons)
    lat_min, lat_max = min(lats), max(lats)
    lon_step = nice_degree_step(lon_max - lon_min)
    lat_step = nice_degree_step(lat_max - lat_min)

    lon0 = math.ceil(lon_min / lon_step) * lon_step
    lat0 = math.ceil(lat_min / lat_step) * lat_step

    lon = lon0
    while lon <= lon_max + 1e-9:
        pts = []
        for i in range(81):
            lat = lat_min + (lat_max-lat_min)*i/80
            try:
                pts.append(xy_transform(to_xy, lon, lat))
            except Exception:
                pass
        if len(pts) > 1:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#202020", linewidth=0.45, alpha=0.52, zorder=1)
            xlab, _ = xy_transform(to_xy, lon, lat_max)
            ax.text(xlab, ymax, f"{lon:.3f}°E", ha="center", va="bottom", fontsize=7.2, clip_on=False)
        lon += lon_step

    lat = lat0
    while lat <= lat_max + 1e-9:
        pts = []
        for i in range(81):
            lon = lon_min + (lon_max-lon_min)*i/80
            try:
                pts.append(xy_transform(to_xy, lon, lat))
            except Exception:
                pass
        if len(pts) > 1:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#202020", linewidth=0.45, alpha=0.52, zorder=1)
            _, ylab = xy_transform(to_xy, lon_min, lat)
            hemi = "S" if lat < 0 else "N"
            ax.text(xmin, ylab, f"{abs(lat):.3f}°{hemi}", ha="right", va="center", fontsize=7.2, rotation=90, clip_on=False)
        lat += lat_step


def nice_number(value):
    if value <= 0:
        return 1.0
    exp = math.floor(math.log10(value))
    frac = value / (10 ** exp)
    if frac < 1.5:
        n = 1
    elif frac < 3.5:
        n = 2
    elif frac < 7.5:
        n = 5
    else:
        n = 10
    return n * (10 ** exp)


def add_scalebar(ax, extent, lang):
    xmin, xmax, ymin, ymax = extent
    width = xmax-xmin
    height = ymax-ymin
    length = nice_number(width*0.11)
    if length > width*0.20:
        length = nice_number(width*0.08)
    x0 = xmin + width*0.035
    y0 = ymin + height*0.055
    # 4 alternating sections
    sections = 4
    seg = length/sections
    bar_h = height*0.012
    for i in range(sections):
        fc = "black" if i % 2 == 0 else "white"
        ax.add_patch(MplPolygon([
            (x0+i*seg,y0), (x0+(i+1)*seg,y0),
            (x0+(i+1)*seg,y0+bar_h), (x0+i*seg,y0+bar_h)
        ], closed=True, facecolor=fc, edgecolor="black", linewidth=0.55, zorder=25))
    ax.text(x0, y0+bar_h*1.45, "0", fontsize=6.8, ha="center", va="bottom", zorder=26)
    ax.text(x0+length/2, y0+bar_h*1.45, f"{length/2000:g}", fontsize=6.8, ha="center", va="bottom", zorder=26)
    ax.text(x0+length, y0+bar_h*1.45, f"{length/1000:g} km", fontsize=6.8, ha="center", va="bottom", zorder=26)


def add_north(ax):
    ax.annotate("N", xy=(0.045,0.91), xytext=(0.045,0.82), xycoords="axes fraction", textcoords="axes fraction",
                ha="center", va="center", fontsize=10, fontweight="bold",
                arrowprops=dict(facecolor="black", edgecolor="black", width=1.8, headwidth=8, headlength=10), zorder=30)


def style_axes(ax, extent):
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#1f1f1f"); s.set_linewidth(1.0)


def panel(ax, face="#f7f7f7"):
    ax.set_facecolor(face)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#777777"); s.set_linewidth(0.8)


def computed_scale_denominator(fig, ax, extent):
    fig.canvas.draw()
    width_in = ax.get_window_extent().width / fig.dpi
    paper_width_m = width_in * 0.0254
    map_width_m = extent[1] - extent[0]
    if paper_width_m <= 0:
        return None
    return map_width_m / paper_width_m


def render(lang, dpi):
    t = TEXT[lang]
    outdir = OUT / lang.upper()
    outdir.mkdir(parents=True, exist_ok=True)
    png = outdir / f"{SLUG[lang]}.png"
    pdf = outdir / f"{SLUG[lang]}.pdf"
    meta = outdir / f"{SLUG[lang]}_RENDER.json"

    # Wider context than V1 so neighbouring subdistricts are visible.
    extent = base.extent_from_layer(SRC["das"], 32747, margin=0.135)
    inset_extent = base.extent_from_layer(SRC["sumbar"], 4326, margin=0.025)

    fig = plt.figure(figsize=(16.54, 11.69), facecolor="white")  # A3 landscape
    fig.text(0.5, 0.965, t["title"], ha="center", va="top", fontsize=20, fontweight="bold", color="#1f1f1f")

    # Main map occupies most of the page, similar to the user's reference.
    ax = fig.add_axes([0.025, 0.205, 0.655, 0.690])
    ax.set_facecolor("white")

    # Context subdistricts first: light hatch and boundaries.
    draw_layer(ax, SRC["kecamatan_raw"], 32747, facecolor="#fafafa", edgecolor="#888888",
               linewidth=0.45, alpha=0.90, zorder=2, hatch="////")
    # Detailed admin boundaries.
    draw_layer(ax, SRC["admin_all"], 32747, facecolor="none", edgecolor="#9d9d9d",
               linewidth=0.34, alpha=0.95, zorder=3)
    focus_counts = draw_focus(ax)
    # Rivers then watershed hatch/outline.
    draw_layer(ax, SRC["rbi"], 32747, facecolor="none", edgecolor="#2385c6",
               linewidth=0.75, alpha=1.0, zorder=7)
    draw_layer(ax, SRC["das"], 32747, facecolor="none", edgecolor="#1677aa",
               linewidth=1.75, alpha=1.0, zorder=8, hatch="////")

    style_axes(ax, extent)
    add_graticule(ax, extent)
    add_north(ax)
    add_scalebar(ax, extent, lang)
    draw_context_labels(ax, extent)

    # Strong focus labels, in the style of the user's design but without oversized decorative text.
    for name, x, y in base.detect_focus_labels(SRC["admin_focus"], 32747):
        ax.annotate(f"KEC {name.upper()}", xy=(x,y), xytext=(x+(extent[1]-extent[0])*0.045, y+(extent[3]-extent[2])*0.018),
                    fontsize=9.2, color="#c7202f", fontweight="bold", zorder=20,
                    arrowprops=dict(arrowstyle="-", color="#d62728", lw=1.2),
                    path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])

    # Scale denominator computed from final physical map width.
    scale_denom = computed_scale_denominator(fig, ax, extent)
    if scale_denom:
        rounded = int(round(scale_denom/1000.0)*1000)
        ax.text(0.03, 0.075, f"{t['scale']} 1 : {rounded:,}".replace(",", "." if lang == "id" else ","),
                transform=ax.transAxes, fontsize=8.2, fontweight="bold", ha="left", va="bottom", zorder=30)

    # Inset
    ax_in = fig.add_axes([0.700, 0.725, 0.275, 0.170])
    ax_in.set_facecolor("#f7f7f7")
    draw_layer(ax_in, SRC["sumbar"], 4326, facecolor="#e8e8e8", edgecolor="#7d7d7d", linewidth=0.35, alpha=1.0, zorder=1)
    draw_layer(ax_in, SRC["das"], 4326, facecolor="#d62828", edgecolor="#8b0000", linewidth=0.8, alpha=0.88, zorder=4)
    style_axes(ax_in, inset_extent)
    ax_in.set_title(t["inset"], fontsize=9.2, fontweight="bold", pad=5)

    # Legend
    ax_leg = fig.add_axes([0.700, 0.505, 0.275, 0.185])
    panel(ax_leg, "white")
    ax_leg.text(0.035,0.93,t["legend"],transform=ax_leg.transAxes,fontsize=11,fontweight="bold",va="top")
    handles = [
        Patch(facecolor="white", edgecolor="#1677aa", hatch="////", label=t["das"]),
        Line2D([0],[0], color="#2385c6", lw=1.4, label=t["rbi"]),
        Line2D([0],[0], color="#888888", lw=0.9, label=t["kec"]),
        Patch(facecolor="#c7df00", edgecolor="#718c00", label=t["kuranji"]),
        Patch(facecolor="#93c95b", edgecolor="#4f7f32", label=t["pauh"]),
    ]
    ax_leg.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.025,0.77), frameon=False,
                  fontsize=8.6, labelspacing=0.75, handlelength=2.1)

    # Result summary
    ax_sum = fig.add_axes([0.700, 0.275, 0.275, 0.195])
    panel(ax_sum)
    ax_sum.text(0.035,0.93,t["summary"],transform=ax_sum.transAxes,fontsize=11,fontweight="bold",va="top")
    y = 0.79
    for line in t["summary_lines"]:
        wrapped = textwrap.fill("• " + line, width=48, subsequent_indent="  ")
        ax_sum.text(0.035,y,wrapped,transform=ax_sum.transAxes,fontsize=8.1,va="top",linespacing=1.18,color="#222")
        y -= 0.135 if len(wrapped) < 82 else 0.175

    # Source / CRS / caption
    ax_src = fig.add_axes([0.700, 0.070, 0.275, 0.165])
    panel(ax_src)
    ax_src.text(0.035,0.92,t["source"],transform=ax_src.transAxes,fontsize=10.2,fontweight="bold",va="top")
    y = 0.79
    for line in t["source_lines"]:
        ax_src.text(0.035,y,line,transform=ax_src.transAxes,fontsize=7.2,va="top",color="#333")
        y -= 0.095
    ax_src.text(0.035,0.055,textwrap.fill(t["caption"],52),transform=ax_src.transAxes,fontsize=7.0,va="bottom",color="#333")

    # Wide scientific note at bottom-left like the reference layout.
    ax_note = fig.add_axes([0.025, 0.070, 0.655, 0.095])
    panel(ax_note)
    ax_note.text(0.015,0.83,t["note"],transform=ax_note.transAxes,fontsize=10.2,fontweight="bold",va="top")
    ax_note.text(0.015,0.48,textwrap.fill(t["note_text"],145),transform=ax_note.transAxes,fontsize=7.7,va="top",linespacing=1.22,color="#333")

    fig.savefig(png, dpi=dpi, facecolor="white")
    fig.savefig(pdf, dpi=dpi, facecolor="white")
    plt.close(fig)

    info = {
        "map_id": "5.1",
        "renderer": "matplotlib_v2_publication_style",
        "language": lang,
        "dpi": dpi,
        "png": str(png),
        "pdf": str(pdf),
        "png_bytes": png.stat().st_size if png.exists() else 0,
        "pdf_bytes": pdf.stat().st_size if pdf.exists() else 0,
        "focus_class_counts": focus_counts,
        "scale_denominator_approx": scale_denom,
        "guardrail": "cartographic rendering only; frozen Stage 1-2 analysis preserved",
    }
    meta.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"RENDER_V2_OK lang={lang} png={png} bytes={info['png_bytes']}")
    print(f"RENDER_V2_OK lang={lang} pdf={pdf} bytes={info['pdf_bytes']}")


def main():
    missing = [str(p) for p in SRC.values() if not Path(p).exists()]
    if missing:
        print("SOURCE_PREFLIGHT=FAIL")
        for p in missing:
            print("MISSING=" + p)
        raise SystemExit(2)
    print("SOURCE_PREFLIGHT=PASS")
    langs = [x.strip().lower() for x in base.args.lang.split(",") if x.strip()]
    for lang in langs:
        if lang not in TEXT:
            raise SystemExit(f"Unsupported language={lang}")
        render(lang, base.args.dpi)
    print(f"FINAL_STATUS=COMPLETE rendered={len(langs)}")


if __name__ == "__main__":
    main()
