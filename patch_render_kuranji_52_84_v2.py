#!/usr/bin/env python3
from pathlib import Path

SRC = Path('render_kuranji_maps_52_84_matplotlib.py')
if not SRC.exists():
    raise SystemExit(f'MISSING_SOURCE={SRC}')

s = SRC.read_text(encoding='utf-8')

old = '        im,hs=plot_layer(ax,spec); last_im=im if im is not None else last_im; legends+=hs'
new = '        im,hs=plot_layer(ax,spec); last_im=im if im is not None else last_im; legends += (hs or [])'
if s.count(old) != 1:
    raise SystemExit(f'PATCH_ABORTED legend_handling occurrences={s.count(old)}')
s = s.replace(old, new, 1)
print('PATCHED=legend_handling_none_safe')

old = '        cmap=LinearSegmentedColormap.from_list("qml",[(v,c) for v,c,_ in entries])'
new = '        cmap=LinearSegmentedColormap.from_list("qml", cols)'
if s.count(old) != 1:
    raise SystemExit(f'PATCH_ABORTED qml_continuous_colormap occurrences={s.count(old)}')
s = s.replace(old, new, 1)
print('PATCHED=qml_continuous_colormap_normalized')

SRC.write_text(s, encoding='utf-8')
print('PATCH_RENDER_52_84_V2=OK')
