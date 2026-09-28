#!/usr/bin/env python3
from pathlib import Path
import re

SRC = Path('render_kuranji_map51_matplotlib_v3.py')
DST = Path('render_kuranji_map51_matplotlib_v4.py')

if not SRC.exists():
    raise SystemExit(f'MISSING_SOURCE={SRC}')

s = SRC.read_text(encoding='utf-8')


def sub_once(pattern, replacement, label, flags=0):
    global s
    new_s, n = re.subn(pattern, replacement, s, count=1, flags=flags)
    if n != 1:
        raise SystemExit(f'PATCH_ABORTED {label} matches={n}')
    s = new_s
    print(f'PATCHED={label}')

# Dedicated V4 output paths and names.
sub_once(
    r'OUT = ROOT / "artifacts/KURANJI_FINAL_PYTHON_MAPS_V3/05_STAGE1"',
    'OUT = ROOT / "artifacts/KURANJI_FINAL_PYTHON_MAPS_V4/05_STAGE1"',
    'output_dir'
)
sub_once(
    r'"id": "PETA_5_1_LOKASI_DAS_KURANJI_V3",\s*\n\s*"en": "MAP_5_1_BATANG_KURANJI_STUDY_AREA_V3",',
    '"id": "PETA_5_1_LOKASI_DAS_KURANJI_V4",\n    "en": "MAP_5_1_BATANG_KURANJI_STUDY_AREA_V4",',
    'slug'
)

# Give the Sumatera Barat locator more breathing room than V3.
sub_once(
    r'inset_extent = base\.extent_from_layer\(SRC\["sumbar"\], 4326, margin=0\.025\)',
    'inset_extent = base.extent_from_layer(SRC["sumbar"], 4326, margin=0.10)',
    'inset_extent_margin'
)

# Replace the complete V3 locator block up to the legend comment.
locator_pattern = r'''    # Stronger locator inset: province context \+ highlighted watershed \+ local label\.\n.*?\n    # Legend\n'''
locator_replacement = '''    # V4 locator inset: larger regional frame, labelled graticule, clear watershed locator.\n    ax_in = fig.add_axes([0.700, 0.690, 0.275, 0.220])\n    ax_in.set_facecolor("#f5f8fa")\n\n    draw_layer(\n        ax_in, SRC["sumbar"], 4326,\n        facecolor="#eeeeee", edgecolor="#676767",\n        linewidth=0.45, alpha=1.0, zorder=2,\n    )\n    draw_layer(\n        ax_in, SRC["das"], 4326,\n        facecolor="#e53935", edgecolor="#8b0000",\n        linewidth=1.15, alpha=0.92, zorder=6,\n    )\n\n    style_axes(ax_in, inset_extent)\n\n    # Geographic graticule and coordinate labels, similar to the user's reference map.\n    ixmin, ixmax, iymin, iymax = inset_extent\n    xstep = nice_degree_step(ixmax - ixmin)\n    ystep = nice_degree_step(iymax - iymin)\n\n    def tick_values(vmin, vmax, step):\n        vals = []\n        v = math.ceil(vmin / step) * step\n        while v <= vmax + 1e-9:\n            vals.append(round(v, 10))\n            v += step\n        return vals\n\n    ixticks = tick_values(ixmin, ixmax, xstep)\n    iyticks = tick_values(iymin, iymax, ystep)\n    ax_in.set_xticks(ixticks)\n    ax_in.set_yticks(iyticks)\n    ax_in.set_xticklabels([f"{x:.2f}°E" for x in ixticks], fontsize=5.6)\n    ax_in.set_yticklabels([f"{abs(y):.2f}°{'S' if y < 0 else 'N'}" for y in iyticks], fontsize=5.6)\n    ax_in.tick_params(\n        axis="x", top=True, labeltop=True, bottom=False, labelbottom=False,\n        direction="in", length=2.2, pad=1.5,\n    )\n    ax_in.tick_params(\n        axis="y", left=True, labelleft=True, right=True, labelright=False,\n        direction="in", length=2.2, pad=1.5,\n    )\n    ax_in.grid(True, color="#6f6f6f", linewidth=0.35, alpha=0.55, zorder=1)\n\n    # Strong locator symbol and concise label.\n    for g, _ in base.iter_transformed(SRC["das"], 4326):\n        c = g.Centroid()\n        if c is not None and not c.IsEmpty():\n            cx, cy = c.GetX(), c.GetY()\n            ax_in.scatter(\n                [cx], [cy], s=32, marker="o", c="#b00020",\n                edgecolors="white", linewidths=0.9, zorder=8,\n            )\n            ax_in.annotate(\n                "DAS KURANJI" if lang == "id" else "KURANJI WATERSHED",\n                xy=(cx, cy),\n                xytext=(cx + (ixmax-ixmin)*0.055, cy - (iymax-iymin)*0.035),\n                fontsize=6.7, fontweight="bold", color="#a40018",\n                ha="left", va="top", zorder=9,\n                arrowprops=dict(arrowstyle="-", lw=0.75, color="#a40018"),\n                path_effects=[pe.withStroke(linewidth=1.8, foreground="white")],\n            )\n            break\n\n    ax_in.set_title(t["inset"], fontsize=9.2, fontweight="bold", pad=6)\n\n    # Legend\n'''
sub_once(locator_pattern, locator_replacement, 'locator_inset', flags=re.S)

# Improve the north arrow proportions slightly without changing map content.
sub_once(
    r'mutation_scale=28,',
    'mutation_scale=32,',
    'north_arrow_size'
)
sub_once(
    r'fontsize=15, fontweight="bold", color="black",',
    'fontsize=16, fontweight="bold", color="black",',
    'north_label_size'
)

# Make the numeric scale statement clearer and give it more separation from the bar.
sub_once(
    r'0\.03, 0\.078, scale_txt,',
    '0.03, 0.082, scale_txt,',
    'scale_text_position'
)
sub_once(
    r'fontsize=8\.4,',
    'fontsize=8.8,',
    'scale_text_size'
)

sub_once(
    r'"renderer": "matplotlib_v3_locator_north_scale",',
    '"renderer": "matplotlib_v4_large_locator_graticule",',
    'metadata_renderer'
)

DST.write_text(s, encoding='utf-8')
print('PATCH_V4=OK')
print(f'SOURCE={SRC}')
print(f'OUTPUT={DST}')
