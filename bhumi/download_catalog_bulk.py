#!/usr/bin/env python3
"""
Bulk-download BHUMI catalog layers that are available through public services.

The runner reuses the adapters in download_public_layer.py and records every
attempt in a JSON manifest so interrupted runs can be resumed.

It does not authenticate, bypass access controls, reuse cookies/tokens, or
attempt protected BHUMI application-wrapper feature endpoints.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import download_public_layer as dpl


def slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "_", value)
    return value.strip("._-") or "layer"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "layers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"version": 1, "layers": {}}
    if not isinstance(data, dict):
        return {"version": 1, "layers": {}}
    data.setdefault("version", 1)
    data.setdefault("layers", {})
    return data


def save_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest["updated_at"] = now_iso()
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def result_entry(row: dict, category: str, status: str, **extra) -> dict:
    return {
        "id": str(row.get("id") or ""),
        "name": row.get("name"),
        "category": category,
        "vendor": row.get("map_service_vendor"),
        "service_url": row.get("map_service_url"),
        "service_layer": row.get("map_service_layer_name"),
        "status": status,
        "updated_at": now_iso(),
        **extra,
    }


def arcgis_leaf_layers(meta: dict) -> list[dict]:
    leaves = []
    for layer in meta.get("layers") or []:
        children = layer.get("subLayerIds")
        if children in (None, [], ()):
            leaves.append(layer)
    return leaves


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Download all publicly downloadable BHUMI catalog layers."
    )
    ap.add_argument(
        "--bbox",
        type=dpl.parse_bbox,
        required=True,
        help="AOI minLon,minLat,maxLon,maxLat.",
    )
    ap.add_argument("--zoom", type=int, default=12)
    ap.add_argument("--output-dir", default="output/bhumi_bulk")
    ap.add_argument("--manifest")
    ap.add_argument("--timeout", type=int, default=dpl.DEFAULT_TIMEOUT)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--max-tiles", type=int, default=500)
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument("--persil-cols", type=int, default=4)
    ap.add_argument("--persil-rows", type=int, default=3)
    ap.add_argument("--max-arcgis-layers", type=int, default=50)
    ap.add_argument(
        "--only",
        action="append",
        default=[],
        help="Only process category (repeatable).",
    )
    ap.add_argument(
        "--name-contains",
        default="",
        help="Only process catalog names containing this text.",
    )
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    outdir = Path(args.output_dir)
    manifest_path = Path(args.manifest or (outdir / "manifest.json"))
    manifest = load_manifest(manifest_path)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; demnas-bulk-downloader/1.0)",
        "Referer": f"{dpl.BASE}/peta",
        "Accept": "*/*",
    })

    try:
        rows = dpl.fetch_catalog(session, args.timeout)
    except (requests.RequestException, ValueError) as exc:
        print(f"ERROR catalog: {exc}", file=sys.stderr)
        return 2

    print(f"Catalog layers: {len(rows)}")
    print(f"AOI: {','.join(str(x) for x in args.bbox)}")
    print(f"Output: {outdir}")
    print(f"Manifest: {manifest_path}")

    processed = 0
    success = 0
    skipped = 0
    failed = 0

    for index, row in enumerate(rows, start=1):
        name = str(row.get("name") or f"layer_{index}")
        category = dpl.classify(row)
        layer_id = str(row.get("id") or name)

        if args.only and category not in set(args.only):
            continue
        if args.name_contains and args.name_contains.lower() not in name.lower():
            continue

        previous = manifest["layers"].get(layer_id)
        if (
            previous
            and previous.get("status") in {"downloaded", "metadata-downloaded"}
            and not args.force
        ):
            print(f"[{index}/{len(rows)}] SKIP completed: {name}")
            skipped += 1
            continue

        processed += 1
        layer_dir = outdir / f"{index:02d}_{slug(name)}"
        print()
        print(f"[{index}/{len(rows)}] {name}")
        print(f"  category={category}")

        if args.dry_run:
            manifest["layers"][layer_id] = result_entry(
                row, category, "planned", output=str(layer_dir)
            )
            save_manifest(manifest_path, manifest)
            continue

        try:
            if category == "bhumi-persil-wms":
                output = layer_dir / "persil.tif"
                dpl.persil_wms_download(
                    session,
                    args.bbox,
                    output,
                    args.timeout,
                    args.width,
                    args.height,
                    cols=args.persil_cols,
                    rows=args.persil_rows,
                    delay=args.delay,
                    max_tiles=args.max_tiles,
                    workdir=layer_dir / ".tiles",
                    keep_tiles=False,
                )
                manifest["layers"][layer_id] = result_entry(
                    row, category, "downloaded",
                    format="GeoTIFF",
                    output=str(output),
                    note="Raster WMS render; not vector/NIB.",
                )
                success += 1

            elif category == "xyz":
                output = layer_dir / "xyz"
                dpl.xyz_download(
                    session, row, args.bbox, args.zoom, output,
                    args.timeout, args.delay, args.max_tiles,
                )
                manifest["layers"][layer_id] = result_entry(
                    row, category, "downloaded",
                    format="XYZ tiles",
                    output=str(output),
                    zoom=args.zoom,
                )
                success += 1

            elif category in {"ogc", "geoserver"}:
                output = layer_dir / "layer.geojson"
                dpl.wfs_download(
                    session, row, args.bbox, output, args.timeout
                )
                manifest["layers"][layer_id] = result_entry(
                    row, category, "downloaded",
                    format="GeoJSON",
                    output=str(output),
                )
                success += 1

            elif category == "wms":
                # Prefer vector WFS when the same service exposes it. If not,
                # preserve the public rendered layer as an image.
                vector_output = layer_dir / "layer.geojson"
                try:
                    dpl.wfs_download(
                        session, row, args.bbox, vector_output, args.timeout
                    )
                    manifest["layers"][layer_id] = result_entry(
                        row, category, "downloaded",
                        format="GeoJSON",
                        output=str(vector_output),
                        note="WFS vector route available.",
                    )
                except (requests.RequestException, ValueError, RuntimeError) as wfs_exc:
                    raster_output = layer_dir / "layer.png"
                    dpl.wms_download(
                        session, row, args.bbox, raster_output,
                        args.timeout, args.width, args.height,
                    )
                    manifest["layers"][layer_id] = result_entry(
                        row, category, "downloaded",
                        format="PNG",
                        output=str(raster_output),
                        note=f"WFS unavailable; WMS raster used: {wfs_exc}",
                    )
                success += 1

            elif category == "arcgis":
                meta = dpl.arcgis_probe(session, row, args.timeout, None)
                leaves = arcgis_leaf_layers(meta)
                if not leaves:
                    raise RuntimeError("ArcGIS service has no downloadable leaf sublayers.")

                outputs = []
                errors = []
                for layer in leaves[: args.max_arcgis_layers]:
                    sid = int(layer["id"])
                    lname = str(layer.get("name") or f"layer_{sid}")
                    output = layer_dir / f"{sid:03d}_{slug(lname)}.geojson"
                    try:
                        dpl.arcgis_download_geojson(
                            session, row, sid, args.bbox, output,
                            args.timeout, args.delay,
                        )
                        outputs.append(str(output))
                    except (requests.RequestException, ValueError, RuntimeError) as exc:
                        errors.append({"layer_id": sid, "name": lname, "error": str(exc)})

                if outputs:
                    manifest["layers"][layer_id] = result_entry(
                        row, category, "downloaded",
                        format="GeoJSON",
                        outputs=outputs,
                        sublayer_errors=errors,
                    )
                    success += 1
                else:
                    raise RuntimeError(
                        "No ArcGIS sublayer could be downloaded. "
                        + json.dumps(errors[:5], ensure_ascii=False)
                    )

            elif category == "3d-tiles":
                output = layer_dir / "tileset.json"
                dpl.fetch_metadata(session, row, output, args.timeout)
                manifest["layers"][layer_id] = result_entry(
                    row, category, "metadata-downloaded",
                    format="3D Tiles tileset JSON",
                    output=str(output),
                    note="Root metadata saved; recursive asset download is a later adapter.",
                )
                success += 1

            elif category == "terrain":
                output = layer_dir / "tiles.json"
                dpl.fetch_metadata(session, row, output, args.timeout)
                manifest["layers"][layer_id] = result_entry(
                    row, category, "metadata-downloaded",
                    format="Terrain TileJSON",
                    output=str(output),
                    note="TileJSON saved; terrain tile bulk adapter pending.",
                )
                success += 1

            elif category == "bhumi-wrapper":
                manifest["layers"][layer_id] = result_entry(
                    row, category, "skipped-restricted",
                    reason="BHUMI application wrapper; no public bulk feature adapter.",
                )
                print("  SKIP: BHUMI application wrapper")
                skipped += 1

            else:
                manifest["layers"][layer_id] = result_entry(
                    row, category, "skipped-unsupported",
                    reason="No public download adapter yet.",
                )
                print(f"  SKIP: unsupported category={category}")
                skipped += 1

        except (requests.RequestException, ValueError, RuntimeError, OSError) as exc:
            failed += 1
            manifest["layers"][layer_id] = result_entry(
                row, category, "failed", error=str(exc)
            )
            print(f"  FAILED: {exc}", file=sys.stderr)

        save_manifest(manifest_path, manifest)

        if args.delay > 0:
            time.sleep(args.delay)

    print()
    print("=== BULK SUMMARY ===")
    print(f"processed={processed}")
    print(f"success={success}")
    print(f"skipped={skipped}")
    print(f"failed={failed}")
    print(f"manifest={manifest_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
