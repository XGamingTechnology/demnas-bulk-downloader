"""Optional, coarse terrain sampling from a local DEMNAS GeoTIFF.

These statistics are exploratory: cells are resampled and clipped on a
limited grid; they are NOT native-resolution zonal statistics and must not
be used as a terrain suitability assessment.
"""
from __future__ import annotations

import math
from pathlib import Path


def summarize_dem(features: list[dict], dem_path: str, max_grid: int = 256) -> list[dict]:
    import numpy as np
    import rasterio
    from affine import Affine
    from rasterio.enums import Resampling
    from rasterio.features import geometry_mask
    from rasterio.warp import transform_geom
    from rasterio.windows import Window, from_bounds, transform as window_transform
    from shapely.geometry import shape

    if max_grid < 16 or max_grid > 2048:
        raise ValueError("max_grid harus antara 16 dan 2048")

    output = []
    with rasterio.open(Path(dem_path)) as src:
        if src.crs is None:
            raise ValueError("DEM tidak memiliki CRS")
        if src.count < 1:
            raise ValueError("DEM tidak memiliki band raster")

        for feature in features:
            props = feature.get("properties") or {}
            item = {
                "provinsi": props.get("NAME_1"),
                "kode": props.get("KODE"),
                "wilayah": props.get("Wilayah"),
                "status": None,
                "sample_pixels": 0,
                "valid_fraction": None,
                "elevation_min_m_approx": None,
                "elevation_mean_m_approx": None,
                "elevation_max_m_approx": None,
            }
            try:
                geometry = feature.get("geometry")
                if not geometry:
                    item["status"] = "missing_geometry"
                    output.append(item)
                    continue

                if src.crs.to_epsg() != 4326:
                    geometry = transform_geom("EPSG:4326", src.crs, geometry)

                polygon = shape(geometry)
                if polygon.is_empty:
                    item["status"] = "empty_geometry"
                    output.append(item)
                    continue
                if not polygon.is_valid:
                    item["status"] = "invalid_geometry"
                    output.append(item)
                    continue

                w = from_bounds(*polygon.bounds, transform=src.transform)
                left = max(0, math.floor(w.col_off))
                top = max(0, math.floor(w.row_off))
                right = min(src.width, math.ceil(w.col_off + w.width))
                bottom = min(src.height, math.ceil(w.row_off + w.height))
                if right <= left or bottom <= top:
                    item["status"] = "outside_dem"
                    output.append(item)
                    continue

                win = Window(left, top, right-left, bottom-top)
                width = min(max_grid, int(win.width))
                height = min(max_grid, int(win.height))
                data = src.read(
                    1, window=win, out_shape=(height, width),
                    masked=True, resampling=Resampling.average,
                )
                sample_transform = window_transform(win, src.transform) * Affine.scale(
                    win.width / width, win.height / height
                )
                interior = geometry_mask(
                    [geometry], out_shape=(height, width),
                    transform=sample_transform, invert=True,
                )
                item["sample_pixels"] = int(interior.sum())
                if not item["sample_pixels"]:
                    item["status"] = "no_sampled_cells"
                    output.append(item)
                    continue

                valid = interior & ~np.ma.getmaskarray(data)
                values = np.asarray(data.data[valid], dtype="float64")
                values = values[np.isfinite(values)]
                item["valid_fraction"] = round(len(values) / item["sample_pixels"], 4)
                if not len(values):
                    item["status"] = "no_valid_dem"
                    output.append(item)
                    continue

                item["status"] = "sampled_approx"
                item["elevation_min_m_approx"] = round(float(values.min()), 2)
                item["elevation_mean_m_approx"] = round(float(values.mean()), 2)
                item["elevation_max_m_approx"] = round(float(values.max()), 2)
            except Exception as exc:
                item["status"] = f"error:{type(exc).__name__}"
                item["error_detail"] = str(exc)
            output.append(item)
    return output
