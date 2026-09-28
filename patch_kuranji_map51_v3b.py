#!/usr/bin/env python3
from pathlib import Path

SRC = Path('render_kuranji_map51_matplotlib_v2.py')
DST = Path('render_kuranji_map51_matplotlib_v3.py')

if not SRC.exists():
    raise SystemExit(f'MISSING_SOURCE={SRC}')

s = SRC.read_text(encoding='utf-8')
repls = []


def replace_once(old, new, label):
    global s
    count = s.count(old)
    if count != 1:
        raise SystemExit(f'PATCH_ABORTED {label} occurrences={count}')
    s = s.replace(old, new, 1)
    repls.append(label)


replace_once(
    'OUT = ROOT / "artifacts/KURANJI_FINAL_PYTHON_MAPS_V2/05_STAGE1"',
    'OUT = ROOT / "artifacts/KURANJI_FINAL_PYTHON_MAPS_V3/05_STAGE1"',
    'output_dir'
)

replace_once(
'''SLUG = {
    "id": "PETA_5_1_LOKASI_DAS_KURANJI_V2",
    "en": "MAP_5_1_BATANG_KURANJI_STUDY_AREA_V2",
}''',
'''SLUG = {
    "id": "PETA_5_1_LOKASI_DAS_KURANJI_V3",
    "en": "MAP_5_1_BATANG_KURANJI_STUDY_AREA_V3",
}''',
    'slug'
)

replace_once(
'''def add_north(ax):
    ax.annotate("N", xy=(0.045,0.91), xytext=(0.045,0.82), xycoords="axes fraction", textcoords="axes fraction",
                ha="center", va="center", fontsize=10, fontweight="bold",
                arrowprops=dict(facecolor="black", edgecolor="black", width=1.8, headwidth=8, headlength=10), zorder=30)
''',
'''def add_north(ax):
    ax.annotate(
        "",
        xy=(0.058, 0.915),
        xytext=(0.058, 0.785),
        xycoords="axes fraction",
        textcoords="axes fraction",
        arrowprops=dict(
            arrowstyle="simple",
            fc="black",
            ec="black",
            mutation_scale=28,
        ),
        zorder=40,
    )
    ax.text(
        0.058, 0.755, "N",
        transform=ax.transAxes,
        ha="center", va="center",
        fontsize=15, fontweight="bold", color="black",
        path_effects=[pe.withStroke(linewidth=3, foreground="white")],
        zorder=41,
    )
''',
    'north_arrow'
)

replace_once(
'''def add_scalebar(ax, extent, lang):
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
''',
'''def add_scalebar(ax, extent, lang):
    xmin, xmax, ymin, ymax = extent
    width = xmax - xmin
    height = ymax - ymin

    length_m = 5000.0
    if length_m > width * 0.18:
        length_m = nice_number(width * 0.12)

    x0 = xmin + width * 0.035
    y0 = ymin + height * 0.055
    bar_h = height * 0.012
    nseg = 4
    seg = length_m / nseg

    for i in range(nseg):
        fc = "black" if i % 2 == 0 else "white"
        ax.add_patch(MplPolygon(
            [
                (x0 + i * seg, y0),
                (x0 + (i + 1) * seg, y0),
                (x0 + (i + 1) * seg, y0 + bar_h),
                (x0 + i * seg, y0 + bar_h),
            ],
            closed=True,
            facecolor=fc,
            edgecolor="black",
            linewidth=0.6,
            zorder=25,
        ))

    ax.add_patch(MplPolygon(
        [
            (x0, y0),
            (x0 + length_m, y0),
            (x0 + length_m, y0 + bar_h),
            (x0, y0 + bar_h),
        ],
        closed=True,
        facecolor="none",
        edgecolor="black",
        linewidth=0.7,
        zorder=26,
    ))

    ax.text(x0, y0 + bar_h * 1.55, "0", fontsize=7.2, ha="center", va="bottom", zorder=27)
    ax.text(x0 + length_m / 2, y0 + bar_h * 1.55, f"{length_m / 2000:g}", fontsize=7.2, ha="center", va="bottom", zorder=27)
    ax.text(x0 + length_m, y0 + bar_h * 1.55, f"{length_m / 1000:g} km", fontsize=7.2, ha="center", va="bottom", zorder=27)
''',
    'scale_bar'
)

# Two identical graticule draw lines exist: longitude and latitude. Patch both together.
old_graticule = '            ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#202020", linewidth=0.45, alpha=0.52, zorder=1)'
new_graticule = '            ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#8e8e8e", linewidth=0.35, alpha=0.45, zorder=1)'
count = s.count(old_graticule)
if count != 2:
    raise SystemExit(f'PATCH_ABORTED graticule occurrences={count}')
s = s.replace(old_graticule, new_graticule)
repls.extend(['graticule_lon', 'graticule_lat'])

replace_once(
'''    # Scale denominator computed from final physical map width.
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
''',
'''    # Scale denominator computed from final physical map width.
    scale_denom = computed_scale_denominator(fig, ax, extent)
    if scale_denom:
        rounded = int(round(scale_denom / 1000.0) * 1000)
        scale_txt = f"{t['scale']} 1 : {rounded:,}"
        if lang == "id":
            scale_txt = scale_txt.replace(",", ".")
        ax.text(
            0.03, 0.078, scale_txt,
            transform=ax.transAxes,
            fontsize=8.4,
            fontweight="bold",
            ha="left",
            va="bottom",
            color="black",
            path_effects=[pe.withStroke(linewidth=2.0, foreground="white")],
            zorder=30,
        )

    # Stronger locator inset: province context + highlighted watershed + local label.
    ax_in = fig.add_axes([0.748, 0.720, 0.185, 0.190])
    ax_in.set_facecolor("white")
    draw_layer(
        ax_in, SRC["sumbar"], 4326,
        facecolor="#efefef", edgecolor="#7a7a7a",
        linewidth=0.42, alpha=1.0, zorder=1,
    )
    draw_layer(
        ax_in, SRC["das"], 4326,
        facecolor="#ff4d4d", edgecolor="#8b0000",
        linewidth=1.1, alpha=0.96, zorder=5,
    )
    style_axes(ax_in, inset_extent)
    ax_in.set_title(t["inset"], fontsize=8.8, fontweight="bold", pad=5)

    for g, _ in base.iter_transformed(SRC["das"], 4326):
        c = g.Centroid()
        if c is not None and not c.IsEmpty():
            cx, cy = c.GetX(), c.GetY()
            ax_in.scatter([cx], [cy], s=22, c="#b30000", edgecolors="white", linewidths=0.7, zorder=7)
            ax_in.text(
                cx, cy - 0.10,
                "DAS Kuranji" if lang == "id" else "Kuranji WS",
                ha="center", va="top",
                fontsize=6.8, fontweight="bold", color="#8b0000",
                path_effects=[pe.withStroke(linewidth=2.0, foreground="white")],
                zorder=8,
            )
            break
''',
    'scale_text_and_inset'
)

replace_once(
    '"renderer": "matplotlib_v2_publication_style",',
    '"renderer": "matplotlib_v3_locator_north_scale",',
    'metadata_renderer'
)

DST.write_text(s, encoding='utf-8')
print('PATCH_V3B=OK')
print('SOURCE=', SRC)
print('OUTPUT=', DST)
for x in repls:
    print('PATCHED=', x)
