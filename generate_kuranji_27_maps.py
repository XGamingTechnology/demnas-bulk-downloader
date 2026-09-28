#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the 27 final QGIS report maps for the Batang Kuranji Stage 1-4 study.

Designed for the frozen repository structure under:
    /opt/demnas-bulk-downloader

QGIS target:
    QGIS / PyQGIS 3.34.x (Ubuntu 24.04 package is 3.34.4-Prizren)

Scientific guardrails:
- This script DOES NOT recalculate Stage 1-4 analytical products.
- It only reads frozen rasters/vectors/tables and creates cartographic layouts.
- It DOES NOT calculate delta-h, delta-DEM, pre/post GFI, or a new hazard score.
- Sentinel-1 is visualised as surface-state/backscatter change evidence.

Outputs:
    artifacts/KURANJI_FINAL_27_MAPS/
        05_STAGE1/*.png|pdf|qpt
        06_STAGE2/*.png|pdf|qpt
        07_STAGE3/*.png|pdf|qpt
        08_STAGE4/*.png|pdf|qpt
        KURANJI_FINAL_27_MAPS.qgz
        MAP_MANIFEST.csv
        SOURCE_PREFLIGHT.txt
        KURANJI_FINAL_27_MAPS.zip

Safe first run:
    QT_QPA_PLATFORM=offscreen python3 generate_kuranji_27_maps.py --preflight-only

Full run:
    QT_QPA_PLATFORM=offscreen python3 generate_kuranji_27_maps.py

Optional subset:
    QT_QPA_PLATFORM=offscreen python3 generate_kuranji_27_maps.py --only 5.1,5.2,6.7
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import traceback
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsColorRampShader,
    QgsContrastEnhancement,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFillSymbol,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemPage,
    QgsLayoutItemPicture,
    QgsLayoutItemScaleBar,
    QgsLayoutItemShape,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPalettedRasterRenderer,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsRasterShader,
    QgsReadWriteContext,
    QgsRectangle,
    QgsSingleBandGrayRenderer,
    QgsSingleBandPseudoColorRenderer,
    QgsSingleSymbolRenderer,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont


# -----------------------------------------------------------------------------
# CLI / PATHS
# -----------------------------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--preflight-only", action="store_true", help="Validate all required sources only")
parser.add_argument("--only", default="", help="Comma-separated map ids, e.g. 5.1,6.7,8.3")
parser.add_argument("--dpi", type=int, default=300)
args = parser.parse_args()

ROOT = Path(os.environ.get("KURANJI_ROOT", "/opt/demnas-bulk-downloader")).resolve()
K = ROOT / "data/work/kuranji"
A2 = ROOT / "artifacts/KURANJI_TAHAP2_SPATIAL_LAYOUT"
A3 = ROOT / "artifacts/KURANJI_TAHAP3_SPATIAL_LAYOUT"
A4 = ROOT / "artifacts/KURANJI_TAHAP4_SPATIAL_LAYOUT"
S1V = K / "05_validation/conditioning_sensitivity"
OUT = ROOT / "artifacts/KURANJI_FINAL_27_MAPS"
OUT.mkdir(parents=True, exist_ok=True)
for sub in ("05_STAGE1", "06_STAGE2", "07_STAGE3", "08_STAGE4"):
    (OUT / sub).mkdir(parents=True, exist_ok=True)

SELECTED = {x.strip() for x in args.only.split(",") if x.strip()}


def wanted(map_id: str) -> bool:
    return not SELECTED or map_id in SELECTED


# -----------------------------------------------------------------------------
# EXACT FROZEN SOURCES
# -----------------------------------------------------------------------------
SRC = {
    # Reference
    "das": K / "01_prepared/DAS_KURANJI_UTM47S.geojson",
    "rbi": K / "01_prepared/SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson",
    "sumbar": ROOT / "data shp/data_administrasi/Sumatera_Barat.shp",
    "kecamatan_raw": ROOT / "data shp/data_administrasi/Kecamatan.shp",
    "admin_all": A2 / "05_ADMIN_VECTOR/ADMIN_ALL_INTERSECTING_UTM47S.geojson",
    "admin_focus": A2 / "05_ADMIN_VECTOR/ADMIN_FOCUS_PAUH_KURANJI_18_UTM47S.geojson",

    # Stage 1
    "dem_breach100": S1V / "BREACH100_DEM.tif",
    "flowacc_breach100": S1V / "BREACH100_FLOW_ACCUM_CELLS.tif",
    "stream6": K / "03_watershed/STREAM_FINAL_6KM2.tif",
    "pour_point": S1V / "BREACH100_POUR_POINT.tif",
    "watershed": S1V / "BREACH100_WATERSHED.tif",
    "ref_only": S1V / "BREACH100_REF_ONLY.tif",
    "model_only": S1V / "BREACH100_MODEL_ONLY.tif",
    "residual_components": S1V / "BREACH_RESIDUAL_COMPONENTS.geojson",

    # Stage 2
    "gfi_raw": A2 / "02_GFI/06_GFI_RAW.tif",
    "gfi_norm": A2 / "02_GFI/07_GFI_NORMALIZED.tif",
    "p175_wd": A2 / "03_P175/P175_WD_INPUT.tif",
    "p175_index": A2 / "03_P175/P175_HAZARD_INDEX.tif",
    "p175_class": A2 / "03_P175/P175_HAZARD_CLASS.tif",
    "m175_class": A2 / "04_SENSITIVITY/M175_HAZARD_CLASS.tif",
    "m250_class": A2 / "04_SENSITIVITY/M250_HAZARD_CLASS.tif",
    "p250_class": A2 / "04_SENSITIVITY/P250_HAZARD_CLASS.tif",

    # Stage 2 QML
    "qml_admin": A2 / "09_QGIS_STYLE/ADMIN_BOUNDARY.qml",
    "qml_focus": A2 / "09_QGIS_STYLE/FOCUS_BOUNDARY.qml",
    "qml_gfi_raw": A2 / "09_QGIS_STYLE/GFI_RAW.qml",
    "qml_gfi_norm": A2 / "09_QGIS_STYLE/GFI_NORMALIZED.qml",
    "qml_p175_wd": A2 / "09_QGIS_STYLE/P175_WD.qml",
    "qml_p175_index": A2 / "09_QGIS_STYLE/P175_HAZARD_INDEX.qml",
    "qml_p175_class": A2 / "09_QGIS_STYLE/P175_HAZARD_CLASS.qml",

    # Stage 3
    "observed": A3 / "02_OBSERVED_BIG_BRIN/OBSERVED_BIG_BRIN_20251201.tif",
    "observed_vector": A3 / "02_OBSERVED_BIG_BRIN/layer3_kuranji_clip_utm47s.geojson",
    "p_confusion": A3 / "04_VALIDATION_RASTER/P_DOMAIN_CONFUSION.tif",
    "m_confusion": A3 / "04_VALIDATION_RASTER/M_DOMAIN_CONFUSION.tif",
    "a3_p175_class": A3 / "03_MODEL_SCENARIOS/P175_HAZARD_CLASS.tif",
    "a3_m175_class": A3 / "03_MODEL_SCENARIOS/M175_HAZARD_CLASS.tif",
    "a3_admin_all": A3 / "01_REFERENCE/ADMIN_ALL_INTERSECTING_UTM47S.geojson",
    "a3_admin_focus": A3 / "01_REFERENCE/ADMIN_FOCUS_PAUH_KURANJI_18_UTM47S.geojson",

    # Stage 3 QML
    "qml_observed": A3 / "09_QGIS_STYLE/OBSERVED_BIG_BRIN.qml",
    "qml_pconf": A3 / "09_QGIS_STYLE/P_DOMAIN_CONFUSION.qml",
    "qml_mconf": A3 / "09_QGIS_STYLE/M_DOMAIN_CONFUSION.qml",
    "qml_a3_p175": A3 / "09_QGIS_STYLE/P175_HAZARD_CLASS.qml",
    "qml_a3_m175": A3 / "09_QGIS_STYLE/M175_HAZARD_CLASS.qml",
    "qml_a3_admin": A3 / "09_QGIS_STYLE/ADMIN_BOUNDARY.qml",
    "qml_das": A3 / "09_QGIS_STYLE/DAS_BOUNDARY.qml",

    # Stage 4
    "s1_event_vv": A4 / "03_SENTINEL1_CHANGE/EVENT_MINUS_PRE_VV_dB_med3_20m_DAS.tif",
    "s1_event_vh": A4 / "03_SENTINEL1_CHANGE/EVENT_MINUS_PRE_VH_dB_med3_20m_DAS.tif",
    "s1_event_ratio": A4 / "03_SENTINEL1_CHANGE/EVENT_MINUS_PRE_VHminusVV_dB_med3_20m_DAS.tif",
    "s1_post_vv": A4 / "03_SENTINEL1_CHANGE/POST_MINUS_PRE_VV_dB_med3_20m_DAS.tif",
    "s1_post_vh": A4 / "03_SENTINEL1_CHANGE/POST_MINUS_PRE_VH_dB_med3_20m_DAS.tif",
    "s1_post_ratio": A4 / "03_SENTINEL1_CHANGE/POST_MINUS_PRE_VHminusVV_dB_med3_20m_DAS.tif",
    "observed20": A4 / "05_STAGE3_OVERLAY/OBSERVED_BIG_BRIN_20251201_20m.tif",
    "p175domain20": A4 / "05_STAGE3_OVERLAY/P175_DOMAIN_20m.tif",
    "fn20": A4 / "05_STAGE3_OVERLAY/STAGE3_FN_20m.tif",
    "validation20": A4 / "07_INTEGRATION/STAGE3_VALIDATION_CATEGORIES_20m.tif",
    "stream20": A4 / "07_INTEGRATION/STREAM_FINAL_6KM2_20m_VIS.tif",
    "integration_png": A4 / "07_INTEGRATION/STAGE4_INTEGRATED_MULTIMODAL_EVIDENCE.png",
    "icesat_pre_csv": A4 / "06_ICESAT2/csv/ATL08_RGT0453_2025-10-14_all_beams.csv",
    "icesat_post_csv": A4 / "06_ICESAT2/csv/ATL08_RGT0453_2026-01-13_all_beams.csv",
    "icesat_geom": A4 / "06_ICESAT2/ICESAT2_REPEAT_TRACK_GEOMETRY_AUDIT.json",
}

REQUIRED = list(SRC.keys())


# -----------------------------------------------------------------------------
# PREFLIGHT
# -----------------------------------------------------------------------------
def preflight() -> bool:
    lines = []
    missing = []
    lines.append("=== KURANJI 27-MAP SOURCE PREFLIGHT ===")
    lines.append(f"QGIS={Qgis.QGIS_VERSION}")
    lines.append(f"ROOT={ROOT}")
    for key in REQUIRED:
        p = SRC[key]
        ok = p.exists()
        lines.append(f"{'OK' if ok else 'MISSING'}\t{key}\t{p}")
        if not ok:
            missing.append((key, p))
    lines.append("")
    lines.append(f"TOTAL={len(REQUIRED)}")
    lines.append(f"MISSING={len(missing)}")
    lines.append("PREFLIGHT_STATUS=" + ("PASS" if not missing else "FAIL"))
    text = "\n".join(lines) + "\n"
    (OUT / "SOURCE_PREFLIGHT.txt").write_text(text, encoding="utf-8")
    print(text)
    return not missing


if not preflight():
    sys.exit(2)
if args.preflight_only:
    print("PRELIGHT_ONLY=COMPLETE")
    sys.exit(0)


# -----------------------------------------------------------------------------
# QGIS INIT
# -----------------------------------------------------------------------------
QgsApplication.setPrefixPath("/usr", True)
qgs = QgsApplication([], False)
qgs.initQgis()

project = QgsProject.instance()
project.clear()
project.setCrs(QgsCoordinateReferenceSystem("EPSG:32747"))
LAYOUT_MANAGER = project.layoutManager()

FONT = "DejaVu Sans"
S1_LIMIT = 3.44645357131958
manifest_rows = []


# -----------------------------------------------------------------------------
# BASIC LAYER / STYLE HELPERS
# -----------------------------------------------------------------------------
def add_to_project(layer):
    if layer is not None and layer.isValid():
        project.addMapLayer(layer, False)
    return layer


def load_vector(path: Path, name: str, qml: Path | None = None):
    lyr = QgsVectorLayer(str(path), name, "ogr")
    if not lyr.isValid():
        raise RuntimeError(f"Invalid vector: {path}")
    add_to_project(lyr)
    if qml and qml.exists():
        lyr.loadNamedStyle(str(qml))
        lyr.triggerRepaint()
    return lyr


def load_raster(path: Path, name: str, qml: Path | None = None):
    lyr = QgsRasterLayer(str(path), name)
    if not lyr.isValid():
        raise RuntimeError(f"Invalid raster: {path}")
    add_to_project(lyr)
    if qml and qml.exists():
        lyr.loadNamedStyle(str(qml))
        lyr.triggerRepaint()
    return lyr


def set_raster_opacity(layer, opacity: float):
    if layer and layer.renderer():
        layer.renderer().setOpacity(opacity)
        layer.triggerRepaint()


def style_polygon(layer, fill=(255,255,255,0), outline=(30,30,30,255), width=0.6):
    sym = QgsFillSymbol.createSimple({
        "color": f"{fill[0]},{fill[1]},{fill[2]},{fill[3]}",
        "outline_color": f"{outline[0]},{outline[1]},{outline[2]},{outline[3]}",
        "outline_width": str(width),
    })
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.triggerRepaint()


def style_line(layer, color=(0,100,220,255), width=0.7):
    sym = QgsLineSymbol.createSimple({
        "color": f"{color[0]},{color[1]},{color[2]},{color[3]}",
        "width": str(width),
    })
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.triggerRepaint()


def style_point(layer, color=(30,100,220,255), size=2.0, shape="circle"):
    sym = QgsMarkerSymbol.createSimple({
        "name": shape,
        "color": f"{color[0]},{color[1]},{color[2]},{color[3]}",
        "outline_color": "255,255,255,255",
        "outline_width": "0.2",
        "size": str(size),
    })
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.triggerRepaint()


def style_binary(layer, color: QColor, label: str, value=1, opacity=1.0):
    classes = [
        QgsPalettedRasterRenderer.Class(0, QColor(255,255,255,0), "Background"),
        QgsPalettedRasterRenderer.Class(value, color, label),
    ]
    layer.setRenderer(QgsPalettedRasterRenderer(layer.dataProvider(), 1, classes))
    layer.renderer().setOpacity(opacity)
    layer.triggerRepaint()


def style_dem(layer):
    stats = layer.dataProvider().bandStatistics(1)
    mn, mx = stats.minimumValue, stats.maximumValue
    span = max(mx - mn, 1.0)
    shader_func = QgsColorRampShader()
    shader_func.setColorRampType(QgsColorRampShader.Interpolated)
    shader_func.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(mn, QColor("#2c7bb6"), f"{mn:.0f} m"),
        QgsColorRampShader.ColorRampItem(mn + 0.25*span, QColor("#abd9e9"), "low"),
        QgsColorRampShader.ColorRampItem(mn + 0.50*span, QColor("#ffffbf"), "mid"),
        QgsColorRampShader.ColorRampItem(mn + 0.75*span, QColor("#fdae61"), "high"),
        QgsColorRampShader.ColorRampItem(mx, QColor("#8c2d04"), f"{mx:.0f} m"),
    ])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(shader_func)
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader))
    layer.triggerRepaint()


def style_flowacc(layer):
    stats = layer.dataProvider().bandStatistics(1)
    mx = max(stats.maximumValue, 10.0)
    vals = [1.0, mx**0.25, mx**0.50, mx**0.75, mx]
    colors = ["#f7fbff", "#c6dbef", "#6baed6", "#2171b5", "#08306b"]
    shader_func = QgsColorRampShader()
    shader_func.setColorRampType(QgsColorRampShader.Interpolated)
    shader_func.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(v, QColor(c), f"{v:.0f}")
        for v, c in zip(vals, colors)
    ])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(shader_func)
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader))
    layer.triggerRepaint()


def style_diverging(layer, limit=S1_LIMIT):
    items = [
        (-limit, "#313695", f"-{limit:.2f} dB"),
        (-limit/2, "#74add1", "negative"),
        (0.0, "#f7f7f7", "0 dB"),
        (limit/2, "#f46d43", "positive"),
        (limit, "#a50026", f"+{limit:.2f} dB"),
    ]
    func = QgsColorRampShader()
    func.setColorRampType(QgsColorRampShader.Interpolated)
    func.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(v, QColor(c), lab) for v, c, lab in items
    ])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(func)
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader))
    layer.triggerRepaint()


def label_field(layer, preferred=None):
    if preferred is None:
        preferred = [
            "NAMOBJ", "WADMKD", "KELURAHAN", "DESA", "NAMA_DESA", "NAMA_KEL",
            "WADMKC", "KECAMATAN", "NAMA_KEC", "NAME_4", "NAME_3", "name", "NAME"
        ]
    existing = {f.name().lower(): f.name() for f in layer.fields()}
    for cand in preferred:
        if cand.lower() in existing:
            return existing[cand.lower()]
    return None


def enable_labels(layer, size=7.0, color="#222222"):
    fld = label_field(layer)
    if not fld:
        return None
    pal = QgsPalLayerSettings()
    pal.fieldName = fld
    pal.enabled = True
    pal.placement = QgsPalLayerSettings.OverPoint
    fmt = QgsTextFormat()
    fmt.setFont(QFont(FONT, int(size)))
    fmt.setSize(size)
    fmt.setColor(QColor(color))
    pal.setFormat(fmt)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()
    return fld


def transform_extent(layer, margin=0.04):
    ext = QgsRectangle(layer.extent())
    if layer.crs().isValid() and layer.crs() != project.crs():
        tr = QgsCoordinateTransform(layer.crs(), project.crs(), project.transformContext())
        ext = tr.transformBoundingBox(ext)
    ext.grow(max(ext.width(), ext.height()) * margin)
    return ext


def union_extent(layers, margin=0.05):
    valid = [x for x in layers if x is not None and x.isValid()]
    if not valid:
        return QgsRectangle(0, 0, 1, 1)
    ext = transform_extent(valid[0], 0)
    for lyr in valid[1:]:
        ext.combineExtentWith(transform_extent(lyr, 0))
    ext.grow(max(ext.width(), ext.height()) * margin)
    return ext


# -----------------------------------------------------------------------------
# LAYOUT HELPERS
# -----------------------------------------------------------------------------
def remove_layout(name):
    old = LAYOUT_MANAGER.layoutByName(name)
    if old:
        LAYOUT_MANAGER.removeLayout(old)


def new_layout(name, paper="A4L"):
    remove_layout(name)
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(name)
    page = layout.pageCollection().page(0)
    if paper == "A3L":
        page.setPageSize(QgsLayoutSize(420, 297, QgsUnitTypes.LayoutMillimeters))
    elif paper == "A4P":
        page.setPageSize(QgsLayoutSize(210, 297, QgsUnitTypes.LayoutMillimeters))
    else:
        page.setPageSize(QgsLayoutSize(297, 210, QgsUnitTypes.LayoutMillimeters))
    LAYOUT_MANAGER.addLayout(layout)
    return layout


def add_label(layout, text, x, y, w, h, size=9, bold=False, align=Qt.AlignLeft, color="#222222"):
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    font = QFont(FONT, int(size))
    font.setBold(bold)
    item.setFont(font)
    item.setFontColor(QColor(color))
    item.setHAlign(align)
    item.setVAlign(Qt.AlignVCenter)
    item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    item.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(item)
    return item


def add_note_box(layout, title, text, x, y, w, h):
    shape = QgsLayoutItemShape(layout)
    shape.setShapeType(QgsLayoutItemShape.Rectangle)
    shape.setSymbol(QgsFillSymbol.createSimple({
        "color": "248,248,248,255",
        "outline_color": "120,120,120,255",
        "outline_width": "0.25",
    }))
    shape.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    shape.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(shape)
    add_label(layout, title, x+2, y+1, w-4, 6, size=7.5, bold=True)
    add_label(layout, text, x+2, y+7, w-4, h-9, size=6.2)
    return shape


def add_map(layout, item_id, x, y, w, h, layers, extent):
    m = QgsLayoutItemMap(layout)
    m.setId(item_id)
    m.setFrameEnabled(True)
    m.setExtent(extent)
    m.setLayers([lyr for lyr in layers if lyr is not None])
    try:
        m.setKeepLayerSet(True)
    except Exception:
        pass
    m.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    m.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(m)
    return m


def add_legend(layout, linked_map, x, y, w, h, title="LEGENDA"):
    leg = QgsLayoutItemLegend(layout)
    leg.setTitle(title)
    leg.setLinkedMap(linked_map)
    leg.setAutoUpdateModel(True)
    try:
        leg.setLegendFilterByMapEnabled(True)
    except Exception:
        pass
    leg.setFrameEnabled(True)
    leg.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    leg.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(leg)
    return leg


def add_north(layout, x, y, w=10, h=14):
    pic = QgsLayoutItemPicture(layout)
    candidates = [
        Path(QgsApplication.pkgDataPath()) / "svg/arrows/NorthArrow_03.svg",
        Path(QgsApplication.pkgDataPath()) / "svg/arrows/NorthArrow_01.svg",
    ]
    for c in candidates:
        if c.exists():
            pic.setPicturePath(str(c))
            break
    pic.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    pic.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(pic)
    return pic


def add_scalebar(layout, linked_map, x, y, w=45, h=8):
    sb = QgsLayoutItemScaleBar(layout)
    sb.setStyle("Single Box")
    sb.setLinkedMap(linked_map)
    sb.setNumberOfSegments(4)
    sb.setNumberOfSegmentsLeft(0)
    sb.setUnits(QgsUnitTypes.DistanceKilometers)
    sb.setUnitLabel("km")
    sb.applyDefaultSize()
    sb.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    sb.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(sb)
    return sb


def add_picture(layout, path, x, y, w, h):
    pic = QgsLayoutItemPicture(layout)
    pic.setPicturePath(str(path))
    try:
        pic.setResizeMode(QgsLayoutItemPicture.ZoomResizeFrame)
    except Exception:
        pass
    pic.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    pic.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(pic)
    return pic


def standard_single(map_id, title, subtitle, layers, extent, note, source_note="EPSG:32747 · sumber sesuai Stage 1-4 frozen outputs"):
    layout = new_layout(f"PETA_{map_id.replace('.', '_')}", "A4L")
    add_label(layout, f"Peta {map_id}. {title}", 8, 5, 281, 10, size=14, bold=True, align=Qt.AlignCenter)
    add_label(layout, subtitle, 8, 15, 281, 6, size=7.5, align=Qt.AlignCenter, color="#555555")
    m = add_map(layout, "MAP_MAIN", 8, 25, 218, 158, layers, extent)
    add_legend(layout, m, 230, 25, 59, 92)
    add_note_box(layout, "CATATAN INTERPRETASI", note, 230, 121, 59, 62)
    add_north(layout, 14, 31)
    add_scalebar(layout, m, 17, 170)
    add_label(layout, source_note, 8, 188, 281, 9, size=6.2, color="#555555")
    return layout


def export_layout(layout, map_id, slug, stage_dir, dpi):
    folder = OUT / stage_dir
    base = f"PETA_{map_id.replace('.', '_')}_{slug}"
    png = folder / f"{base}.png"
    pdf = folder / f"{base}.pdf"
    qpt = folder / f"{base}.qpt"
    exporter = QgsLayoutExporter(layout)
    img_settings = QgsLayoutExporter.ImageExportSettings()
    img_settings.dpi = dpi
    pdf_settings = QgsLayoutExporter.PdfExportSettings()
    pdf_settings.dpi = dpi
    r_img = exporter.exportToImage(str(png), img_settings)
    r_pdf = exporter.exportToPdf(str(pdf), pdf_settings)
    r_qpt = layout.saveAsTemplate(str(qpt), QgsReadWriteContext())
    ok = (r_img == QgsLayoutExporter.Success and r_pdf == QgsLayoutExporter.Success and bool(r_qpt))
    manifest_rows.append({
        "map_id": map_id,
        "slug": slug,
        "png": str(png.relative_to(ROOT)),
        "pdf": str(pdf.relative_to(ROOT)),
        "qpt": str(qpt.relative_to(ROOT)),
        "png_status": str(r_img),
        "pdf_status": str(r_pdf),
        "qpt_status": str(bool(r_qpt)),
        "status": "OK" if ok else "REVIEW",
    })
    print(f"[EXPORT] {map_id} {slug}: {'OK' if ok else 'REVIEW'}")
    return ok


# -----------------------------------------------------------------------------
# MAP BUILDERS
# -----------------------------------------------------------------------------
def map_5_1():
    das = load_vector(SRC["das"], "DAS Kuranji")
    style_polygon(das, outline=(20,20,20,255), width=0.9)
    admin = load_vector(SRC["admin_all"], "Administrasi yang beririsan", SRC["qml_admin"])
    rbi = load_vector(SRC["rbi"], "Sungai RBI")
    style_line(rbi, (25,105,210,220), 0.5)
    sumbar = load_vector(SRC["sumbar"], "Sumatera Barat")
    style_polygon(sumbar, fill=(235,235,235,100), outline=(90,90,90,220), width=0.35)

    layout = new_layout("PETA_5_1", "A4L")
    add_label(layout, "Peta 5.1. Lokasi Penelitian DAS Batang Kuranji", 8, 5, 281, 10, size=14, bold=True, align=Qt.AlignCenter)
    add_label(layout, "Konteks DAS dan fokus administrasi Pauh-Kuranji", 8, 15, 281, 6, size=7.5, align=Qt.AlignCenter, color="#555555")
    main = add_map(layout, "MAP_MAIN", 8, 25, 205, 158, [das, rbi, admin], transform_extent(das, 0.04))
    inset = add_map(layout, "MAP_INSET", 218, 25, 71, 50, [das, sumbar], transform_extent(sumbar, 0.03))
    add_legend(layout, main, 218, 80, 71, 58)
    add_note_box(layout, "KONTEKS", "Pemodelan fisik menggunakan seluruh DAS; Pauh dan Kuranji adalah fokus administratif, bukan batas proses hidrologi.", 218, 143, 71, 40)
    add_north(layout, 14, 31)
    add_scalebar(layout, main, 17, 170)
    add_label(layout, "CRS utama EPSG:32747 · DAS, RBI, dan administrasi dari paket frozen penelitian.", 8, 188, 281, 9, size=6.2, color="#555555")
    return layout


def map_5_2():
    dem = load_raster(SRC["dem_breach100"], "BREACH100 DEM")
    style_dem(dem)
    das = load_vector(SRC["das"], "DAS Kuranji"); style_polygon(das, outline=(20,20,20,255), width=0.8)
    rbi = load_vector(SRC["rbi"], "Sungai RBI"); style_line(rbi, (20,95,210,220), 0.45)
    return standard_single("5.2", "DEM dan Topografi", "Baseline terrain BREACH100", [das, rbi, dem], transform_extent(das), "BREACH100 dipilih sebagai conditioning baseline Stage 1. Peta ini menggambarkan topografi baseline, bukan terrain pascakejadian.")


def map_5_3():
    fa = load_raster(SRC["flowacc_breach100"], "Flow Accumulation (cells)"); style_flowacc(fa)
    das = load_vector(SRC["das"], "DAS Kuranji"); style_polygon(das, outline=(20,20,20,255), width=0.8)
    rbi = load_vector(SRC["rbi"], "Sungai RBI"); style_line(rbi, (15,80,190,210), 0.4)
    pp = load_raster(SRC["pour_point"], "Outlet / Pour Point"); style_binary(pp, QColor("#ff00aa"), "Pour point", 1, 1.0)
    return standard_single("5.3", "Flow Accumulation", "BREACH100 D8 flow accumulation", [pp, das, rbi, fa], transform_extent(das), "Flow accumulation adalah produk routing Stage 1. Warna digunakan untuk visualisasi struktur akumulasi; tidak mengubah threshold drainase frozen 6 km².")


def map_5_4():
    stream = load_raster(SRC["stream6"], "Modeled stream ≥6 km²"); style_binary(stream, QColor("#0033cc"), "Modeled stream ≥6 km²", 1)
    rbi = load_vector(SRC["rbi"], "Sungai RBI"); style_line(rbi, (220,55,45,235), 0.8)
    das = load_vector(SRC["das"], "DAS Kuranji"); style_polygon(das, outline=(20,20,20,255), width=0.8)
    pp = load_raster(SRC["pour_point"], "Outlet"); style_binary(pp, QColor("#ff00aa"), "Outlet", 1)
    return standard_single("5.4", "Jaringan Sungai Final 6 km² vs RBI", "Validasi visual modeled drainage terhadap RBI", [pp, das, rbi, stream], transform_extent(das), "Threshold 6 km² menghasilkan network sekitar 81.00 km dibanding RBI 79.813 km. RBI adalah reference, bukan target yang dipaksakan 100%.")


def map_5_5():
    model = load_raster(SRC["watershed"], "Watershed model"); style_binary(model, QColor(61,130,246,110), "Model watershed", 1, 0.55)
    refonly = load_raster(SRC["ref_only"], "Reference-only"); style_binary(refonly, QColor(210,50,50,220), "Reference-only", 1)
    modelonly = load_raster(SRC["model_only"], "Model-only"); style_binary(modelonly, QColor(245,145,35,220), "Model-only", 1)
    das = load_vector(SRC["das"], "Reference DAS"); style_polygon(das, outline=(20,20,20,255), width=1.0)
    return standard_single("5.5", "Watershed Model vs DAS Referensi", "BREACH100 overlap dan residual mismatch", [das, modelonly, refonly, model], transform_extent(das), "Stage 1 frozen: watershed model 212.125 km²; IoU 0.9161; Dice 0.9562. Residual reference-only dan model-only dipertahankan sebagai uncertainty.")


def map_5_6():
    refonly = load_raster(SRC["ref_only"], "Reference-only"); style_binary(refonly, QColor(210,50,50,210), "Reference-only", 1)
    modelonly = load_raster(SRC["model_only"], "Model-only"); style_binary(modelonly, QColor(245,145,35,210), "Model-only", 1)
    res = load_vector(SRC["residual_components"], "Residual components")
    # Geometry type may vary; use transparent polygon style as a safe default.
    try:
        style_polygon(res, fill=(180,0,180,35), outline=(170,0,170,230), width=0.55)
    except Exception:
        try: style_line(res, (170,0,170,230), 0.6)
        except Exception: pass
    rbi = load_vector(SRC["rbi"], "Sungai RBI"); style_line(rbi, (20,100,220,210), 0.45)
    das = load_vector(SRC["das"], "Reference DAS"); style_polygon(das, outline=(20,20,20,255), width=0.9)
    return standard_single("5.6", "Residual Mismatch dan Uncertainty", "Residual spatial mismatch Stage 1", [res, das, rbi, modelonly, refonly], transform_extent(das), "Peta ini menunjukkan mismatch yang sengaja tidak dihapus melalui retuning. Residual menjadi uncertainty audit, bukan alasan untuk memaksa model mengikuti reference secara sirkular.")


def map_6_1():
    admin = load_vector(SRC["admin_all"], "Administrasi beririsan", SRC["qml_admin"])
    das = load_vector(SRC["das"], "DAS Kuranji"); style_polygon(das, outline=(20,20,20,255), width=1.0)
    return standard_single("6.1", "Lokasi DAS dan Administrasi", "Wilayah administratif yang beririsan dengan DAS", [das, admin], transform_extent(das), "DAS beririsan dengan 3 kabupaten/kota, 10 kecamatan, dan 41 desa/kelurahan. Pauh dan Kuranji adalah focus area administratif.")


def map_6_2():
    stream = load_raster(SRC["stream6"], "Modeled drainage 6 km²"); style_binary(stream, QColor("#0033cc"), "Modeled drainage 6 km²", 1)
    rbi = load_vector(SRC["rbi"], "Sungai RBI"); style_line(rbi, (220,55,45,235), 0.8)
    das = load_vector(SRC["das"], "DAS Kuranji"); style_polygon(das, outline=(20,20,20,255), width=0.8)
    return standard_single("6.2", "Jaringan Sungai RBI dan Baseline Drainase", "Reference river vs modeled drainage", [das, rbi, stream], transform_extent(das), "Jaringan lokal 6 km² dipertahankan sebagai drainage baseline untuk GFI karena panjang dan topology lebih seimbang terhadap RBI.")


def map_6_3():
    gfi = load_raster(SRC["gfi_raw"], "GFI Raw", SRC["qml_gfi_raw"])
    das = load_vector(SRC["das"], "DAS Kuranji"); style_polygon(das, outline=(20,20,20,255), width=0.8)
    return standard_single("6.3", "GFI Raw", "Distribusi Geomorphic Flood Index mentah", [das, gfi], transform_extent(das), "GFI raw = ln(hr/H). Nilai ini merupakan baseline geomorphic screening variable, bukan observed inundation.")


def map_6_4():
    gfi = load_raster(SRC["gfi_norm"], "GFI Normalized", SRC["qml_gfi_norm"])
    das = load_vector(SRC["das"], "DAS Kuranji"); style_polygon(das, outline=(20,20,20,255), width=0.8)
    return standard_single("6.4", "GFI Normalized", "GFI ternormalisasi pada baseline Stage 2", [das, gfi], transform_extent(das), "Manual threshold -0.53 dipertahankan sebagai sensitivity domain, tetapi primary physical domain Stage 2 memakai WD > 0 / GFI_raw > 0.")


def map_6_5():
    wd = load_raster(SRC["p175_wd"], "P175 Water Depth Input", SRC["qml_p175_wd"])
    das = load_vector(SRC["das"], "DAS Kuranji"); style_polygon(das, outline=(20,20,20,255), width=0.8)
    return standard_single("6.5", "Water Depth P175", "Domain dan modeled water depth untuk P175", [das, wd], transform_extent(das), "P175 menggunakan domain WD > 0. Water depth adalah modeled geomorphic quantity dari workflow GFI, bukan measured flood depth.")


def map_6_6():
    idx = load_raster(SRC["p175_index"], "P175 Hazard Index", SRC["qml_p175_index"])
    das = load_vector(SRC["das"], "DAS Kuranji"); style_polygon(das, outline=(20,20,20,255), width=0.8)
    return standard_single("6.6", "Indeks Bahaya P175", "Fuzzy Large hazard index 0-1", [das, idx], transform_extent(das), "Fuzzy Large: midpoint 1.125 m, spread 1.75. P175 adalah primary baseline hazard candidate, bukan probabilistic return-period hazard.")


def map_6_7():
    hz = load_raster(SRC["p175_class"], "P175 Hazard Class", SRC["qml_p175_class"])
    admin = load_vector(SRC["admin_all"], "Administrasi", SRC["qml_admin"])
    das = load_vector(SRC["das"], "DAS Kuranji"); style_polygon(das, outline=(20,20,20,255), width=0.9)
    return standard_single("6.7", "Kelas Bahaya P175 Seluruh DAS", "Low, Medium, High pada primary baseline candidate", [das, admin, hz], transform_extent(das), "Frozen Stage 2 P175 area ≈13.249 km² (5.90% DAS): Low 4.702 km²; Medium 4.257 km²; High 4.290 km².")


def map_6_8():
    hz = load_raster(SRC["p175_class"], "P175 Hazard Class", SRC["qml_p175_class"])
    focus = load_vector(SRC["admin_focus"], "Pauh-Kuranji 18 kelurahan", SRC["qml_focus"])
    enable_labels(focus, 7.0)
    extent = transform_extent(focus, 0.06)
    return standard_single("6.8", "Fokus Pauh dan Kuranji", "P175 dan 18 kelurahan focus area", [focus, hz], extent, "Pauh dan Kuranji bersama mencakup sekitar 77.74% DAS. Focus area bersifat administratif; domain fisik model tetap seluruh DAS.")


def map_6_9():
    layout = new_layout("PETA_6_9", "A3L")
    add_label(layout, "Peta 6.9. Sensitivitas M175, M250, P175, dan P250", 10, 5, 400, 11, size=15, bold=True, align=Qt.AlignCenter)
    add_label(layout, "Perbandingan spasial empat skenario Stage 2", 10, 17, 400, 6, size=8, align=Qt.AlignCenter, color="#555555")
    das_extent = transform_extent(load_vector(SRC["das"], "DAS base 6.9"), 0.04)
    specs = [
        ("M175", SRC["m175_class"], 10, 30), ("M250", SRC["m250_class"], 212, 30),
        ("P175", SRC["p175_class"], 10, 151), ("P250", SRC["p250_class"], 212, 151),
    ]
    first_map = None
    for name, path, x, y in specs:
        hz = load_raster(path, name, SRC["qml_p175_class"])
        das = load_vector(SRC["das"], f"DAS {name}"); style_polygon(das, outline=(20,20,20,255), width=0.7)
        add_label(layout, name, x, y-7, 188, 6, size=9, bold=True, align=Qt.AlignCenter)
        m = add_map(layout, f"MAP_{name}", x, y, 188, 105, [das, hz], das_extent)
        if first_map is None: first_map = m
    add_legend(layout, first_map, 340, 257, 70, 31, "LEGENDA KELAS")
    add_label(layout, "M-domain menggunakan threshold manual yang jauh lebih luas; P-domain memakai WD > 0. Perbandingan ini adalah sensitivity analysis, bukan empat peta hazard final yang setara.", 10, 263, 320, 22, size=7)
    return layout


def map_7_1():
    obs = load_raster(SRC["observed"], "Observed BIG/BRIN 1 Dec 2025", SRC["qml_observed"])
    admin = load_vector(SRC["a3_admin_all"], "Administrasi", SRC["qml_a3_admin"])
    das = load_vector(SRC["das"], "DAS Kuranji", SRC["qml_das"])
    return standard_single("7.1", "Observed Flood Extent BIG/BRIN", "Post-event mapped flood extent 1 Desember 2025", [das, admin, obs], transform_extent(das), "Observed extent ≈4.176 km². Reference ini bukan peak-event inundation dan tidak boleh diperlakukan sebagai perfect flood truth.")


def map_7_2():
    obs = load_raster(SRC["observed"], "Observed BIG/BRIN", SRC["qml_observed"]); set_raster_opacity(obs, 0.80)
    p = load_raster(SRC["a3_p175_class"], "P175 Hazard Class", SRC["qml_a3_p175"]); set_raster_opacity(p, 0.62)
    das = load_vector(SRC["das"], "DAS Kuranji", SRC["qml_das"])
    return standard_single("7.2", "Observed vs P175", "Overlay post-event mapped extent dan primary baseline candidate", [das, obs, p], transform_extent(das), "Overlay ini menunjukkan correspondence dan mismatch. Model-only relatif terhadap 1 Desember bukan bukti definitive false alarm saat peak event.")


def map_7_3():
    conf = load_raster(SRC["p_confusion"], "P-domain Confusion", SRC["qml_pconf"])
    admin = load_vector(SRC["a3_admin_all"], "Administrasi", SRC["qml_a3_admin"])
    das = load_vector(SRC["das"], "DAS Kuranji", SRC["qml_das"])
    return standard_single("7.3", "P-domain Confusion Map", "TP, model-only relative to observed, observed-only/FN, TN", [das, admin, conf], transform_extent(das), "Strict r=0 P175: precision 0.1232, recall 0.3909, F1 0.1874, IoU 0.1034. Strict overlap tetap hasil validasi utama.")


def map_7_4():
    obs = load_raster(SRC["observed"], "Observed BIG/BRIN", SRC["qml_observed"]); set_raster_opacity(obs, 0.80)
    m175 = load_raster(SRC["a3_m175_class"], "M175 Hazard Class", SRC["qml_a3_m175"]); set_raster_opacity(m175, 0.60)
    das = load_vector(SRC["das"], "DAS Kuranji", SRC["qml_das"])
    return standard_single("7.4", "Observed vs M175", "Overlay observed dengan sensitivity scenario M175", [das, obs, m175], transform_extent(das), "M175 memiliki recall sangat tinggi tetapi overprediction besar. M175 disimpan sebagai sensitivity scenario, bukan primary baseline.")


def map_7_5():
    conf = load_raster(SRC["m_confusion"], "M-domain Confusion", SRC["qml_mconf"])
    admin = load_vector(SRC["a3_admin_all"], "Administrasi", SRC["qml_a3_admin"])
    das = load_vector(SRC["das"], "DAS Kuranji", SRC["qml_das"])
    return standard_single("7.5", "M-domain Confusion Map", "Overprediction sensitivity scenario M175", [das, admin, conf], transform_extent(das), "M-domain menangkap hampir seluruh observed extent tetapi prediksi ≈60.138 km², sekitar 14× observed mapped extent. Ini menjelaskan mengapa M175 tidak dipilih sebagai baseline utama.")


def map_7_6():
    conf = load_raster(SRC["p_confusion"], "P-domain Confusion", SRC["qml_pconf"])
    obs = load_raster(SRC["observed"], "Observed BIG/BRIN", SRC["qml_observed"]); set_raster_opacity(obs, 0.70)
    focus = load_vector(SRC["a3_admin_focus"], "Pauh-Kuranji focus", SRC["qml_a3_admin"])
    enable_labels(focus, 7.0)
    return standard_single("7.6", "Focus Pauh-Kuranji", "Validasi pada focus administratif utama", [focus, obs, conf], transform_extent(focus, 0.06), "Focus map memperlihatkan hit/miss dalam Pauh-Kuranji. Interpretasi tetap memakai strict validation dan tidak mengubah threshold P175.")


def map_7_7():
    conf = load_raster(SRC["p_confusion"], "P-domain Confusion", SRC["qml_pconf"])
    admin = load_vector(SRC["a3_admin_all"], "Kelurahan/desa", SRC["qml_a3_admin"])
    enable_labels(admin, 6.0)
    das = load_vector(SRC["das"], "DAS Kuranji", SRC["qml_das"])
    return standard_single("7.7", "Hotspot False Negative P175", "Observed-only terbesar pada validasi Stage 3", [das, admin, conf], transform_extent(das), "FN terbesar terkonsentrasi terutama di Nanggalo dan Kuranji. Hotspot adalah prioritas audit lokal, bukan dasar retuning otomatis terhadap event yang sama.")


def map_7_8():
    layout = new_layout("PETA_7_8", "A3L")
    add_label(layout, "Peta 7.8. Scenario Comparison P175 vs M175", 10, 5, 400, 11, size=15, bold=True, align=Qt.AlignCenter)
    add_label(layout, "Primary baseline candidate vs high-recall sensitivity scenario", 10, 17, 400, 6, size=8, align=Qt.AlignCenter, color="#555555")
    ext = transform_extent(load_vector(SRC["das"], "DAS extent 7.8"), 0.04)
    p = load_raster(SRC["a3_p175_class"], "P175", SRC["qml_a3_p175"])
    m = load_raster(SRC["a3_m175_class"], "M175", SRC["qml_a3_m175"])
    dp = load_vector(SRC["das"], "DAS P175"); style_polygon(dp, outline=(20,20,20,255), width=0.7)
    dm = load_vector(SRC["das"], "DAS M175"); style_polygon(dm, outline=(20,20,20,255), width=0.7)
    add_label(layout, "P175", 10, 28, 195, 7, size=10, bold=True, align=Qt.AlignCenter)
    mp = add_map(layout, "MAP_P175", 10, 36, 195, 205, [dp, p], ext)
    add_label(layout, "M175", 215, 28, 195, 7, size=10, bold=True, align=Qt.AlignCenter)
    mm = add_map(layout, "MAP_M175", 215, 36, 195, 205, [dm, m], ext)
    add_legend(layout, mp, 10, 247, 100, 37, "P175 LEGEND")
    add_legend(layout, mm, 215, 247, 100, 37, "M175 LEGEND")
    add_note_box(layout, "INTERPRETASI", "P175 lebih seimbang pada F1/IoU; M175 mempertahankan recall tinggi tetapi overprediction besar. Keduanya tidak dituning ulang pada event validasi.", 320, 247, 90, 37)
    return layout


def stage4_panel_layout(map_id, title, subtitle, paths, labels, note):
    layout = new_layout(f"PETA_{map_id.replace('.', '_')}", "A3L")
    add_label(layout, f"Peta {map_id}. {title}", 10, 5, 400, 11, size=15, bold=True, align=Qt.AlignCenter)
    add_label(layout, subtitle, 10, 17, 400, 6, size=8, align=Qt.AlignCenter, color="#555555")
    ext = transform_extent(load_vector(SRC["das"], f"DAS extent {map_id}"), 0.04)
    xs = [10, 145, 280]
    first = None
    for i, (path, label, x) in enumerate(zip(paths, labels, xs)):
        rr = load_raster(path, label); style_diverging(rr)
        obs = load_raster(SRC["observed20"], f"Observed overlay {map_id}-{i}"); style_binary(obs, QColor(30,220,255,190), "Observed BIG/BRIN", 1, 0.70)
        das = load_vector(SRC["das"], f"DAS {map_id}-{i}"); style_polygon(das, outline=(20,20,20,255), width=0.7)
        add_label(layout, label, x, 30, 125, 7, size=9, bold=True, align=Qt.AlignCenter)
        mm = add_map(layout, f"MAP_{i}", x, 38, 125, 190, [das, obs, rr], ext)
        if first is None: first = mm
    add_legend(layout, first, 10, 236, 120, 48, "LEGENDA PANEL 1")
    add_note_box(layout, "INTERPRETASI", note, 140, 236, 270, 48)
    return layout


def map_8_1():
    return stage4_panel_layout(
        "8.1", "Sentinel-1 EVENT minus PRE", "Median 3×3 backscatter change pada common 20 m grid",
        [SRC["s1_event_vv"], SRC["s1_event_vh"], SRC["s1_event_ratio"]],
        ["VV ΔdB", "VH ΔdB", "VH−VV ΔdB"],
        "Interpretasi dibatasi pada event-associated surface-state change. Acquisition 22 Nov adalah label internal EVENT/early-event-window dan mendahului documented Senyar formation 26 Nov. Bukan direct cyclone-effect map dan bukan elevation change."
    )


def map_8_2():
    return stage4_panel_layout(
        "8.2", "Sentinel-1 POST minus PRE", "Persistent surface-state change pada acquisition 4 Desember 2025",
        [SRC["s1_post_vv"], SRC["s1_post_vh"], SRC["s1_post_ratio"]],
        ["VV ΔdB", "VH ΔdB", "VH−VV ΔdB"],
        "Observed zones menunjukkan contrast backscatter yang lebih negatif dan signal tetap tampak pada POST. Potential mechanisms mencakup moisture, residual inundation, sediment, roughness, vegetation disturbance, dan kondisi permukaan lain."
    )


def map_8_3():
    layout = new_layout("PETA_8_3", "A3L")
    add_label(layout, "Peta 8.3. Integrasi Multimodal Stage 4", 10, 5, 400, 11, size=15, bold=True, align=Qt.AlignCenter)
    add_label(layout, "P175 + observed BIG/BRIN + TP/FN + drainage + Sentinel-1", 10, 17, 400, 6, size=8, align=Qt.AlignCenter, color="#555555")
    add_picture(layout, SRC["integration_png"], 10, 30, 300, 235)
    add_note_box(layout, "RINGKASAN", "Frozen integration figure. P175 tetap baseline candidate; BIG/BRIN adalah external observed extent; Sentinel-1 adalah surface-state evidence; ICESat-2 tidak menyediakan defensible delta-h.", 318, 30, 92, 105)
    add_note_box(layout, "BATAS KLAIM", "No true ΔDEM. No Δh. No pre/post GFI. No quantified pre/post flood-hazard-index change. Peta ini adalah multimodal evidence synthesis, bukan synthetic hazard score.", 318, 143, 92, 122)
    return layout


def load_icesat_points(path: Path, name: str, beams=("gt3l", "gt3r")):
    lyr = QgsVectorLayer("Point?crs=EPSG:32747&field=beam:string(10)&field=h:double", name, "memory")
    pr = lyr.dataProvider()
    feats = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        # Robust field lookup.
        def pick(cands):
            low = {x.lower(): x for x in fields}
            for c in cands:
                if c.lower() in low:
                    return low[c.lower()]
            return None
        fx = pick(["x_utm47s", "x", "easting"])
        fy = pick(["y_utm47s", "y", "northing"])
        fb = pick(["beam", "beam_name"])
        fh = pick(["h", "elevation", "elev"])
        if not fx or not fy or not fb:
            raise RuntimeError(f"ICESat CSV missing required columns: {path}; fields={fields}")
        from qgis.core import QgsGeometry, QgsPointXY
        for row in reader:
            if row.get(fb) not in beams:
                continue
            try:
                x = float(row[fx]); y = float(row[fy])
            except Exception:
                continue
            ft = QgsFeature(lyr.fields())
            ft.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            ft["beam"] = row.get(fb, "")
            if fh and row.get(fh):
                try: ft["h"] = float(row[fh])
                except Exception: pass
            feats.append(ft)
    pr.addFeatures(feats)
    lyr.updateExtents()
    add_to_project(lyr)
    return lyr


def map_8_4():
    pre = load_icesat_points(SRC["icesat_pre_csv"], "ICESat-2 PRE 14 Oct 2025")
    post = load_icesat_points(SRC["icesat_post_csv"], "ICESat-2 POST 13 Jan 2026")
    style_point(pre, (30,105,210,240), 2.1, "circle")
    style_point(post, (220,55,50,240), 2.3, "triangle")
    das = load_vector(SRC["das"], "DAS Kuranji"); style_polygon(das, outline=(20,20,20,255), width=0.9)
    ext = union_extent([pre, post, das], 0.06)
    with SRC["icesat_geom"].open(encoding="utf-8") as f:
        geom = json.load(f)
    g3l = geom.get("gt3l", {}).get("same_y_separation_m", {})
    g3r = geom.get("gt3r", {}).get("same_y_separation_m", {})
    note = (
        f"RGT0453 consecutive cycles gagal positional comparability. gt3l median separation ≈{g3l.get('median', 12628.6):.1f} m; "
        f"gt3r ≈{g3r.get('median', 12655.6):.1f} m. Within 100 m = 0%. NO Δh CALCULATED."
    )
    return standard_single("8.4", "ICESat-2 Repeat-Track Comparability", "PRE 14 Oct 2025 vs POST 13 Jan 2026 · beams gt3l/gt3r", [das, post, pre], ext, note)


BUILDERS = {
    "5.1": (map_5_1, "LOKASI_DAS_KURANJI", "05_STAGE1"),
    "5.2": (map_5_2, "DEM_TOPOGRAFI", "05_STAGE1"),
    "5.3": (map_5_3, "FLOW_ACCUMULATION", "05_STAGE1"),
    "5.4": (map_5_4, "STREAM_6KM2_VS_RBI", "05_STAGE1"),
    "5.5": (map_5_5, "WATERSHED_VS_REFERENCE", "05_STAGE1"),
    "5.6": (map_5_6, "RESIDUAL_MISMATCH", "05_STAGE1"),

    "6.1": (map_6_1, "DAS_ADMINISTRASI", "06_STAGE2"),
    "6.2": (map_6_2, "RBI_VS_BASELINE_DRAINAGE", "06_STAGE2"),
    "6.3": (map_6_3, "GFI_RAW", "06_STAGE2"),
    "6.4": (map_6_4, "GFI_NORMALIZED", "06_STAGE2"),
    "6.5": (map_6_5, "WATER_DEPTH_P175", "06_STAGE2"),
    "6.6": (map_6_6, "HAZARD_INDEX_P175", "06_STAGE2"),
    "6.7": (map_6_7, "HAZARD_CLASS_P175", "06_STAGE2"),
    "6.8": (map_6_8, "FOCUS_PAUH_KURANJI", "06_STAGE2"),
    "6.9": (map_6_9, "SENSITIVITY_M175_M250_P175_P250", "06_STAGE2"),

    "7.1": (map_7_1, "OBSERVED_BIG_BRIN", "07_STAGE3"),
    "7.2": (map_7_2, "OBSERVED_VS_P175", "07_STAGE3"),
    "7.3": (map_7_3, "P_DOMAIN_CONFUSION", "07_STAGE3"),
    "7.4": (map_7_4, "OBSERVED_VS_M175", "07_STAGE3"),
    "7.5": (map_7_5, "M_DOMAIN_CONFUSION", "07_STAGE3"),
    "7.6": (map_7_6, "FOCUS_PAUH_KURANJI_VALIDATION", "07_STAGE3"),
    "7.7": (map_7_7, "FN_HOTSPOTS_P175", "07_STAGE3"),
    "7.8": (map_7_8, "P175_VS_M175", "07_STAGE3"),

    "8.1": (map_8_1, "SENTINEL1_EVENT_MINUS_PRE", "08_STAGE4"),
    "8.2": (map_8_2, "SENTINEL1_POST_MINUS_PRE", "08_STAGE4"),
    "8.3": (map_8_3, "MULTIMODAL_INTEGRATION", "08_STAGE4"),
    "8.4": (map_8_4, "ICESAT2_COMPARABILITY", "08_STAGE4"),
}


# -----------------------------------------------------------------------------
# BUILD / EXPORT
# -----------------------------------------------------------------------------
errors = []
for map_id in BUILDERS:
    if not wanted(map_id):
        continue
    builder, slug, stage_dir = BUILDERS[map_id]
    print("=" * 88)
    print(f"BUILD MAP {map_id}: {slug}")
    try:
        layout = builder()
        if not export_layout(layout, map_id, slug, stage_dir, args.dpi):
            errors.append((map_id, "export status review"))
    except Exception as exc:
        errors.append((map_id, repr(exc)))
        print(f"[ERROR] {map_id}: {exc}")
        traceback.print_exc()


# -----------------------------------------------------------------------------
# MANIFEST / PROJECT / ZIP
# -----------------------------------------------------------------------------
manifest_path = OUT / "MAP_MANIFEST.csv"
with manifest_path.open("w", newline="", encoding="utf-8") as f:
    fields = ["map_id", "slug", "png", "pdf", "qpt", "png_status", "pdf_status", "qpt_status", "status"]
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(manifest_rows)

project_path = OUT / "KURANJI_FINAL_27_MAPS.qgz"
project.write(str(project_path))

summary = {
    "qgis_version": Qgis.QGIS_VERSION,
    "requested_maps": sorted(SELECTED) if SELECTED else list(BUILDERS.keys()),
    "exported_rows": len(manifest_rows),
    "errors": errors,
    "scientific_guardrails": [
        "no Stage 1-4 analytical recalculation",
        "no delta-h",
        "no delta-DEM",
        "no pre/post GFI",
        "no quantified pre/post hazard-index change",
        "Sentinel-1 visualised as surface-state/backscatter change evidence",
    ],
}
(OUT / "RUN_SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

# Create final ZIP only for a full 27-map run. Subset runs retain their files without replacing a prior full ZIP.
if not SELECTED:
    zip_path = ROOT / "artifacts/KURANJI_FINAL_27_MAPS.zip"
    if zip_path.exists():
        zip_path.unlink()
    with ZipFile(zip_path, "w", ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(OUT.rglob("*")):
            if p.is_file():
                z.write(p, f"KURANJI_FINAL_27_MAPS/{p.relative_to(OUT).as_posix()}")
    print(f"ZIP={zip_path}")

print("=" * 88)
print("KURANJI_27_MAPS_RUN_COMPLETE")
print(f"MANIFEST={manifest_path}")
print(f"PROJECT={project_path}")
print(f"EXPORTED={len(manifest_rows)}")
print(f"ERRORS={len(errors)}")
if errors:
    for map_id, err in errors:
        print(f"ERROR_MAP={map_id}\t{err}")
    print("FINAL_STATUS=REVIEW_REQUIRED")
else:
    expected = len(SELECTED) if SELECTED else 27
    if len(manifest_rows) == expected:
        print("FINAL_STATUS=COMPLETE")
    else:
        print("FINAL_STATUS=REVIEW_REQUIRED")

qgs.exitQgis()
