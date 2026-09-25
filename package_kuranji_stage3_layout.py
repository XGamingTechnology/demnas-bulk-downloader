#!/usr/bin/env python3
"""Build the final QGIS-ready Stage-3 validation package for DAS Batang Kuranji.

Run after Stage-3 validation and positional-tolerance QC are complete:

    python package_kuranji_stage3_layout.py

Output:
    artifacts/KURANJI_TAHAP3_SPATIAL_LAYOUT.zip

The package contains the independent BIG/BRIN observed flood extent, model
validation rasters/tables, Stage-2 comparison rasters, administration/reference
vectors, QC, documentation, and reusable QGIS QML styles. No analysis is
recomputed by this script.
"""

from __future__ import annotations

import csv
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts"
PKG = ART / "KURANJI_TAHAP3_SPATIAL_LAYOUT"
ZIP = ART / "KURANJI_TAHAP3_SPATIAL_LAYOUT.zip"


def copy_required(src: Path, dst: Path):
    if not src.exists():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_optional(src: Path, dst: Path):
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def qml_observed():
    return '''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology|Legend">
  <pipe>
    <rasterrenderer type="paletted" band="1" opacity="0.72">
      <colorPalette>
        <paletteEntry value="1" label="Observed flood extent (BIG/BRIN, 1 Dec 2025)" color="#2166ac" alpha="190"/>
      </colorPalette>
    </rasterrenderer>
  </pipe>
</qgis>
'''


def qml_hazard_class():
    return '''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology|Legend">
  <pipe>
    <rasterrenderer type="paletted" band="1" opacity="0.70">
      <colorPalette>
        <paletteEntry value="1" label="Rendah" color="#fff7bc" alpha="210"/>
        <paletteEntry value="2" label="Sedang" color="#fec44f" alpha="220"/>
        <paletteEntry value="3" label="Tinggi" color="#d7301f" alpha="225"/>
      </colorPalette>
    </rasterrenderer>
  </pipe>
</qgis>
'''


def qml_confusion():
    return '''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology|Legend">
  <pipe>
    <rasterrenderer type="paletted" band="1" opacity="0.82">
      <colorPalette>
        <paletteEntry value="1" label="TN - neither model nor observed" color="#f2f2f2" alpha="110"/>
        <paletteEntry value="2" label="TP - model and observed" color="#1a9850" alpha="230"/>
        <paletteEntry value="3" label="Model-only (FP relative to 1 Dec reference)" color="#fdae61" alpha="220"/>
        <paletteEntry value="4" label="Observed-only (FN)" color="#d73027" alpha="230"/>
      </colorPalette>
    </rasterrenderer>
  </pipe>
</qgis>
'''


def qml_admin():
    return '''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology">
  <renderer-v2 type="singleSymbol">
    <symbols>
      <symbol type="fill" name="0">
        <layer class="SimpleFill">
          <Option type="Map">
            <Option name="color" value="255,255,255,0" type="QString"/>
            <Option name="outline_color" value="70,70,70,255" type="QString"/>
            <Option name="outline_width" value="0.35" type="QString"/>
          </Option>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>
'''


def qml_das():
    return '''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology">
  <renderer-v2 type="singleSymbol">
    <symbols>
      <symbol type="fill" name="0">
        <layer class="SimpleFill">
          <Option type="Map">
            <Option name="color" value="255,255,255,0" type="QString"/>
            <Option name="outline_color" value="0,0,0,255" type="QString"/>
            <Option name="outline_width" value="0.8" type="QString"/>
          </Option>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>
'''


def main():
    if PKG.exists():
        shutil.rmtree(PKG)
    PKG.mkdir(parents=True, exist_ok=True)
    ART.mkdir(parents=True, exist_ok=True)

    stage3 = ROOT / "data/work/kuranji/15_stage3_validation"
    source = stage3 / "source_big"
    results = stage3 / "results_big_layer3"
    tol = stage3 / "positional_tolerance"
    stage2 = ROOT / "data/work/kuranji/12_fuzzy_hazard_sensitivity/rasters"
    admin = ROOT / "data/work/kuranji/14_stage2_admin_final/vector"
    prep = ROOT / "data/work/kuranji/01_prepared"

    # Reference layers.
    copy_required(prep / "DAS_KURANJI_UTM47S.geojson", PKG / "01_REFERENCE/DAS_KURANJI_UTM47S.geojson")
    copy_optional(prep / "SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson", PKG / "01_REFERENCE/SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson")
    copy_required(admin / "ADMIN_ALL_INTERSECTING_UTM47S.geojson", PKG / "01_REFERENCE/ADMIN_ALL_INTERSECTING_UTM47S.geojson")
    copy_required(admin / "ADMIN_FOCUS_PAUH_KURANJI_18_UTM47S.geojson", PKG / "01_REFERENCE/ADMIN_FOCUS_PAUH_KURANJI_18_UTM47S.geojson")

    # Observed source, preserving original and clipped forms plus metadata.
    for name in [
        "layer3_raw_bbox.geojson",
        "layer3_kuranji_clip_utm47s.geojson",
        "layer3_kuranji_aligned.tif",
        "service_metadata.json",
        "layer3_metadata.json",
        "source_attributes_layer3.csv",
        "source_preflight_qc.json",
    ]:
        copy_required(source / name, PKG / "02_OBSERVED_BIG_BRIN" / name)

    # Explicitly keep the validator's frozen observed raster.
    copy_required(
        results / "raster/OBSERVED_BIG_BRIN_20251201.tif",
        PKG / "02_OBSERVED_BIG_BRIN/OBSERVED_BIG_BRIN_20251201.tif",
    )

    # Stage-2 scenarios used for external validation.
    for sc in ["P175", "P250", "M175", "M250"]:
        copy_required(stage2 / f"{sc}_HAZARD_CLASS.tif", PKG / "03_MODEL_SCENARIOS" / f"{sc}_HAZARD_CLASS.tif")
        copy_optional(stage2 / f"{sc}_HAZARD_INDEX.tif", PKG / "03_MODEL_SCENARIOS" / f"{sc}_HAZARD_INDEX.tif")
        copy_optional(stage2 / f"{sc}_WD_INPUT.tif", PKG / "03_MODEL_SCENARIOS" / f"{sc}_WD_INPUT.tif")

    # Confusion rasters.
    for name in ["P_DOMAIN_CONFUSION.tif", "M_DOMAIN_CONFUSION.tif"]:
        copy_required(results / "raster" / name, PKG / "04_VALIDATION_RASTER" / name)

    # Validation tables.
    for p in (results / "table").glob("*.csv"):
        copy_required(p, PKG / "05_VALIDATION_TABLE" / p.name)

    # Positional tolerance QC.
    copy_required(tol / "positional_tolerance_metrics.csv", PKG / "06_POSITIONAL_TOLERANCE/positional_tolerance_metrics.csv")
    copy_required(tol / "positional_tolerance_qc.json", PKG / "06_POSITIONAL_TOLERANCE/positional_tolerance_qc.json")

    # Main validation QC/readme.
    copy_required(results / "qc/stage3_validation_qc.json", PKG / "07_QC/stage3_validation_qc.json")
    copy_required(results / "README_STAGE3_VALIDATION_RESULTS.md", PKG / "07_QC/README_STAGE3_VALIDATION_RESULTS.md")

    # Method and freeze decision documents.
    docs = [
        "docs/KURANJI_TAHAP3_RENCANA_VALIDASI_2025.md",
        "docs/KURANJI_TAHAP3_INTERPRETASI_VALIDASI_BIG_BRIN.md",
        "docs/KURANJI_TAHAP3_KEPUTUSAN_FREEZE_VALIDASI.md",
        "docs/KURANJI_LAPORAN_TAHAP_2_GFI_BAHAYA_BASELINE.md",
    ]
    for rel in docs:
        src = ROOT / rel
        if src.exists():
            copy_required(src, PKG / "08_DOCS" / src.name)

    # QGIS styles.
    styles = PKG / "09_QGIS_STYLE"
    styles.mkdir(parents=True, exist_ok=True)
    (styles / "OBSERVED_BIG_BRIN.qml").write_text(qml_observed(), encoding="utf-8")
    (styles / "P175_HAZARD_CLASS.qml").write_text(qml_hazard_class(), encoding="utf-8")
    (styles / "M175_HAZARD_CLASS.qml").write_text(qml_hazard_class(), encoding="utf-8")
    (styles / "P_DOMAIN_CONFUSION.qml").write_text(qml_confusion(), encoding="utf-8")
    (styles / "M_DOMAIN_CONFUSION.qml").write_text(qml_confusion(), encoding="utf-8")
    (styles / "ADMIN_BOUNDARY.qml").write_text(qml_admin(), encoding="utf-8")
    (styles / "DAS_BOUNDARY.qml").write_text(qml_das(), encoding="utf-8")

    checklist = [
        ["01", "Observed flood extent BIG/BRIN", "Observed 1 Dec 2025 + DAS + admin"],
        ["02", "Observed vs P175", "OBSERVED + P175_HAZARD_CLASS"],
        ["03", "P-domain confusion", "P_DOMAIN_CONFUSION + admin"],
        ["04", "Observed vs M175", "OBSERVED + M175_HAZARD_CLASS"],
        ["05", "M-domain confusion", "M_DOMAIN_CONFUSION + admin"],
        ["06", "Focus Pauh-Kuranji validation", "Observed + P-domain confusion + focus admin"],
        ["07", "FN hotspots", "P_DOMAIN_CONFUSION + kelurahan labels"],
        ["08", "Scenario comparison", "P175/M175 side-by-side"],
    ]
    with (PKG / "MAP_CHECKLIST.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["No", "Layout", "Layer utama"])
        w.writerows(checklist)

    layer_order_text = (
        "Recommended QGIS layer order (top -> bottom)\n"
        "1. Labels / annotations\n"
        "2. Administrative boundaries\n"
        "3. DAS boundary\n"
        "4. Observed BIG/BRIN flood extent (when used as overlay)\n"
        "5. Model hazard class or confusion raster\n"
        "6. Optional basemap/hillshade\n\n"
        "CRS utama: EPSG:32747 (WGS84 / UTM Zone 47S).\n"
        "Observed reference date: 1 Dec 2025.\n"
        "P175 status: primary baseline hazard candidate, externally evaluated, NOT final calibrated hazard.\n"
    )
    (PKG / "LAYER_ORDER.txt").write_text(layer_order_text, encoding="utf-8")

    readme = (
        "# Paket Spatial Layouting Tahap 3 - DAS Batang Kuranji\n\n"
        "Observed reference: BIG/BRIN WorldView interpretation, 1 Dec 2025.\n"
        "CRS utama: EPSG:32747.\n\n"
        "P175 tetap berstatus primary baseline hazard candidate, externally evaluated.\n"
        "Strict r=0 adalah validasi utama; tolerance 1-5 pixel hanya sensitivity diagnostic.\n\n"
        "Folder:\n"
        "- 01_REFERENCE: DAS, RBI, administrasi\n"
        "- 02_OBSERVED_BIG_BRIN: observed source dan metadata\n"
        "- 03_MODEL_SCENARIOS: P175/P250/M175/M250\n"
        "- 04_VALIDATION_RASTER: confusion rasters\n"
        "- 05_VALIDATION_TABLE: metrik DAS/kecamatan/kelurahan\n"
        "- 06_POSITIONAL_TOLERANCE: QC offset spasial\n"
        "- 07_QC: validation QC\n"
        "- 08_DOCS: metode dan keputusan freeze\n"
        "- 09_QGIS_STYLE: style QML\n"
    )
    (PKG / "README_LAYOUTING_TAHAP3.md").write_text(readme, encoding="utf-8")

    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(PKG.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(PKG.parent))

    print("=== KURANJI STAGE 3 SPATIAL LAYOUT PACKAGE ===")
    print("Folder:", PKG)
    print("ZIP   :", ZIP)
    print(f"Size  : {ZIP.stat().st_size/1024/1024:.1f} MB")
    print("Ready for download/copy from the VPS.")


if __name__ == "__main__":
    main()
