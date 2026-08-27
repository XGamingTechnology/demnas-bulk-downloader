#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

from shapely import make_valid
from shapely.geometry import box, mapping, shape
from shapely.prepared import prep

from download_demnas import (
    get_province_geometry,
    norm_name,
    save_boundary,
    session_with_retries,
)

RBI = (
    "https://geoservices.big.go.id/rbi/rest/services/"
    "BASEMAP/Rupabumi_Indonesia/MapServer"
)

LAYERS = {
    "garis_pantai": (563, "GARIS_PANTAI"),
    "sungai_garis": (566, "SUNGAI_GARIS"),
    "danau": (594, "DANAU"),
    "sungai_area": (598, "SUNGAI_AREA"),
    "waduk": (600, "WADUK"),
}

DEFAULT_LAYERS = [
    "sungai_garis",
    "sungai_area",
    "waduk",
    "danau",
    "garis_pantai",
]


def request_json(session, url, params, timeout=180):
    r = session.get(url, params=params, timeout=timeout)
    r.raise_for_status()

    data = r.json()

    if "error" in data:
        raise RuntimeError(
            json.dumps(data["error"], ensure_ascii=False)
        )

    return data


def get_ids(session, layer_id, province_geom):
    minx, miny, maxx, maxy = province_geom.bounds

    params = {
        "where": "1=1",
        "geometry": f"{minx},{miny},{maxx},{maxy}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnIdsOnly": "true",
        "f": "json",
    }

    data = request_json(
        session,
        f"{RBI}/{layer_id}/query",
        params,
    )

    return sorted(data.get("objectIds") or [])


def chunks(values, size=500):
    for i in range(0, len(values), size):
        yield values[i:i + size]


def fetch_features(session, layer_id, object_ids):
    params = {
        "objectIds": ",".join(str(x) for x in object_ids),
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "returnZ": "false",
        "returnM": "false",
        "geometryPrecision": "7",
        "f": "geojson",
    }

    data = request_json(
        session,
        f"{RBI}/{layer_id}/query",
        params,
        timeout=240,
    )

    return data.get("features", [])


def download_layer(
    session,
    key,
    province,
    province_geom,
    output_dir,
    overwrite=False,
):
    layer_id, label = LAYERS[key]

    safe = norm_name(province).replace(" ", "_")

    output = output_dir / f"{label}_{safe}.geojson"

    if output.exists() and not overwrite:
        print(f"SKIP: {output.name} sudah ada")
        return

    print()
    print("=" * 60)
    print(f"{label}")
    print(f"Layer BIG : {layer_id}")
    print("=" * 60)

    ids = get_ids(session, layer_id, province_geom)

    print(f"Kandidat bbox : {len(ids):,} feature")

    province_geom = make_valid(province_geom)
    prepared = prep(province_geom)

    tmp = output.with_suffix(".geojson.part")

    written = 0
    first = True

    total_pages = (len(ids) + 499) // 500

    with tmp.open("w", encoding="utf-8") as f:

        f.write(
            '{"type":"FeatureCollection","features":[\n'
        )

        for page, ids_chunk in enumerate(
            chunks(ids, 500),
            start=1,
        ):

            features = fetch_features(
                session,
                layer_id,
                ids_chunk,
            )

            for feature in features:

                geometry = feature.get("geometry")

                if not geometry:
                    continue

                geom = shape(geometry)

                if geom.is_empty:
                    continue

                if not geom.is_valid:
                    geom = make_valid(geom)

                if not prepared.intersects(geom):
                    continue

                if prepared.contains(geom):
                    clipped = geom
                else:
                    clipped = geom.intersection(
                        province_geom
                    )

                if clipped.is_empty:
                    continue

                properties = dict(
                    feature.get("properties") or {}
                )

                properties["SRC_BIG_LAYER"] = layer_id

                result = {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": mapping(clipped),
                }

                if not first:
                    f.write(",\n")

                json.dump(
                    result,
                    f,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )

                first = False
                written += 1

            print(
                f"[{page}/{total_pages}] "
                f"tersimpan {written:,} feature"
            )

        f.write("\n]}\n")

    tmp.replace(output)

    print(
        f"SELESAI: {written:,} feature -> {output}"
    )


def parse_layers(value):
    if value.lower() == "all":
        return DEFAULT_LAYERS

    result = []

    for item in value.split(","):
        key = item.strip().lower()

        if key not in LAYERS:
            raise ValueError(
                f"Layer tidak dikenal: {key}. "
                f"Pilihan: {', '.join(LAYERS)}, all"
            )

        result.append(key)

    return result


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Download hidrografi RBI BIG "
            "berdasarkan batas provinsi."
        )
    )

    parser.add_argument(
        "--province",
        default="Jawa Timur",
    )

    parser.add_argument(
        "--workdir",
        default="data",
    )

    parser.add_argument(
        "--layers",
        default="all",
        help=(
            "all atau daftar: "
            "sungai_garis,sungai_area,"
            "waduk,danau,garis_pantai"
        ),
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
    )

    args = parser.parse_args()

    selected = parse_layers(args.layers)

    workdir = Path(args.workdir)

    output_dir = (
        workdir /
        "output" /
        "hydro"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    session = session_with_retries()

    print(
        f"Mengambil batas provinsi: "
        f"{args.province}"
    )

    province_geom = get_province_geometry(
        session,
        args.province,
    )

    boundary_dir = workdir / "output"

    boundary_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    save_boundary(
        province_geom,
        args.province,
        boundary_dir,
    )

    print()
    print("=== RBI BIG HYDRO DOWNLOADER ===")
    print("Provinsi :", args.province)
    print("CRS      : EPSG:4326")
    print(
        "Layers   :",
        ", ".join(selected),
    )

    for key in selected:

        download_layer(
            session,
            key,
            args.province,
            province_geom,
            output_dir,
            overwrite=args.overwrite,
        )

    print()
    print("SEMUA SELESAI")
    print(
        "Output:",
        output_dir.resolve(),
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDihentikan user.")
