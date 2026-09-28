#!/usr/bin/env python3
from pathlib import Path
from shutil import copy2, rmtree
from zipfile import ZipFile, ZIP_DEFLATED
import csv, json

ROOT = Path('/opt/demnas-bulk-downloader')
SRC_51 = ROOT / 'artifacts/KURANJI_FINAL_PYTHON_MAPS_V4/05_STAGE1'
SRC_52_84 = ROOT / 'artifacts/KURANJI_FINAL_ALL27_BILINGUAL'
OUT = ROOT / 'artifacts/KURANJI_FINAL_54_MAPS_BILINGUAL'
ZIP = ROOT / 'artifacts/KURANJI_FINAL_54_MAPS_BILINGUAL.zip'

EXPECTED = []
for lang in ('ID','EN'):
    if lang == 'ID':
        EXPECTED.append((SRC_51/lang/'PETA_5_1_LOKASI_DAS_KURANJI_V4.png', '05_STAGE1/ID/PETA_5_1_LOKASI_DAS_KURANJI.png'))
        EXPECTED.append((SRC_51/lang/'PETA_5_1_LOKASI_DAS_KURANJI_V4.pdf', '05_STAGE1/ID/PETA_5_1_LOKASI_DAS_KURANJI.pdf'))
    else:
        EXPECTED.append((SRC_51/lang/'MAP_5_1_BATANG_KURANJI_STUDY_AREA_V4.png', '05_STAGE1/EN/MAP_5_1_BATANG_KURANJI_STUDY_AREA.png'))
        EXPECTED.append((SRC_51/lang/'MAP_5_1_BATANG_KURANJI_STUDY_AREA_V4.pdf', '05_STAGE1/EN/MAP_5_1_BATANG_KURANJI_STUDY_AREA.pdf'))

missing = [str(src) for src, _ in EXPECTED if not src.exists()]
if not SRC_52_84.exists():
    missing.append(str(SRC_52_84))
if missing:
    print('PACKAGE_PREFLIGHT=FAIL')
    for p in missing: print('MISSING=' + p)
    raise SystemExit(2)
print('PACKAGE_PREFLIGHT=PASS')

if OUT.exists():
    rmtree(OUT)
OUT.mkdir(parents=True)

# Copy 5.2-8.4 tree first.
for p in SRC_52_84.rglob('*'):
    if p.is_file() and p.suffix.lower() in ('.png','.pdf'):
        rel = p.relative_to(SRC_52_84)
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        copy2(p, dst)

# Copy 5.1 V4 with final names.
for src, rel in EXPECTED:
    dst = OUT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    copy2(src, dst)

pngs = sorted(OUT.rglob('*.png'))
pdfs = sorted(OUT.rglob('*.pdf'))
print(f'PNG_COUNT={len(pngs)}')
print(f'PDF_COUNT={len(pdfs)}')

# Build manifest from actual final package.
rows = []
for p in pngs:
    rel = p.relative_to(OUT)
    parts = rel.parts
    stage = parts[0] if len(parts) > 0 else ''
    lang = parts[1] if len(parts) > 1 else ''
    stem = p.stem
    pdf = p.with_suffix('.pdf')
    rows.append({
        'stage': stage,
        'language': lang,
        'map_file': stem,
        'png': str(rel),
        'png_bytes': p.stat().st_size,
        'pdf': str(pdf.relative_to(OUT)) if pdf.exists() else '',
        'pdf_bytes': pdf.stat().st_size if pdf.exists() else 0,
        'status': 'OK' if pdf.exists() else 'PDF_MISSING',
    })

with (OUT/'FINAL_MANIFEST.csv').open('w', newline='', encoding='utf-8') as f:
    fields=['stage','language','map_file','png','png_bytes','pdf','pdf_bytes','status']
    w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

summary = {
    'expected_maps_per_language': 27,
    'expected_total_maps': 54,
    'png_count': len(pngs),
    'pdf_count': len(pdfs),
    'complete': (len(pngs) == 54 and len(pdfs) == 54),
    'scientific_guardrails': [
        'No analytical recalculation during packaging',
        'No true delta DEM claim',
        'No defensible delta h from ICESat-2',
        'No pre/post GFI claim',
        'No quantified pre/post hazard-index change claim',
        'Sentinel-1 is surface-state/backscatter-change evidence only',
    ],
}
(OUT/'FINAL_SUMMARY.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')

if ZIP.exists(): ZIP.unlink()
with ZipFile(ZIP, 'w', ZIP_DEFLATED, compresslevel=6) as z:
    for p in sorted(OUT.rglob('*')):
        if p.is_file():
            z.write(p, f'KURANJI_FINAL_54_MAPS_BILINGUAL/{p.relative_to(OUT).as_posix()}')

print(f'ZIP={ZIP}')
print(f'ZIP_BYTES={ZIP.stat().st_size}')
print('FINAL_STATUS=' + ('COMPLETE' if summary['complete'] else 'REVIEW_REQUIRED'))
