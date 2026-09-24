#!/usr/bin/env python3
import json
from pathlib import Path

import requests

from download_demnas import DEMNAS_SERVICE, session_with_retries

AOI_GEOJSON = Path("data/input/kuranji/DAS_KURANJI_WGS84.geojson")
INDEX_LAYER = (
    "https://geoservices.big.go.id/rbi/rest/services/"
    "INDEKS/DEM_Nasional/MapServer/0"
)


def load_bounds():
    with AOI_GEOJSON.open(encoding="utf-8") as f:
        data = json.load(f)

    xs, ys = [], []

    def walk(coords):
        if not isinstance(coords, (list, tuple)):
            return
        if (
            len(coords) >= 2
            and isinstance(coords[0], (int, float))
            and isinstance(coords[1], (int, float))
        ):
            xs.append(float(coords[0]))
            ys.append(float(coords[1]))
            return
        for item in coords:
            walk(item)

    for feat in data.get("features", []):
        geom = feat.get("geometry") or {}
        walk(geom.get("coordinates"))

    if not xs:
        raise RuntimeError("AOI tidak mempunyai koordinat valid")

    return min(xs), min(ys), max(xs), max(ys)


def get_json(session, url, params, timeout=180):
    r = session.get(url, params=params, timeout=timeout)
    print("GET:", r.url)
    print("HTTP:", r.status_code)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        print("BODY:", r.text[:2000])
        raise


def main():
    session = session_with_retries()
    xmin, ymin, xmax, ymax = load_bounds()
    bbox = f"{xmin},{ymin},{xmax},{ymax}"

    print("=" * 78)
    print("AOI DAS KURANJI")
    print("=" * 78)
    print("bbox:", bbox)

    print("\n" + "=" * 78)
    print("1) QUERY PRIMARY RASTERS FROM DEMNAS IMAGESERVER")
    print("=" * 78)

    query_params = {
        "where": "Category=1",
        "geometry": bbox,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "OBJECTID,Name,Category,MinPS,MaxPS,LowPS,HighPS,CenterX,CenterY",
        "returnGeometry": "false",
        "f": "json",
    }

    cat = get_json(
        session,
        f"{DEMNAS_SERVICE}/query",
        query_params,
    )

    features = cat.get("features") or []
    print("Primary raster count:", len(features))

    ids = []
    for feat in features:
        a = feat.get("attributes") or {}
        print(json.dumps(a, ensure_ascii=False))
        oid = a.get("OBJECTID")
        if oid is not None:
            ids.append(int(oid))

    print("Raster IDs:", ids)

    print("\n" + "=" * 78)
    print("2) QUERY OFFICIAL DEMNAS INDEX MAPSERVER")
    print("=" * 78)

    idx_params = {
        "where": "1=1",
        "geometry": bbox,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "OBJECTID,NAMOBJ,REGION,SENSOR,SKALA,TAHUN,NAMA_PETA",
        "returnGeometry": "false",
        "f": "json",
    }

    idx = get_json(
        session,
        f"{INDEX_LAYER}/query",
        idx_params,
    )

    idx_features = idx.get("features") or []
    print("Index tile count:", len(idx_features))

    for feat in idx_features:
        print(json.dumps(feat.get("attributes") or {}, ensure_ascii=False))

    print("\n" + "=" * 78)
    print("3) TEST IMAGESERVER RAW /download")
    print("=" * 78)

    if not ids:
        print("Tidak ada primary raster ID, raw download tidak dites.")
        return

    dl_params = {
        "rasterIds": ",".join(map(str, ids[:20])),
        "f": "json",
    }

    try:
        dl = get_json(
            session,
            f"{DEMNAS_SERVICE}/download",
            dl_params,
            timeout=300,
        )
        print(json.dumps(dl, indent=2, ensure_ascii=False)[:10000])
    except requests.HTTPError as exc:
        print("RAW DOWNLOAD HTTP ERROR:", repr(exc))
    except Exception as exc:
        print("RAW DOWNLOAD ERROR:", repr(exc))

    print("\n" + "=" * 78)
    print("4) TEST FIRST PRIMARY RASTER ITEM METADATA")
    print("=" * 78)

    first_id = ids[0]
    try:
        item = get_json(
            session,
            f"{DEMNAS_SERVICE}/{first_id}",
            {"f": "json"},
        )
        print(json.dumps(item, indent=2, ensure_ascii=False)[:10000])
    except Exception as exc:
        print("ITEM METADATA ERROR:", repr(exc))


if __name__ == "__main__":
    main()
