#!/usr/bin/env python3
"""Build a QGIS-ready Stage-2 spatial layout package for DAS Kuranji.

Run on the VPS after Stage-2 has been finalized:

    python package_kuranji_stage2_layout.py

Output:
    artifacts/KURANJI_TAHAP2_SPATIAL_LAYOUT.zip

The package is intentionally focused on cartographic/layout products. It includes
actual final rasters, GFI rasters, administrative vectors, tables, QC, module/report
notes, and reusable QGIS QML styles. It does not recompute analysis.
"""

from __future__ import annotations

import csv
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts"
PKG = ART / "KURANJI_TAHAP2_SPATIAL_LAYOUT"
ZIP = ART / "KURANJI_TAHAP2_SPATIAL_LAYOUT.zip"


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


def qml_hazard_class():
    return '''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology|Legend">
  <pipe>
    <rasterrenderer type="paletted" band="1" opacity="1">
      <colorPalette>
        <paletteEntry value="1" label="Rendah" color="#fff7bc" alpha="255"/>
        <paletteEntry value="2" label="Sedang" color="#fec44f" alpha="255"/>
        <paletteEntry value="3" label="Tinggi" color="#d7301f" alpha="255"/>
      </colorPalette>
    </rasterrenderer>
  </pipe>
</qgis>
'''


def qml_admin_boundary():
    return '''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology|Labeling">
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


def qml_focus_boundary():
    return '''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology|Labeling">
  <renderer-v2 type="singleSymbol">
    <symbols>
      <symbol type="fill" name="0">
        <layer class="SimpleFill">
          <Option type="Map">
            <Option name="color" value="255,255,255,0" type="QString"/>
            <Option name="outline_color" value="0,0,0,255" type="QString"/>
            <Option name="outline_width" value="0.6" type="QString"/>
          </Option>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>
'''


def qml_continuous(name, minv, maxv):
    return f'''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34" styleCategories="Symbology|Legend">
  <pipe>
    <rasterrenderer type="singlebandpseudocolor" band="1" opacity="1" classificationMin="{minv}" classificationMax="{maxv}">
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" minimumValue="{minv}" maximumValue="{maxv}" labelPrecision="3">
          <colorramp type="gradient" name="{name}">
            <Option type="Map">
              <Option name="color1" value="49,54,149,255" type="QString"/>
              <Option name="color2" value="165,0,38,255" type="QString"/>
            </Option>
          </colorramp>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
  </pipe>
</qgis>
'''


def main():
    if PKG.exists():
        shutil.rmtree(PKG)
    PKG.mkdir(parents=True)
    ART.mkdir(parents=True, exist_ok=True)

    final = ROOT / "data/work/kuranji/14_stage2_admin_final"
    gfi = ROOT / "data/work/kuranji/08_gfi_baseline"
    prep = ROOT / "data/work/kuranji/01_prepared"
    sens = ROOT / "data/work/kuranji/12_fuzzy_hazard_sensitivity"

    # Reference vectors.
    copy_required(prep / "DAS_KURANJI_UTM47S.geojson", PKG / "01_REFERENCE/DAS_KURANJI_UTM47S.geojson")
    copy_optional(prep / "SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson", PKG / "01_REFERENCE/SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson")

    # Core GFI rasters needed for report maps.
    copy_required(gfi / "06_GFI_RAW.tif", PKG / "02_GFI/06_GFI_RAW.tif")
    copy_required(gfi / "07_GFI_NORMALIZED.tif", PKG / "02_GFI/07_GFI_NORMALIZED.tif")
    copy_required(gfi / "05_HR_M.tif", PKG / "02_GFI/05_HR_M.tif")
    copy_required(gfi / "02_H_CONNECTED_DRAINAGE_M.tif", PKG / "02_GFI/02_H_CONNECTED_DRAINAGE_M.tif")

    # Final P175 products.
    for name in ["P175_WD_INPUT.tif", "P175_HAZARD_INDEX.tif", "P175_HAZARD_CLASS.tif"]:
        copy_required(final / "raster" / name, PKG / "03_P175" / name)

    # Sensitivity class rasters are useful for the 4-panel comparison map.
    for sc in ["M175", "M250", "P175", "P250"]:
        copy_optional(sens / "rasters" / f"{sc}_HAZARD_CLASS.tif", PKG / "04_SENSITIVITY" / f"{sc}_HAZARD_CLASS.tif")
        copy_optional(sens / "rasters" / f"{sc}_HAZARD_INDEX.tif", PKG / "04_SENSITIVITY" / f"{sc}_HAZARD_INDEX.tif")

    # Final vector and tables.
    for p in (final / "vector").glob("*"):
        if p.is_file():
            copy_required(p, PKG / "05_ADMIN_VECTOR" / p.name)
    for p in (final / "table").glob("*.csv"):
        copy_required(p, PKG / "06_TABLE" / p.name)
    for p in (final / "qc").glob("*.json"):
        copy_required(p, PKG / "07_QC" / p.name)

    # Reports/method notes.
    docs = [
        "docs/KURANJI_LAPORAN_TAHAP_2_GFI_BAHAYA_BASELINE.md",
        "docs/KURANJI_TAHAP2_KEPUTUSAN_BASELINE_HAZARD_CANDIDATE.md",
        "docs/KURANJI_TAHAP2_QC_FUZZY_PARAMETER.md",
        "docs/KURANJI_TAHAP2_QC_THRESHOLD_WD.md",
        "docs/KURANJI_TAHAP2_KEPUTUSAN_DRAINAGE_NETWORK.md",
    ]
    for rel in docs:
        src = ROOT / rel
        if src.exists():
            copy_required(src, PKG / "08_DOCS" / src.name)

    # QGIS styles.
    styles = PKG / "09_QGIS_STYLE"
    styles.mkdir(parents=True, exist_ok=True)
    (styles / "P175_HAZARD_CLASS.qml").write_text(qml_hazard_class(), encoding="utf-8")
    (styles / "ADMIN_BOUNDARY.qml").write_text(qml_admin_boundary(), encoding="utf-8")
    (styles / "FOCUS_BOUNDARY.qml").write_text(qml_focus_boundary(), encoding="utf-8")
    (styles / "GFI_RAW.qml").write_text(qml_continuous("GFI_RAW", -6.638383, 13.411668), encoding="utf-8")
    (styles / "GFI_NORMALIZED.qml").write_text(qml_continuous("GFI_NORMALIZED", -1, 1), encoding="utf-8")
    (styles / "P175_HAZARD_INDEX.qml").write_text(qml_continuous("HAZARD_INDEX", 0, 1), encoding="utf-8")
    (styles / "P175_WD.qml").write_text(qml_continuous("WATER_DEPTH", 0, 6.677484), encoding="utf-8")

    # Layer order and map checklist.
    (PKG / "LAYER_ORDER.txt").write_text(
        """Recommended QGIS layer order (top -> bottom)\n"
        "1. Labels / annotations\n"
        "2. ADMIN_FOCUS_PAUH_KURANJI_18_UTM47S\n"
        "3. ADMIN_ALL_INTERSECTING_UTM47S\n"
        "4. DAS_KURANJI_UTM47S boundary\n"
        "5. SUNGAI_RBI_DAS_KURANJI_UTM47S\n"
        "6. Thematic raster for the map being produced\n"
        "7. Hillshade/DEM basemap if desired\n"
        "\nAll analysis products use EPSG:32747 (WGS84 / UTM Zone 47S).\n"
        """,
        encoding="utf-8",
    )

    checklist = [
        ["01", "Lokasi DAS dan administrasi", "DAS + ADMIN_ALL_INTERSECTING"],
        ["02", "Jaringan sungai", "RBI + DAS"],
        ["03", "GFI raw", "06_GFI_RAW.tif"],
        ["04", "GFI normalized", "07_GFI_NORMALIZED.tif"],
        ["05", "Domain/WD P175", "P175_WD_INPUT.tif"],
        ["06", "Indeks bahaya P175", "P175_HAZARD_INDEX.tif"],
        ["07", "Kelas bahaya P175 seluruh DAS", "P175_HAZARD_CLASS.tif + all admin"],
        ["08", "Fokus Pauh-Kuranji", "P175 class + focus 18 admin"],
        ["09", "Sensitivitas 4 skenario", "M175/M250/P175/P250 class"],
    ]
    with (PKG / "MAP_CHECKLIST.csv").open("w", encoding="utf-8", newline="") as f:
        w=csv.writer(f); w.writerow(["No","Layout","Layer utama"]); w.writerows(checklist)

    readme = """# Paket Spatial Layouting Tahap 2 - DAS Batang Kuranji\n\n"
    readme += "CRS utama: EPSG:32747 (WGS84 / UTM Zone 47S).\n\n"
    readme += "Status P175: primary baseline hazard candidate, belum final calibrated flood hazard map.\n\n"
    readme += "Folder:\n"
    readme += "- 01_REFERENCE: DAS dan RBI\n- 02_GFI: GFI, H, hr\n- 03_P175: WD, hazard index, hazard class\n"
    readme += "- 04_SENSITIVITY: M175/M250/P175/P250\n- 05_ADMIN_VECTOR: administrasi whole-DAS dan focus\n"
    readme += "- 06_TABLE: statistik area\n- 07_QC: quality control\n- 08_DOCS: metode/keputusan\n- 09_QGIS_STYLE: style QML\n\n"
    readme += "Untuk layout laporan, gunakan MAP_CHECKLIST.csv dan LAYER_ORDER.txt.\n"
    readme += "Jangan memberi label P175 sebagai peta bahaya final sebelum validasi eksternal Tahap 3.\n"
    (PKG / "README_LAYOUTING_TAHAP2.md").write_text(readme, encoding="utf-8")

    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(PKG.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(PKG.parent))

    print("=== KURANJI STAGE 2 SPATIAL LAYOUT PACKAGE ===")
    print("Folder:", PKG)
    print("ZIP   :", ZIP)
    print(f"Size  : {ZIP.stat().st_size/1024/1024:.1f} MB")
    print("Ready for download/copy from the VPS.")


if __name__ == "__main__":
    main()
