#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render Kuranji report Maps 5.2–8.4 with GDAL/OGR + Matplotlib.

Cartographic renderer only. It reads frozen Stage 1–4 outputs and does not
recalculate hydrology, GFI, hazard, validation metrics, Sentinel-1 change, or
ICESat-2 elevation change.

Map 5.1 is intentionally handled by the dedicated V4 locator renderer because
its locator-map design has been iterated separately with the user.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import ListedColormap, BoundaryNorm, LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Polygon as MplPolygon
from osgeo import gdal, ogr, osr

gdal.UseExceptions()
gdal.SetConfigOption("OGR_GEOMETRY_ACCEPT_UNCLOSED_RING", "YES")

parser = argparse.ArgumentParser()
parser.add_argument("--root", default="/opt/demnas-bulk-downloader")
parser.add_argument("--dpi", type=int, default=220)
parser.add_argument("--lang", default="id,en")
parser.add_argument("--only", default="", help="Comma-separated map IDs, e.g. 5.2,6.7")
args = parser.parse_args()

ROOT = Path(args.root).resolve()
K = ROOT / "data/work/kuranji"
A2 = ROOT / "artifacts/KURANJI_TAHAP2_SPATIAL_LAYOUT"
A3 = ROOT / "artifacts/KURANJI_TAHAP3_SPATIAL_LAYOUT"
A4 = ROOT / "artifacts/KURANJI_TAHAP4_SPATIAL_LAYOUT"
S1V = K / "05_validation/conditioning_sensitivity"
OUT = ROOT / "artifacts/KURANJI_FINAL_ALL27_BILINGUAL"

SRC = {
    "das": K / "01_prepared/DAS_KURANJI_UTM47S.geojson",
    "rbi": K / "01_prepared/SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson",
    "sumbar": ROOT / "data shp/data_administrasi/Sumatera_Barat.shp",
    "kecamatan_raw": ROOT / "data shp/data_administrasi/Kecamatan.shp",
    "admin_all": A2 / "05_ADMIN_VECTOR/ADMIN_ALL_INTERSECTING_UTM47S.geojson",
    "admin_focus": A2 / "05_ADMIN_VECTOR/ADMIN_FOCUS_PAUH_KURANJI_18_UTM47S.geojson",
    "dem_breach100": S1V / "BREACH100_DEM.tif",
    "flowacc_breach100": S1V / "BREACH100_FLOW_ACCUM_CELLS.tif",
    "stream6": K / "03_watershed/STREAM_FINAL_6KM2.tif",
    "pour_point": S1V / "BREACH100_POUR_POINT.tif",
    "watershed": S1V / "BREACH100_WATERSHED.tif",
    "ref_only": S1V / "BREACH100_REF_ONLY.tif",
    "model_only": S1V / "BREACH100_MODEL_ONLY.tif",
    "residual_components": S1V / "BREACH_RESIDUAL_COMPONENTS.geojson",
    "gfi_raw": A2 / "02_GFI/06_GFI_RAW.tif",
    "gfi_norm": A2 / "02_GFI/07_GFI_NORMALIZED.tif",
    "p175_wd": A2 / "03_P175/P175_WD_INPUT.tif",
    "p175_index": A2 / "03_P175/P175_HAZARD_INDEX.tif",
    "p175_class": A2 / "03_P175/P175_HAZARD_CLASS.tif",
    "m175_class": A2 / "04_SENSITIVITY/M175_HAZARD_CLASS.tif",
    "m250_class": A2 / "04_SENSITIVITY/M250_HAZARD_CLASS.tif",
    "p250_class": A2 / "04_SENSITIVITY/P250_HAZARD_CLASS.tif",
    "qml_gfi_raw": A2 / "09_QGIS_STYLE/GFI_RAW.qml",
    "qml_gfi_norm": A2 / "09_QGIS_STYLE/GFI_NORMALIZED.qml",
    "qml_p175_wd": A2 / "09_QGIS_STYLE/P175_WD.qml",
    "qml_p175_index": A2 / "09_QGIS_STYLE/P175_HAZARD_INDEX.qml",
    "qml_p175_class": A2 / "09_QGIS_STYLE/P175_HAZARD_CLASS.qml",
    "observed": A3 / "02_OBSERVED_BIG_BRIN/OBSERVED_BIG_BRIN_20251201.tif",
    "observed_vector": A3 / "02_OBSERVED_BIG_BRIN/layer3_kuranji_clip_utm47s.geojson",
    "p_confusion": A3 / "04_VALIDATION_RASTER/P_DOMAIN_CONFUSION.tif",
    "m_confusion": A3 / "04_VALIDATION_RASTER/M_DOMAIN_CONFUSION.tif",
    "a3_p175_class": A3 / "03_MODEL_SCENARIOS/P175_HAZARD_CLASS.tif",
    "a3_m175_class": A3 / "03_MODEL_SCENARIOS/M175_HAZARD_CLASS.tif",
    "a3_admin_all": A3 / "01_REFERENCE/ADMIN_ALL_INTERSECTING_UTM47S.geojson",
    "a3_admin_focus": A3 / "01_REFERENCE/ADMIN_FOCUS_PAUH_KURANJI_18_UTM47S.geojson",
    "qml_observed": A3 / "09_QGIS_STYLE/OBSERVED_BIG_BRIN.qml",
    "qml_pconf": A3 / "09_QGIS_STYLE/P_DOMAIN_CONFUSION.qml",
    "qml_mconf": A3 / "09_QGIS_STYLE/M_DOMAIN_CONFUSION.qml",
    "qml_a3_p175": A3 / "09_QGIS_STYLE/P175_HAZARD_CLASS.qml",
    "qml_a3_m175": A3 / "09_QGIS_STYLE/M175_HAZARD_CLASS.qml",
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

# -----------------------------------------------------------------------------
# Map copy: derived from the frozen map plan and results already established.
# -----------------------------------------------------------------------------
MAPS = {
"5.2": dict(stage="05_STAGE1", slug="DEM_TOPOGRAFI", kind="single", title_id="DEM dan Topografi", title_en="DEM and Topography", sub_id="Baseline terrain BREACH100", sub_en="BREACH100 baseline terrain", note_id="BREACH100 dipilih sebagai conditioning baseline Stage 1. Peta menggambarkan topografi baseline, bukan terrain pascakejadian.", note_en="BREACH100 is the selected Stage 1 conditioning baseline. This map shows baseline topography, not post-event terrain.", layers=[("continuous","dem_breach100","dem"),("line","rbi","river"),("boundary","das","das")]),
"5.3": dict(stage="05_STAGE1", slug="FLOW_ACCUMULATION", kind="single", title_id="Flow Accumulation", title_en="Flow Accumulation", sub_id="BREACH100 D8 flow accumulation", sub_en="BREACH100 D8 flow accumulation", note_id="Flow accumulation adalah produk routing Stage 1. Visualisasi ini tidak mengubah threshold drainase frozen 6 km².", note_en="Flow accumulation is a Stage 1 routing product. The visualisation does not alter the frozen 6 km² drainage threshold.", layers=[("continuous","flowacc_breach100","flowacc"),("line","rbi","river"),("binary","pour_point","pour"),("boundary","das","das")]),
"5.4": dict(stage="05_STAGE1", slug="STREAM_6KM2_VS_RBI", kind="single", title_id="Jaringan Sungai Final 6 km² vs RBI", title_en="Final 6 km² Stream Network vs RBI", sub_id="Validasi visual modeled drainage terhadap RBI", sub_en="Visual validation of modelled drainage against RBI", note_id="Threshold 6 km² menghasilkan network sekitar 81,00 km dibanding RBI 79,813 km. RBI adalah reference, bukan target yang dipaksakan 100%.", note_en="The 6 km² threshold produces about 81.00 km of network compared with 79.813 km for RBI. RBI is a reference, not a target forced to 100% agreement.", layers=[("binary","stream6","stream"),("line","rbi","river_ref"),("boundary","das","das")]),
"5.5": dict(stage="05_STAGE1", slug="WATERSHED_VS_REFERENCE", kind="single", title_id="Watershed Model vs DAS Referensi", title_en="Model Watershed vs Reference Watershed", sub_id="BREACH100 overlap dan residual mismatch", sub_en="BREACH100 overlap and residual mismatch", note_id="Watershed model 212,125 km² vs referensi sekitar 224,696 km²; IoU 0,9161; Dice 0,9562. Residual dipertahankan sebagai uncertainty.", note_en="Model watershed 212.125 km² vs reference about 224.696 km²; IoU 0.9161; Dice 0.9562. Residual mismatch is retained as uncertainty.", layers=[("binary","watershed","model_ws"),("binary","ref_only","ref_only"),("binary","model_only","model_only"),("boundary","das","das")]),
"5.6": dict(stage="05_STAGE1", slug="RESIDUAL_MISMATCH", kind="single", title_id="Residual Mismatch dan Uncertainty", title_en="Residual Mismatch and Uncertainty", sub_id="Residual spatial mismatch Stage 1", sub_en="Stage 1 residual spatial mismatch", note_id="Mismatch sengaja tidak dihapus melalui retuning. Residual menjadi uncertainty audit, bukan alasan memaksa model mengikuti reference secara sirkular.", note_en="Mismatch is intentionally not removed through retuning. Residuals are retained for uncertainty audit rather than forcing circular agreement with the reference.", layers=[("binary","ref_only","ref_only"),("binary","model_only","model_only"),("vector","residual_components","residual"),("line","rbi","river"),("boundary","das","das")]),
"6.1": dict(stage="06_STAGE2", slug="DAS_ADMINISTRASI", kind="single", title_id="Lokasi DAS dan Administrasi", title_en="Watershed and Administrative Context", sub_id="Wilayah administratif yang beririsan dengan DAS", sub_en="Administrative areas intersecting the watershed", note_id="DAS beririsan dengan 3 kabupaten/kota, 10 kecamatan, dan 41 desa/kelurahan. Pauh dan Kuranji adalah focus area administratif.", note_en="The watershed intersects 3 regencies/cities, 10 subdistricts, and 41 villages/urban villages. Pauh and Kuranji are the administrative focus area.", layers=[("admin","admin_all","admin"),("boundary","das","das")]),
"6.2": dict(stage="06_STAGE2", slug="RBI_VS_BASELINE_DRAINAGE", kind="single", title_id="Jaringan Sungai RBI dan Baseline Drainase", title_en="RBI River Network and Baseline Drainage", sub_id="Reference river vs modeled drainage", sub_en="Reference river versus modelled drainage", note_id="Jaringan lokal 6 km² dipertahankan sebagai drainage baseline untuk GFI karena panjang dan topology lebih seimbang terhadap RBI.", note_en="The local 6 km² network is retained as the GFI drainage baseline because its length and topology are more balanced against RBI.", layers=[("binary","stream6","stream"),("line","rbi","river_ref"),("boundary","das","das")]),
"6.3": dict(stage="06_STAGE2", slug="GFI_RAW", kind="single", title_id="GFI Raw", title_en="Raw GFI", sub_id="Distribusi Geomorphic Flood Index mentah", sub_en="Raw Geomorphic Flood Index distribution", note_id="GFI raw = ln(hr/H). Nilai ini merupakan baseline geomorphic screening variable, bukan observed inundation.", note_en="Raw GFI = ln(hr/H). It is a baseline geomorphic screening variable, not observed inundation.", layers=[("qml","gfi_raw","qml_gfi_raw"),("boundary","das","das")]),
"6.4": dict(stage="06_STAGE2", slug="GFI_NORMALIZED", kind="single", title_id="GFI Normalized", title_en="Normalised GFI", sub_id="GFI ternormalisasi pada baseline Stage 2", sub_en="Normalised GFI for the Stage 2 baseline", note_id="Manual threshold -0,53 dipertahankan sebagai sensitivity domain, sedangkan primary physical domain memakai WD > 0 / GFI_raw > 0.", note_en="The manual threshold -0.53 is retained as a sensitivity domain, while the primary physical domain uses WD > 0 / GFI_raw > 0.", layers=[("qml","gfi_norm","qml_gfi_norm"),("boundary","das","das")]),
"6.5": dict(stage="06_STAGE2", slug="WATER_DEPTH_P175", kind="single", title_id="Water Depth P175", title_en="P175 Water Depth", sub_id="Domain dan modeled water depth untuk P175", sub_en="P175 domain and modelled water depth", note_id="P175 menggunakan domain WD > 0. Water depth adalah modeled geomorphic quantity dari workflow GFI, bukan measured flood depth.", note_en="P175 uses the WD > 0 domain. Water depth is a modelled geomorphic quantity from the GFI workflow, not measured flood depth.", layers=[("qml","p175_wd","qml_p175_wd"),("boundary","das","das")]),
"6.6": dict(stage="06_STAGE2", slug="HAZARD_INDEX_P175", kind="single", title_id="Indeks Bahaya P175", title_en="P175 Hazard Index", sub_id="Fuzzy Large hazard index 0–1", sub_en="Fuzzy Large hazard index 0–1", note_id="Fuzzy Large: midpoint 1,125 m, spread 1,75. P175 adalah primary baseline hazard candidate, bukan probabilistic return-period hazard.", note_en="Fuzzy Large: midpoint 1.125 m, spread 1.75. P175 is the primary baseline hazard candidate, not a probabilistic return-period hazard.", layers=[("qml","p175_index","qml_p175_index"),("boundary","das","das")]),
"6.7": dict(stage="06_STAGE2", slug="HAZARD_CLASS_P175", kind="single", title_id="Kelas Bahaya P175 Seluruh DAS", title_en="P175 Hazard Classes Across the Watershed", sub_id="Low, Medium, High pada primary baseline candidate", sub_en="Low, Medium and High classes in the primary baseline candidate", note_id="P175 area ≈13,249 km² (5,90% DAS): Low 4,702 km²; Medium 4,257 km²; High 4,290 km².", note_en="P175 area ≈13.249 km² (5.90% of the watershed): Low 4.702 km²; Medium 4.257 km²; High 4.290 km².", layers=[("qml","p175_class","qml_p175_class"),("admin","admin_all","admin"),("boundary","das","das")]),
"6.8": dict(stage="06_STAGE2", slug="FOCUS_PAUH_KURANJI", kind="single_focus", title_id="Fokus Pauh dan Kuranji", title_en="Pauh and Kuranji Focus Area", sub_id="P175 dan 18 kelurahan focus area", sub_en="P175 and the 18-village focus area", note_id="Pauh dan Kuranji bersama mencakup sekitar 77,74% DAS. Focus area bersifat administratif; domain fisik model tetap seluruh DAS.", note_en="Pauh and Kuranji together cover about 77.74% of the watershed. The focus area is administrative; the model's physical domain remains the full watershed.", layers=[("qml","p175_class","qml_p175_class"),("focus","admin_focus","focus")]),
"6.9": dict(stage="06_STAGE2", slug="SENSITIVITY_M175_M250_P175_P250", kind="quad", title_id="Sensitivitas M175, M250, P175, dan P250", title_en="Sensitivity: M175, M250, P175 and P250", sub_id="Perbandingan spasial empat skenario Stage 2", sub_en="Spatial comparison of four Stage 2 scenarios", note_id="M-domain menggunakan threshold manual yang jauh lebih luas; P-domain memakai WD > 0. Ini sensitivity analysis, bukan empat peta hazard final yang setara.", note_en="The M-domain uses a much broader manual threshold, whereas the P-domain uses WD > 0. This is a sensitivity analysis, not four equivalent final hazard maps.", panels=[("M175","m175_class"),("M250","m250_class"),("P175","p175_class"),("P250","p250_class")]),
"7.1": dict(stage="07_STAGE3", slug="OBSERVED_BIG_BRIN", kind="single", title_id="Observed Flood Extent BIG/BRIN", title_en="BIG/BRIN Observed Flood Extent", sub_id="Post-event mapped flood extent 1 Desember 2025", sub_en="Post-event mapped flood extent, 1 December 2025", note_id="Observed extent ≈4,176 km². Reference ini bukan peak-event inundation dan tidak diperlakukan sebagai perfect flood truth.", note_en="Observed extent ≈4.176 km². This reference is not peak-event inundation and is not treated as perfect flood truth.", layers=[("qml","observed","qml_observed"),("admin","a3_admin_all","admin"),("boundary","das","das")]),
"7.2": dict(stage="07_STAGE3", slug="OBSERVED_VS_P175", kind="single", title_id="Observed vs P175", title_en="Observed vs P175", sub_id="Overlay post-event mapped extent dan primary baseline candidate", sub_en="Overlay of the post-event mapped extent and primary baseline candidate", note_id="Overlay menunjukkan correspondence dan mismatch. Model-only relatif terhadap 1 Desember bukan bukti definitif false alarm saat peak event.", note_en="The overlay shows correspondence and mismatch. Model-only areas relative to 1 December are not definitive evidence of false alarms at peak event.", layers=[("qml_alpha","a3_p175_class","qml_a3_p175",0.62),("qml_alpha","observed","qml_observed",0.80),("boundary","das","das")]),
"7.3": dict(stage="07_STAGE3", slug="P_DOMAIN_CONFUSION", kind="single", title_id="P-domain Confusion Map", title_en="P-domain Confusion Map", sub_id="TP, model-only, observed-only/FN, TN", sub_en="TP, model-only, observed-only/FN and TN", note_id="Strict r=0 P175: precision 0,1232; recall 0,3909; F1 0,1874; IoU 0,1034. Strict overlap tetap hasil validasi utama.", note_en="Strict r=0 P175: precision 0.1232; recall 0.3909; F1 0.1874; IoU 0.1034. Strict overlap remains the primary validation result.", layers=[("qml","p_confusion","qml_pconf"),("admin","a3_admin_all","admin"),("boundary","das","das")]),
"7.4": dict(stage="07_STAGE3", slug="OBSERVED_VS_M175", kind="single", title_id="Observed vs M175", title_en="Observed vs M175", sub_id="Overlay observed dengan sensitivity scenario M175", sub_en="Observed extent over the M175 sensitivity scenario", note_id="M175 memiliki recall sangat tinggi tetapi overprediction besar. M175 disimpan sebagai sensitivity scenario, bukan primary baseline.", note_en="M175 has very high recall but substantial overprediction. It is retained as a sensitivity scenario rather than the primary baseline.", layers=[("qml_alpha","a3_m175_class","qml_a3_m175",0.60),("qml_alpha","observed","qml_observed",0.80),("boundary","das","das")]),
"7.5": dict(stage="07_STAGE3", slug="M_DOMAIN_CONFUSION", kind="single", title_id="M-domain Confusion Map", title_en="M-domain Confusion Map", sub_id="Overprediction sensitivity scenario M175", sub_en="Overprediction in the M175 sensitivity scenario", note_id="M-domain menangkap hampir seluruh observed extent tetapi prediksi ≈60,138 km², sekitar 14× observed mapped extent. Ini menjelaskan mengapa M175 tidak dipilih sebagai baseline utama.", note_en="The M-domain captures almost all of the observed extent but predicts ≈60.138 km², about 14× the mapped observed extent. This explains why M175 was not selected as the primary baseline.", layers=[("qml","m_confusion","qml_mconf"),("admin","a3_admin_all","admin"),("boundary","das","das")]),
"7.6": dict(stage="07_STAGE3", slug="FOCUS_PAUH_KURANJI_VALIDATION", kind="single_focus", title_id="Focus Pauh–Kuranji", title_en="Pauh–Kuranji Focus", sub_id="Validasi pada focus administratif utama", sub_en="Validation within the main administrative focus", note_id="Focus map memperlihatkan hit/miss dalam Pauh–Kuranji. Interpretasi tetap memakai strict validation dan tidak mengubah threshold P175.", note_en="The focus map shows hits and misses within Pauh–Kuranji. Interpretation retains strict validation and does not alter the P175 threshold.", layers=[("qml_alpha","p_confusion","qml_pconf",0.90),("qml_alpha","observed","qml_observed",0.55),("focus","a3_admin_focus","focus")]),
"7.7": dict(stage="07_STAGE3", slug="FN_HOTSPOTS_P175", kind="single", title_id="Hotspot False Negative P175", title_en="P175 False-Negative Hotspots", sub_id="Observed-only terbesar pada validasi Stage 3", sub_en="Largest observed-only areas in Stage 3 validation", note_id="FN terbesar: Gurun Laweh 0,580; Tabiang Banda Gadang 0,478; Gunung Sarik 0,331; Kampung Olo 0,314; Kuranji 0,305 km². Hotspot adalah prioritas audit lokal, bukan dasar retuning otomatis.", note_en="Largest FN areas: Gurun Laweh 0.580; Tabiang Banda Gadang 0.478; Gunung Sarik 0.331; Kampung Olo 0.314; Kuranji 0.305 km². Hotspots are priorities for local audit, not automatic retuning.", layers=[("qml","p_confusion","qml_pconf"),("admin","a3_admin_all","admin_labels"),("boundary","das","das")]),
"7.8": dict(stage="07_STAGE3", slug="P175_VS_M175", kind="compare2", title_id="Scenario Comparison P175 vs M175", title_en="Scenario Comparison: P175 vs M175", sub_id="Primary baseline candidate vs high-recall sensitivity scenario", sub_en="Primary baseline candidate versus high-recall sensitivity scenario", note_id="P175 lebih seimbang pada F1/IoU; M175 mempertahankan recall tinggi tetapi overprediction besar. Keduanya tidak dituning ulang pada event validasi.", note_en="P175 is more balanced on F1/IoU; M175 retains high recall but has substantial overprediction. Neither is retuned on the validation event.", panels=[("P175","a3_p175_class","qml_a3_p175"),("M175","a3_m175_class","qml_a3_m175")]),
"8.1": dict(stage="08_STAGE4", slug="SENTINEL1_EVENT_MINUS_PRE", kind="triple_s1", title_id="Sentinel-1 EVENT minus PRE", title_en="Sentinel-1 EVENT minus PRE", sub_id="Median 3×3 backscatter change pada common 20 m grid", sub_en="Median 3×3 backscatter change on the common 20 m grid", note_id="Acquisition 22 Nov adalah label internal EVENT/early-event-window dan mendahului documented Senyar formation 26 Nov. Interpretasi dibatasi pada perubahan keadaan permukaan/backscatter, bukan direct cyclone effect atau elevation change.", note_en="The 22 Nov acquisition is the internal EVENT/early-event-window label and predates documented Senyar formation on 26 Nov. Interpretation is limited to surface-state/backscatter change, not direct cyclone effect or elevation change.", panels=[("VV ΔdB","s1_event_vv"),("VH ΔdB","s1_event_vh"),("VH−VV ΔdB","s1_event_ratio")]),
"8.2": dict(stage="08_STAGE4", slug="SENTINEL1_POST_MINUS_PRE", kind="triple_s1", title_id="Sentinel-1 POST minus PRE", title_en="Sentinel-1 POST minus PRE", sub_id="Persistent surface-state change pada acquisition 4 Desember 2025", sub_en="Persistent surface-state change on the 4 December 2025 acquisition", note_id="Contrast backscatter tetap tampak pada POST. Mekanisme potensial mencakup moisture, residual inundation, sediment, roughness, vegetation disturbance, dan kondisi permukaan lain.", note_en="Backscatter contrast remains visible in POST. Potential mechanisms include moisture, residual inundation, sediment, roughness, vegetation disturbance and other surface conditions.", panels=[("VV ΔdB","s1_post_vv"),("VH ΔdB","s1_post_vh"),("VH−VV ΔdB","s1_post_ratio")]),
"8.3": dict(stage="08_STAGE4", slug="MULTIMODAL_INTEGRATION", kind="picture", title_id="Integrasi Multimodal Stage 4", title_en="Stage 4 Multimodal Integration", sub_id="P175 + observed BIG/BRIN + TP/FN + drainage + Sentinel-1", sub_en="P175 + BIG/BRIN observed extent + TP/FN + drainage + Sentinel-1", note_id="P175 tetap baseline candidate; BIG/BRIN adalah external observed extent; Sentinel-1 adalah surface-state evidence; ICESat-2 tidak menyediakan defensible Δh. Tidak ada true ΔDEM, pre/post GFI, atau quantified pre/post hazard-index change.", note_en="P175 remains the baseline candidate; BIG/BRIN is the external observed extent; Sentinel-1 provides surface-state evidence; ICESat-2 does not provide defensible Δh. There is no true ΔDEM, pre/post GFI, or quantified pre/post hazard-index change.", picture="integration_png"),
"8.4": dict(stage="08_STAGE4", slug="ICESAT2_COMPARABILITY", kind="icesat", title_id="ICESat-2 Repeat-Track Comparability", title_en="ICESat-2 Repeat-Track Comparability", sub_id="PRE 14 Oct 2025 vs POST 13 Jan 2026 · beams gt3l/gt3r", sub_en="PRE 14 Oct 2025 vs POST 13 Jan 2026 · beams gt3l/gt3r", note_id="RGT0453 gagal positional comparability: same-Y beam separation sekitar 12,6 km dan 0% within 100 m. NO Δh CALCULATED.", note_en="RGT0453 fails positional comparability: same-Y beam separation is about 12.6 km and 0% is within 100 m. NO Δh CALCULATED."),
}

# -----------------------------------------------------------------------------
# Geometry and raster helpers
# -----------------------------------------------------------------------------
def srs_epsg(epsg):
    s = osr.SpatialReference(); s.ImportFromEPSG(epsg)
    try: s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    except Exception: pass
    return s

def open_layer(path):
    ds = ogr.Open(str(path), 0)
    if ds is None: raise RuntimeError(f"Cannot open vector: {path}")
    lyr = ds.GetLayer(0)
    return ds, lyr

def iter_geom(path, target_epsg=32747):
    ds, lyr = open_layer(path)
    src = lyr.GetSpatialRef()
    fields = [lyr.GetLayerDefn().GetFieldDefn(i).GetName() for i in range(lyr.GetLayerDefn().GetFieldCount())]
    if src:
        src = src.Clone()
        try: src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        except Exception: pass
    dst = srs_epsg(target_epsg)
    ct = None if src is None or src.IsSame(dst) else osr.CoordinateTransformation(src, dst)
    for feat in lyr:
        g = feat.GetGeometryRef()
        if g is None or g.IsEmpty(): continue
        g = g.Clone()
        if ct:
            try:
                if g.Transform(ct) != 0: continue
            except Exception: continue
        attrs = {f: feat.GetField(f) for f in fields}
        yield g, attrs
    ds = None

def extent_vector(path, epsg=32747, margin=0.05):
    vals=[]
    for g,_ in iter_geom(path,epsg): vals.append(g.GetEnvelope())
    if not vals: raise RuntimeError(f"No geometry: {path}")
    xmin=min(v[0] for v in vals); xmax=max(v[1] for v in vals); ymin=min(v[2] for v in vals); ymax=max(v[3] for v in vals)
    p=max(xmax-xmin,ymax-ymin)*margin
    return xmin-p,xmax+p,ymin-p,ymax+p

def draw_geom(ax,g,fc="none",ec="#333",lw=.6,alpha=1,z=3,hatch=None):
    gt=ogr.GT_Flatten(g.GetGeometryType())
    if gt==ogr.wkbPolygon:
        if g.GetGeometryCount()==0:return
        r=g.GetGeometryRef(0)
        if not r or r.GetPointCount()<3:return
        xy=[(r.GetX(i),r.GetY(i)) for i in range(r.GetPointCount())]
        ax.add_patch(MplPolygon(xy,closed=True,facecolor=fc,edgecolor=ec,linewidth=lw,alpha=alpha,zorder=z,hatch=hatch))
    elif gt in (ogr.wkbLineString,ogr.wkbLinearRing):
        if g.GetPointCount()<2:return
        ax.plot([g.GetX(i) for i in range(g.GetPointCount())],[g.GetY(i) for i in range(g.GetPointCount())],color=ec,lw=lw,alpha=alpha,zorder=z)
    elif gt==ogr.wkbPoint:
        ax.scatter([g.GetX()],[g.GetY()],s=18,c=ec,zorder=z)
    elif gt in (ogr.wkbMultiPolygon,ogr.wkbMultiLineString,ogr.wkbGeometryCollection):
        for i in range(g.GetGeometryCount()):
            sg=g.GetGeometryRef(i)
            if sg: draw_geom(ax,sg,fc,ec,lw,alpha,z,hatch)

def draw_vector(ax,path,style,labels=False):
    styles={
        "das":dict(fc="none",ec="#1769aa",lw=1.45,z=12),
        "river":dict(fc="none",ec="#2385c6",lw=.65,z=10),
        "river_ref":dict(fc="none",ec="#d84335",lw=.85,z=11),
        "admin":dict(fc="none",ec="#999",lw=.38,z=8),
        "focus":dict(fc="#b8d96b",ec="#5b8735",lw=.55,alpha=.48,z=8),
        "residual":dict(fc="#c036d3",ec="#8b159b",lw=.65,alpha=.20,z=9),
        "admin_labels":dict(fc="none",ec="#a0a0a0",lw=.35,z=8),
    }
    st=styles.get(style,styles["admin"])
    for g,a in iter_geom(path,32747): draw_geom(ax,g,**st)
    if labels:
        candidates=["NAMOBJ","WADMKD","KELURAHAN","DESA","NAMA_DESA","NAMA_KEL","WADMKC","KECAMATAN","NAME_4","NAME_3","name","NAME"]
        seen=set(); n=0
        for g,a in iter_geom(path,32747):
            name=None
            lower={str(k).lower():v for k,v in a.items()}
            for c in candidates:
                v=lower.get(c.lower())
                if v not in (None,""): name=str(v); break
            if not name or name.lower() in seen: continue
            c=g.Centroid()
            if not c or c.IsEmpty(): continue
            seen.add(name.lower()); n+=1
            ax.text(c.GetX(),c.GetY(),name,fontsize=5.2,ha="center",va="center",zorder=20,path_effects=[pe.withStroke(linewidth=1.5,foreground="white")])
            if n>=28: break

def read_raster(path):
    ds=gdal.Open(str(path))
    if ds is None: raise RuntimeError(f"Cannot open raster: {path}")
    a=ds.GetRasterBand(1).ReadAsArray().astype(float)
    nd=ds.GetRasterBand(1).GetNoDataValue()
    if nd is not None: a[np.isclose(a,nd,equal_nan=False)] = np.nan
    gt=ds.GetGeoTransform(); x0,px,_,y0,_,py=gt
    xmax=x0+ds.RasterXSize*px; ymin=y0+ds.RasterYSize*py
    ext=(min(x0,xmax),max(x0,xmax),min(y0,ymin),max(y0,ymin))
    ds=None
    return a,ext

def parse_color(c):
    if not c: return "#808080"
    c=str(c).strip()
    if c.startswith("#"): return c[:7] if len(c)>=7 else c
    parts=c.split(",")
    try:
        vals=[int(float(x)) for x in parts[:3]]
        return "#%02x%02x%02x"%tuple(vals)
    except Exception:return "#808080"

def qml_entries(path):
    try: root=ET.parse(path).getroot()
    except Exception:return []
    out=[]
    for el in root.iter():
        at=el.attrib
        if "value" in at and ("color" in at or "colour" in at):
            try:v=float(at["value"])
            except Exception:continue
            col=parse_color(at.get("color") or at.get("colour")); lab=at.get("label",str(v))
            out.append((v,col,lab))
    uniq={}
    for v,c,l in out: uniq[v]=(v,c,l)
    return [uniq[k] for k in sorted(uniq)]
def plot_qml(ax,rkey,qkey,alpha=1.0):
    a,ext=read_raster(SRC[rkey]); entries=qml_entries(SRC[qkey])
    valid=a[np.isfinite(a)]
    if entries:
        vals=[x[0] for x in entries]; cols=[x[1] for x in entries]
        integerish=all(abs(v-round(v))<1e-8 for v in vals) and len(vals)<=12
        if integerish:
            m=np.ma.masked_invalid(a); keys=sorted(set(vals));
            lo=[k-.5 for k in keys]+[keys[-1]+.5]
            cmap=ListedColormap(cols); norm=BoundaryNorm(lo,len(cols))
            im=ax.imshow(m,extent=ext,origin="upper",cmap=cmap,norm=norm,alpha=alpha,zorder=2)
            handles=[Patch(facecolor=c,edgecolor="none",label=l) for _,c,l in entries]
            return im,handles
        cmap=LinearSegmentedColormap.from_list("qml",[(v,c) for v,c,_ in entries])
        norm=Normalize(min(vals),max(vals))
        im=ax.imshow(np.ma.masked_invalid(a),extent=ext,origin="upper",cmap=cmap,norm=norm,alpha=alpha,zorder=2)
        return im,None
    vmin,vmax=np.nanpercentile(valid,[2,98]) if valid.size else (0,1)
    im=ax.imshow(np.ma.masked_invalid(a),extent=ext,origin="upper",cmap="viridis",vmin=vmin,vmax=vmax,alpha=alpha,zorder=2)
    return im,None

def plot_cont(ax,key,style,alpha=1):
    a,ext=read_raster(SRC[key]); v=a[np.isfinite(a)]
    if style=="flowacc":
        a=np.log1p(np.where(a<0,np.nan,a)); v=a[np.isfinite(a)]; cmap="Blues"
    elif style=="dem": cmap="terrain"
    else:cmap="viridis"
    lo,hi=np.nanpercentile(v,[2,98]) if v.size else (0,1)
    return ax.imshow(np.ma.masked_invalid(a),extent=ext,origin="upper",cmap=cmap,vmin=lo,vmax=hi,alpha=alpha,zorder=2),None

def plot_binary(ax,key,style,alpha=.8):
    a,ext=read_raster(SRC[key]); m=np.ma.masked_where(~np.isfinite(a)|(a==0),a)
    colors={"pour":"#ff00aa","stream":"#0033cc","model_ws":"#4f83f1","ref_only":"#d23232","model_only":"#f59123"}
    labels={"pour":"Outlet / pour point","stream":"Modeled stream ≥6 km²","model_ws":"Model watershed","ref_only":"Reference-only","model_only":"Model-only"}
    c=colors.get(style,"#5b8ff9"); im=ax.imshow(m,extent=ext,origin="upper",cmap=ListedColormap([c]),vmin=1,vmax=max(1,np.nanmax(m)),alpha=alpha,zorder=4)
    return im,[Patch(facecolor=c,label=labels.get(style,style))]

def plot_layer(ax,spec):
    typ=spec[0]
    if typ=="boundary": draw_vector(ax,SRC[spec[1]],spec[2]); return None,[]
    if typ=="line": draw_vector(ax,SRC[spec[1]],spec[2]); return None,[Line2D([0],[0],color="#d84335" if spec[2]=="river_ref" else "#2385c6",lw=1.2,label="RBI / river")]
    if typ=="admin": draw_vector(ax,SRC[spec[1]],"admin",labels=(spec[2]=="admin_labels")); return None,[Line2D([0],[0],color="#999",lw=.8,label="Administrative boundary")]
    if typ=="focus": draw_vector(ax,SRC[spec[1]],"focus",labels=True); return None,[Patch(facecolor="#b8d96b",edgecolor="#5b8735",alpha=.5,label="Pauh–Kuranji focus")]
    if typ=="vector": draw_vector(ax,SRC[spec[1]],spec[2]); return None,[Patch(facecolor="#c036d3",edgecolor="#8b159b",alpha=.2,label="Residual component")]
    if typ=="continuous": return plot_cont(ax,spec[1],spec[2])
    if typ=="binary": return plot_binary(ax,spec[1],spec[2])
    if typ=="qml": return plot_qml(ax,spec[1],spec[2])
    if typ=="qml_alpha": return plot_qml(ax,spec[1],spec[2],spec[3])
    raise ValueError(spec)

# -----------------------------------------------------------------------------
# Cartographic layout helpers
# -----------------------------------------------------------------------------
def nice_degree_step(span):
    for s in (.02,.05,.1,.2,.5,1,2):
        if span/s<=6:return s
    return 5
def transformer(src,dst): return osr.CoordinateTransformation(srs_epsg(src),srs_epsg(dst))
def xy(ct,x,y):
    p=ct.TransformPoint(float(x),float(y)); return p[0],p[1]
def add_graticule(ax,ext):
    xmin,xmax,ymin,ymax=ext; to_ll=transformer(32747,4326); to_xy=transformer(4326,32747)
    cs=[xy(to_ll,x,y) for x,y in ((xmin,ymin),(xmin,ymax),(xmax,ymin),(xmax,ymax))]
    lons=[p[0] for p in cs]; lats=[p[1] for p in cs]
    ds=nice_degree_step(max(lons)-min(lons)); ts=nice_degree_step(max(lats)-min(lats))
    lon=math.ceil(min(lons)/ds)*ds
    while lon<=max(lons)+1e-9:
        pts=[xy(to_xy,lon,min(lats)+(max(lats)-min(lats))*i/60) for i in range(61)]
        ax.plot([p[0] for p in pts],[p[1] for p in pts],color="#999",lw=.28,alpha=.4,zorder=1)
        xlab,_=xy(to_xy,lon,max(lats)); ax.text(xlab,ymax,f"{lon:.2f}°E",fontsize=5.5,ha="center",va="bottom",clip_on=False)
        lon+=ds
    lat=math.ceil(min(lats)/ts)*ts
    while lat<=max(lats)+1e-9:
        pts=[xy(to_xy,min(lons)+(max(lons)-min(lons))*i/60,lat) for i in range(61)]
        ax.plot([p[0] for p in pts],[p[1] for p in pts],color="#999",lw=.28,alpha=.4,zorder=1)
        _,yl=xy(to_xy,min(lons),lat); ax.text(xmin,yl,f"{abs(lat):.2f}°{'S' if lat<0 else 'N'}",fontsize=5.5,ha="right",va="center",rotation=90,clip_on=False)
        lat+=ts
def style_ax(ax,ext,grid=True):
    ax.set_xlim(ext[0],ext[1]);ax.set_ylim(ext[2],ext[3]);ax.set_aspect("equal",adjustable="box");ax.set_xticks([]);ax.set_yticks([])
    for s in ax.spines.values():s.set_color("#333");s.set_linewidth(.8)
    if grid:add_graticule(ax,ext)
def add_north(ax):
    ax.annotate("",xy=(.055,.91),xytext=(.055,.80),xycoords="axes fraction",textcoords="axes fraction",arrowprops=dict(arrowstyle="simple",fc="black",ec="black",mutation_scale=25),zorder=30)
    ax.text(.055,.765,"N",transform=ax.transAxes,fontsize=12,fontweight="bold",ha="center",path_effects=[pe.withStroke(linewidth=2,foreground="white")],zorder=31)
def nice_number(v):
    if v<=0:return 1
    e=math.floor(math.log10(v)); f=v/10**e
    n=1 if f<1.5 else 2 if f<3.5 else 5 if f<7.5 else 10
    return n*10**e
def add_scalebar(ax,ext):
    xmin,xmax,ymin,ymax=ext; w=xmax-xmin;h=ymax-ymin;L=nice_number(w*.12)
    x0=xmin+w*.035;y0=ymin+h*.05;bh=h*.009;seg=L/4
    for i in range(4):
        ax.add_patch(MplPolygon([(x0+i*seg,y0),(x0+(i+1)*seg,y0),(x0+(i+1)*seg,y0+bh),(x0+i*seg,y0+bh)],closed=True,facecolor="black" if i%2==0 else "white",edgecolor="black",lw=.5,zorder=25))
    ax.text(x0,y0+bh*1.5,"0",fontsize=6.2,ha="center");ax.text(x0+L/2,y0+bh*1.5,f"{L/2000:g}",fontsize=6.2,ha="center");ax.text(x0+L,y0+bh*1.5,f"{L/1000:g} km",fontsize=6.2,ha="center")
def panel_box(fig,pos,title,text,fs=8.2):
    ax=fig.add_axes(pos);ax.set_facecolor("#f7f7f7");ax.set_xticks([]);ax.set_yticks([])
    for s in ax.spines.values():s.set_color("#888");s.set_linewidth(.7)
    ax.text(.04,.91,title,transform=ax.transAxes,fontsize=10,fontweight="bold",va="top")
    ax.text(.04,.73,textwrap.fill(text,48),transform=ax.transAxes,fontsize=fs,va="top",linespacing=1.28,color="#222")
    return ax
def source_text(lang,map_id):
    if lang=="id": return f"Sumber: frozen output penelitian Stage {map_id.split('.')[0]} / paket sumber terkait | CRS utama: WGS 84 / UTM Zone 47S (EPSG:32747) | Tahun data: mengikuti metadata sumber."
    return f"Source: frozen research outputs for Stage {map_id.split('.')[0]} / associated source package | Main CRS: WGS 84 / UTM Zone 47S (EPSG:32747) | Data year: according to source metadata."
def title_for(m,lang,key): return m[f"{key}_{lang}"]
def extent_for(m): return extent_vector(SRC["admin_focus" if m["kind"]=="single_focus" else "das"],32747,.07 if m["kind"]=="single_focus" else .055)

def render_single(mid,m,lang,dpi):
    fig=plt.figure(figsize=(16.54,11.69),facecolor="white")
    fig.text(.5,.965,f"{'PETA' if lang=='id' else 'MAP'} {mid}. {title_for(m,lang,'title').upper()}",ha="center",va="top",fontsize=19,fontweight="bold")
    fig.text(.5,.936,title_for(m,lang,'sub'),ha="center",va="top",fontsize=9.5,color="#555")
    ax=fig.add_axes([.035,.225,.675,.64]);ext=extent_for(m);ax.set_facecolor("white")
    legends=[]; last_im=None
    for spec in m["layers"]:
        im,hs=plot_layer(ax,spec); last_im=im if im is not None else last_im; legends+=hs
    style_ax(ax,ext,True);add_north(ax);add_scalebar(ax,ext)
    # Colorbar for continuous/QML continuous renderers.
    if last_im is not None and not isinstance(getattr(last_im,"norm",None),BoundaryNorm):
        cax=fig.add_axes([.735,.655,.22,.018]);cb=fig.colorbar(last_im,cax=cax,orientation="horizontal");cb.ax.tick_params(labelsize=6)
    legax=fig.add_axes([.735,.49,.23,.14]);legax.set_xticks([]);legax.set_yticks([])
    for s in legax.spines.values():s.set_color("#888");s.set_linewidth(.7)
    legax.text(.04,.90,"LEGENDA" if lang=="id" else "LEGEND",transform=legax.transAxes,fontsize=10,fontweight="bold",va="top")
    # Deduplicate legend labels.
    uniq=[];seen=set()
    for h in legends:
        lab=h.get_label()
        if lab not in seen:uniq.append(h);seen.add(lab)
    if uniq:legax.legend(handles=uniq,loc="upper left",bbox_to_anchor=(.03,.73),frameon=False,fontsize=7.2,labelspacing=.65)
    panel_box(fig,[.735,.275,.23,.18],"RINGKASAN HASIL" if lang=="id" else "RESULT SUMMARY",title_for(m,lang,'note'),7.6)
    panel_box(fig,[.035,.075,.675,.105],"CATATAN ILMIAH" if lang=="id" else "SCIENTIFIC NOTE",title_for(m,lang,'note'),7.6)
    fig.text(.735,.075,source_text(lang,mid),fontsize=7.2,va="bottom",ha="left",color="#444",wrap=True)
    save(fig,mid,m,lang,dpi)

def hazard_plot(ax,key,qml=None):
    if qml:return plot_qml(ax,key,qml)[0]
    a,e=read_raster(SRC[key]);vals=sorted(int(x) for x in np.unique(a[np.isfinite(a)]) if x>0)
    colors=["#7bc96f","#f2c84b","#d9534f","#8b1a1a"][:max(1,len(vals))]
    return ax.imshow(np.ma.masked_where(~np.isfinite(a)|(a<=0),a),extent=e,origin="upper",cmap=ListedColormap(colors),vmin=min(vals or [1]),vmax=max(vals or [1]),zorder=2)
def render_quad(mid,m,lang,dpi):
    fig=plt.figure(figsize=(16.54,11.69),facecolor="white")
    fig.text(.5,.965,f"{'PETA' if lang=='id' else 'MAP'} {mid}. {title_for(m,lang,'title').upper()}",ha="center",va="top",fontsize=18,fontweight="bold")
    fig.text(.5,.935,title_for(m,lang,'sub'),ha="center",fontsize=9,color="#555")
    positions=[[.035,.53,.43,.34],[.53,.53,.43,.34],[.035,.15,.43,.34],[.53,.15,.43,.34]];ext=extent_vector(SRC["das"],32747,.05)
    for (lab,key),pos in zip(m["panels"],positions):
        ax=fig.add_axes(pos);hazard_plot(ax,key,"qml_p175_class");draw_vector(ax,SRC["das"],"das");style_ax(ax,ext,False);ax.set_title(lab,fontsize=10,fontweight="bold");add_scalebar(ax,ext)
    fig.text(.035,.07,textwrap.fill(title_for(m,lang,'note'),150),fontsize=8,color="#333")
    save(fig,mid,m,lang,dpi)
def render_compare2(mid,m,lang,dpi):
    fig=plt.figure(figsize=(16.54,11.69),facecolor="white")
    fig.text(.5,.965,f"{'PETA' if lang=='id' else 'MAP'} {mid}. {title_for(m,lang,'title').upper()}",ha="center",va="top",fontsize=18,fontweight="bold")
    fig.text(.5,.935,title_for(m,lang,'sub'),ha="center",fontsize=9,color="#555")
    ext=extent_vector(SRC["das"],32747,.05)
    for (lab,key,qml),pos in zip(m["panels"],[[.035,.20,.455,.65],[.51,.20,.455,.65]]):
        ax=fig.add_axes(pos);plot_qml(ax,key,qml);draw_vector(ax,SRC["das"],"das");style_ax(ax,ext,True);ax.set_title(lab,fontsize=11,fontweight="bold");add_north(ax);add_scalebar(ax,ext)
    fig.text(.035,.09,textwrap.fill(title_for(m,lang,'note'),150),fontsize=8,color="#333")
    save(fig,mid,m,lang,dpi)
def sentinel_limit(keys):
    vals=[]
    for k in keys:
        a,_=read_raster(SRC[k]);v=np.abs(a[np.isfinite(a)]); 
        if v.size: vals.append(v)
    if not vals:return 1.0
    return float(np.nanpercentile(np.concatenate(vals),98))
def render_triple_s1(mid,m,lang,dpi):
    fig=plt.figure(figsize=(16.54,11.69),facecolor="white")
    fig.text(.5,.965,f"{'PETA' if lang=='id' else 'MAP'} {mid}. {title_for(m,lang,'title').upper()}",ha="center",va="top",fontsize=18,fontweight="bold")
    fig.text(.5,.935,title_for(m,lang,'sub'),ha="center",fontsize=9,color="#555")
    keys=[k for _,k in m["panels"]];L=sentinel_limit(keys);ext=extent_vector(SRC["das"],32747,.05);last=None
    for (lab,key),pos in zip(m["panels"],[[.025,.25,.31,.58],[.345,.25,.31,.58],[.665,.25,.31,.58]]):
        ax=fig.add_axes(pos);a,e=read_raster(SRC[key]);last=ax.imshow(np.ma.masked_invalid(a),extent=e,origin="upper",cmap="RdBu_r",vmin=-L,vmax=L,zorder=2);plot_binary(ax,"observed20","observed",.35);draw_vector(ax,SRC["das"],"das");style_ax(ax,ext,False);ax.set_title(lab,fontsize=10,fontweight="bold");add_scalebar(ax,ext)
    cax=fig.add_axes([.30,.19,.40,.018]);cb=fig.colorbar(last,cax=cax,orientation="horizontal");cb.set_label("ΔdB (cartographic symmetric 98th-percentile scale)",fontsize=7);cb.ax.tick_params(labelsize=6)
    fig.text(.035,.085,textwrap.fill(title_for(m,lang,'note'),155),fontsize=8,color="#333")
    save(fig,mid,m,lang,dpi)
def render_picture(mid,m,lang,dpi):
    fig=plt.figure(figsize=(16.54,11.69),facecolor="white")
    fig.text(.5,.965,f"{'PETA' if lang=='id' else 'MAP'} {mid}. {title_for(m,lang,'title').upper()}",ha="center",va="top",fontsize=18,fontweight="bold")
    fig.text(.5,.935,title_for(m,lang,'sub'),ha="center",fontsize=9,color="#555")
    ax=fig.add_axes([.035,.18,.67,.68]);img=plt.imread(SRC[m["picture"]]);ax.imshow(img);ax.axis("off")
    panel_box(fig,[.74,.47,.225,.32],"RINGKASAN" if lang=="id" else "SUMMARY",title_for(m,lang,'note'),7.5)
    panel_box(fig,[.74,.18,.225,.24],"BATAS KLAIM" if lang=="id" else "CLAIM LIMITS",("Tidak ada true ΔDEM, Δh, pre/post GFI, atau quantified pre/post hazard-index change." if lang=="id" else "No true ΔDEM, Δh, pre/post GFI, or quantified pre/post hazard-index change."),7.5)
    save(fig,mid,m,lang,dpi)
def load_icesat(path):
    rows=[]
    with path.open(newline="",encoding="utf-8") as f:
        rd=csv.DictReader(f);fields=rd.fieldnames or [];low={x.lower():x for x in fields}
        def pick(cs):
            for c in cs:
                if c.lower() in low:return low[c.lower()]
        fx=pick(["x_utm47s","x","easting"]);fy=pick(["y_utm47s","y","northing"]);fb=pick(["beam","beam_name"])
        if not fx or not fy:return rows
        for r in rd:
            if fb and r.get(fb) not in ("gt3l","gt3r"):continue
            try:rows.append((float(r[fx]),float(r[fy]),r.get(fb,"")))
            except Exception:pass
    return rows
def render_icesat(mid,m,lang,dpi):
    fig=plt.figure(figsize=(16.54,11.69),facecolor="white")
    fig.text(.5,.965,f"{'PETA' if lang=='id' else 'MAP'} {mid}. {title_for(m,lang,'title').upper()}",ha="center",va="top",fontsize=18,fontweight="bold")
    fig.text(.5,.935,title_for(m,lang,'sub'),ha="center",fontsize=9,color="#555")
    pre=load_icesat(SRC["icesat_pre_csv"]);post=load_icesat(SRC["icesat_post_csv"]);xs=[x for x,y,b in pre+post];ys=[y for x,y,b in pre+post];de=extent_vector(SRC["das"],32747,.05)
    if xs:ext=(min(min(xs),de[0]),max(max(xs),de[1]),min(min(ys),de[2]),max(max(ys),de[3]));p=max(ext[1]-ext[0],ext[3]-ext[2])*.04;ext=(ext[0]-p,ext[1]+p,ext[2]-p,ext[3]+p)
    else:ext=de
    ax=fig.add_axes([.035,.22,.68,.64]);draw_vector(ax,SRC["das"],"das");
    if pre:ax.scatter([x for x,y,b in pre],[y for x,y,b in pre],s=4,c="#1e6bd6",label="PRE 14 Oct 2025",zorder=5)
    if post:ax.scatter([x for x,y,b in post],[y for x,y,b in post],s=5,c="#dc3732",marker="^",label="POST 13 Jan 2026",zorder=6)
    style_ax(ax,ext,False);ax.legend(fontsize=8,loc="upper right");add_north(ax);add_scalebar(ax,ext)
    panel_box(fig,[.75,.45,.21,.29],"RINGKASAN" if lang=="id" else "SUMMARY",title_for(m,lang,'note'),7.5)
    save(fig,mid,m,lang,dpi)
def save(fig,mid,m,lang,dpi):
    d=OUT/m["stage"]/lang.upper();d.mkdir(parents=True,exist_ok=True);base=f"{'PETA' if lang=='id' else 'MAP'}_{mid.replace('.','_')}_{m['slug']}"
    png=d/f"{base}.png";pdf=d/f"{base}.pdf";fig.savefig(png,dpi=dpi,facecolor="white");fig.savefig(pdf,dpi=dpi,facecolor="white");plt.close(fig)
    manifest.append(dict(map_id=mid,language=lang,stage=m["stage"],slug=m["slug"],png=str(png.relative_to(ROOT)),pdf=str(pdf.relative_to(ROOT)),png_bytes=png.stat().st_size,pdf_bytes=pdf.stat().st_size,status="OK"))
    print(f"RENDER_OK map={mid} lang={lang} png_bytes={png.stat().st_size}")

manifest=[]
selected={x.strip() for x in args.only.split(",") if x.strip()}
langs=[x.strip().lower() for x in args.lang.split(",") if x.strip()]

missing=[str(p) for p in SRC.values() if not p.exists()]
if missing:
    print("SOURCE_PREFLIGHT=FAIL")
    for p in missing:print("MISSING="+p)
    raise SystemExit(2)
print("SOURCE_PREFLIGHT=PASS")

for mid,m in MAPS.items():
    if selected and mid not in selected:continue
    for lang in langs:
        print(f"=== RENDER {mid} {lang} ===")
        if m["kind"] in ("single","single_focus"):render_single(mid,m,lang,args.dpi)
        elif m["kind"]=="quad":render_quad(mid,m,lang,args.dpi)
        elif m["kind"]=="compare2":render_compare2(mid,m,lang,args.dpi)
        elif m["kind"]=="triple_s1":render_triple_s1(mid,m,lang,args.dpi)
        elif m["kind"]=="picture":render_picture(mid,m,lang,args.dpi)
        elif m["kind"]=="icesat":render_icesat(mid,m,lang,args.dpi)

OUT.mkdir(parents=True,exist_ok=True)
with (OUT/"MAP_MANIFEST_5_2_TO_8_4.csv").open("w",newline="",encoding="utf-8") as f:
    fields=["map_id","language","stage","slug","png","pdf","png_bytes","pdf_bytes","status"];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(manifest)
summary={"renderer":"GDAL/OGR + Matplotlib","maps":"5.2-8.4","languages":langs,"rendered":len(manifest),"guardrails":["no analytical recalculation","no true delta DEM","no delta h","no pre/post GFI","no quantified pre/post hazard-index change","Sentinel-1 scale is cartographic symmetric 98th percentile only"]}
(OUT/"RUN_SUMMARY_5_2_TO_8_4.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
print(f"FINAL_STATUS=COMPLETE rendered={len(manifest)}")
