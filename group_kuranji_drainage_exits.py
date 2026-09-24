#!/usr/bin/env python3
"""Group thousands of cell-scale D8 exits into meaningful drainage-leakage zones.

The first partition diagnostic intentionally treated every reference-DAS boundary
cell whose D8 pointer exits the polygon as an individual pour point. This is exact
at raster-cell scale but creates thousands of tiny outlet IDs. This script groups
nearby exit cells into spatial zones and sums the reference-DAS area draining to
each zone.

Grouping is evaluated at several radii (25, 50, 100, 250 m) so the interpretation
is not dependent on a single arbitrary clustering distance.

Inputs
------
data/work/kuranji/03_watershed/DAS_D8_EXIT_POINTS.geojson
data/work/kuranji/03_watershed/DAS_D8_PARTITIONS.tif
data/work/kuranji/01_prepared/DAS_KURANJI_UTM47S.geojson

Outputs
-------
data/work/kuranji/03_watershed/drainage_exit_zones.json
data/work/kuranji/03_watershed/DRAINAGE_EXIT_ZONES_100M.geojson
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.spatial import cKDTree
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent
PREP = ROOT / "data/work/kuranji/01_prepared"
OUT = ROOT / "data/work/kuranji/03_watershed"

EXIT_POINTS = OUT / "DAS_D8_EXIT_POINTS.geojson"
PARTITIONS = OUT / "DAS_D8_PARTITIONS.tif"
DAS = PREP / "DAS_KURANJI_UTM47S.geojson"
REPORT = OUT / "drainage_exit_zones.json"
ZONES_100 = OUT / "DRAINAGE_EXIT_ZONES_100M.geojson"

RADII_M = [25.0, 50.0, 100.0, 250.0]
MAJOR_ZONE_KM2 = 0.5


class UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.p[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def load_geojson(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def build_clusters(points_xy: np.ndarray, radius: float):
    tree = cKDTree(points_xy)
    pairs = tree.query_pairs(radius)
    uf = UnionFind(len(points_xy))
    for a, b in pairs:
        uf.union(a, b)
    groups = defaultdict(list)
    for i in range(len(points_xy)):
        groups[uf.find(i)].append(i)
    return list(groups.values())


def main():
    for p in [EXIT_POINTS, PARTITIONS, DAS]:
        if not p.exists():
            raise FileNotFoundError(p)

    exit_fc = load_geojson(EXIT_POINTS)
    das_fc = load_geojson(DAS)
    das_geoms = [shape(ft["geometry"]) for ft in das_fc.get("features", []) if ft.get("geometry")]
    if not das_geoms:
        raise RuntimeError("Reference DAS geometry missing")

    exits = []
    for ft in exit_fc.get("features", []):
        prop = ft.get("properties", {})
        geom = ft.get("geometry") or {}
        coords = geom.get("coordinates")
        if not coords or "outlet_id" not in prop:
            continue
        exits.append({
            "outlet_id": int(prop["outlet_id"]),
            "kind": prop.get("kind", "unknown"),
            "x": float(coords[0]),
            "y": float(coords[1]),
            "distance_to_rbi_m": float(prop.get("distance_to_rbi_m", np.nan)),
            "accum_area_global_km2": float(prop.get("accum_area_global_km2", np.nan)),
        })
    if not exits:
        raise RuntimeError("No exit points found")

    with rasterio.open(PARTITIONS) as pds:
        labels = pds.read(1)
        cell_area = abs(pds.res[0] * pds.res[1])
        das_mask = rasterize(
            [(g, 1) for g in das_geoms],
            out_shape=(pds.height, pds.width),
            transform=pds.transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)

        vals = labels[das_mask]
        if pds.nodata is not None:
            vals = vals[~np.isclose(vals, pds.nodata)]
        vals = vals[np.isfinite(vals)]
        ids, counts = np.unique(vals.astype("int64"), return_counts=True)
        area_by_id = {
            int(oid): float(n * cell_area / 1_000_000.0)
            for oid, n in zip(ids, counts)
            if int(oid) > 0
        }
        ref_area_km2 = float(np.count_nonzero(das_mask) * cell_area / 1_000_000.0)
        crs_text = str(pds.crs)

    xy = np.array([[e["x"], e["y"]] for e in exits], dtype="float64")
    results = {}
    zones_100_features = []

    for radius in RADII_M:
        groups = build_clusters(xy, radius)
        zones = []
        for zone_id, members in enumerate(groups, start=1):
            member_exits = [exits[i] for i in members]
            area = float(sum(area_by_id.get(e["outlet_id"], 0.0) for e in member_exits))
            weights = np.array([max(area_by_id.get(e["outlet_id"], 0.0), 1e-12) for e in member_exits])
            xs = np.array([e["x"] for e in member_exits])
            ys = np.array([e["y"] for e in member_exits])
            cx = float(np.average(xs, weights=weights))
            cy = float(np.average(ys, weights=weights))
            d_rbi_vals = [e["distance_to_rbi_m"] for e in member_exits if np.isfinite(e["distance_to_rbi_m"])]
            max_global_vals = [e["accum_area_global_km2"] for e in member_exits if np.isfinite(e["accum_area_global_km2"])]
            zone = {
                "zone_id": zone_id,
                "exit_cell_count": len(member_exits),
                "reference_das_area_km2": area,
                "percent_reference_das": float(area / ref_area_km2 * 100.0) if ref_area_km2 else 0.0,
                "centroid_x": cx,
                "centroid_y": cy,
                "minimum_distance_to_rbi_m": float(min(d_rbi_vals)) if d_rbi_vals else None,
                "maximum_global_accum_area_km2": float(max(max_global_vals)) if max_global_vals else None,
                "outlet_ids": [e["outlet_id"] for e in member_exits],
            }
            zones.append(zone)

        zones.sort(key=lambda z: z["reference_das_area_km2"], reverse=True)
        for rank, z in enumerate(zones, start=1):
            z["rank"] = rank

        major = [z for z in zones if z["reference_das_area_km2"] >= MAJOR_ZONE_KM2]
        results[f"{int(radius)}m"] = {
            "radius_m": radius,
            "zone_count": len(zones),
            "major_zone_threshold_km2": MAJOR_ZONE_KM2,
            "major_zone_count": len(major),
            "major_zone_area_km2": float(sum(z["reference_das_area_km2"] for z in major)),
            "top_zones": zones[:30],
        }

        if radius == 100.0:
            for z in zones:
                zones_100_features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [z["centroid_x"], z["centroid_y"]],
                    },
                    "properties": {
                        k: v for k, v in z.items()
                        if k not in {"outlet_ids"}
                    },
                })

    report = {
        "reference_das_area_km2": ref_area_km2,
        "raw_exit_cell_count": len(exits),
        "raw_partition_count_with_area": len(area_by_id),
        "grouping_radii_m": RADII_M,
        "major_zone_threshold_km2": MAJOR_ZONE_KM2,
        "grouped_results": results,
        "interpretation_note": (
            "Thousands of raw exit cells are raster-scale boundary leakage points, not thousands of meaningful sub-basins. "
            "Stable major zones that persist across several clustering radii indicate where the DEM-derived drainage disagrees materially with the reference DAS boundary."
        ),
    }
    with REPORT.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    fc = {
        "type": "FeatureCollection",
        "name": "drainage_exit_zones_100m",
        "crs": {"type": "name", "properties": {"name": crs_text}},
        "features": zones_100_features,
    }
    with ZONES_100.open("w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)

    print("=== KURANJI GROUPED DRAINAGE EXIT ZONES ===")
    print(f"Reference DAS area : {ref_area_km2:.3f} km2")
    print(f"Raw exit cells     : {len(exits):,}")
    print(f"Raw partitions     : {len(area_by_id):,}")
    for key in ["25m", "50m", "100m", "250m"]:
        row = results[key]
        print(f"\nGrouping radius {key}:")
        print(f"  zones      : {row['zone_count']:,}")
        print(f"  major >=0.5 km2 : {row['major_zone_count']}")
        print("  top zones:")
        for z in row["top_zones"][:10]:
            print(
                f"    #{z['rank']:>2} area={z['reference_das_area_km2']:>8.3f} km2 "
                f"({z['percent_reference_das']:>6.2f}%) | exits={z['exit_cell_count']:>4} | "
                f"dRBI(min)={z['minimum_distance_to_rbi_m'] if z['minimum_distance_to_rbi_m'] is not None else float('nan'):>7.1f} m"
            )
    print("\nJSON      :", REPORT)
    print("100m zones:", ZONES_100)


if __name__ == "__main__":
    main()
