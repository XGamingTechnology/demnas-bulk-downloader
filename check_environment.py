#!/usr/bin/env python3
import sys

print("Python:", sys.version.split()[0])

mods = ["requests", "numpy", "shapely", "rasterio"]
failed = False

for name in mods:
    try:
        mod = __import__(name)
        print(f"{name}: OK ({getattr(mod, '__version__', 'unknown version')})")
    except Exception as e:
        failed = True
        print(f"{name}: ERROR - {e}")

if failed:
    raise SystemExit(1)

print("\nEnvironment siap.")
