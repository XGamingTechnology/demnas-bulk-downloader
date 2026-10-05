#!/usr/bin/env python3
"""
Download/probe published BHUMI catalog layers by service type.

Supported public-source strategies:
- ArcGIS MapServer: inspect metadata and download vector sublayers as GeoJSON.
- OGC/GeoServer: probe WMS/WFS; download WFS GeoJSON when available.
- WMS: probe capabilities and download a rendered PNG for a BBOX.
- XYZ tiles: download requested AOI/zoom tiles to z/x/y folders.
- 3D Tiles: fetch tileset.json metadata.
- Terrain/TileJSON: fetch tiles metadata.

BHUMI application wrappers such as /bhumigs/umum are deliberately not treated
as open bulk-download endpoints here.

Examples:
  python3 bhumi/download_public_layer.py --name "Index Peta Dasar" --probe

  python3 bhumi/download_public_layer.py \
    --name "Index Peta Dasar" --download \
    --bbox 104.08,-3.51,104.44,-3.32 --zoom 12 \
    --output output/index_peta_dasar

  python3 bhumi/download_public_layer.py \
    --name "Rencana Tata Ruang Wilayah Nasional" --probe

  python3 bhumi/download_public_layer.py \
    --name "Rencana Tata Ruang Wilayah Nasional" --download \
    --arcgis-layer-id 0 --bbox 104.08,-3.51,104.44,-3.32 \
    --output output/rtrwn_layer0.geojson
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import mimetypes
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import requests


BASE = "https://bhumi.atrbpn.go.id"
CATALOG_URL = f"{BASE}/panel/items/layers"
DEFAULT_TIMEOUT = 60


def fetch_catalog(session: requests.Session, timeout: int) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, 30):
        r = session.get(
            CATALOG_URL,
            params={
                "filter[status][_eq]": "published",
                "limit": 100,
                "page": page,
            },
            timeout=timeout,
        )
        r.raise_for_status()
        payload = r.json()
        batch = payload.get("data", []) if isinstance(payload, dict) else []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 100:
            break
    return rows


def find_layer(rows: list[dict], name: str | None, layer_id: str | None) -> dict:
    if layer_id:
        hits = [r for r in rows if str(r.get("id")) == layer_id]
    else:
        needle = (name or "").strip().lower()
        exact = [r for r in rows if str(r.get("name") or "").strip().lower() == needle]
        hits = exact or [
            r for r in rows
            if needle in str(r.get("name") or "").lower()
        ]

    if not hits:
        raise RuntimeError("Layer katalog tidak ditemukan.")
    if len(hits) > 1:
        names = "\n".join(
            f"  {r.get('id')} | {r.get('name')}" for r in hits[:20]
        )
        raise RuntimeError(
            "Nama layer ambigu. Gunakan --id salah satu record berikut:\n" + names
        )
    return hits[0]


def classify(row: dict) -> str:
    vendor = str(row.get("map_service_vendor") or "").strip().lower()
    url = str(row.get("map_service_url") or "").strip()
    url_l = url.lower()

    if vendor == "arcgis":
        return "arcgis"
    if vendor in {"3d tile", "3d tiles"}:
        return "3d-tiles"
    if vendor == "terrain":
        return "terrain"
    if "{x}" in url and "{y}" in url and "{z}" in url:
        return "xyz"
    if vendor == "geoserver":
        if url.startswith("/bhumigs/"):
            return "bhumi-wrapper"
        if "/wms/" in url_l or url_l.endswith("/wms"):
            return "wms"
        if "/ows" in url_l or "/geoserver" in url_l:
            return "ogc"
        return "geoserver"
    return "unknown"


def resolve_url(url: str) -> str:
    if url.startswith("/"):
        return BASE + url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return BASE + "/" + url.lstrip("/")


def print_layer(row: dict) -> None:
    print(f"name: {row.get('name')}")
    print(f"id: {row.get('id')}")
    print(f"vendor: {row.get('map_service_vendor')}")
    print(f"category: {classify(row)}")
    print(f"service_url: {row.get('map_service_url')}")
    print(f"resolved_url: {resolve_url(str(row.get('map_service_url') or ''))}")
    print(f"service_layer: {row.get('map_service_layer_name')}")
    print(f"type: {row.get('type')}")
    print(f"sw_bound: {row.get('sw_bound')}")
    print(f"ne_bound: {row.get('ne_bound')}")


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    try:
        vals = tuple(float(x.strip()) for x in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "BBOX harus minLon,minLat,maxLon,maxLat"
        ) from exc
    if len(vals) != 4:
        raise argparse.ArgumentTypeError("BBOX harus empat angka.")
    minx, miny, maxx, maxy = vals
    if minx >= maxx or miny >= maxy:
        raise argparse.ArgumentTypeError("BBOX tidak valid.")
    return minx, miny, maxx, maxy


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def arcgis_parts(url: str) -> tuple[str | None, str]:
    """
    Return (proxy_prefix, MapServer root).

    Direct:
      https://host/.../MapServer
    Proxy:
      https://host/run.ashx?https://target/.../MapServer?f=pjson
    """
    if "run.ashx?" in url:
        prefix, target = url.split("run.ashx?", 1)
        proxy_prefix = prefix + "run.ashx?"
        target = target.split("?f=", 1)[0].rstrip("/")
        if target.endswith("/export"):
            target = target[:-7]
        return proxy_prefix, target

    root = url.split("?", 1)[0].rstrip("/")
    if root.endswith("/export"):
        root = root[:-7]
    return None, root


def arcgis_candidates(row: dict) -> list[tuple[str | None, str, str]]:
    """Return evidence-based ArcGIS access routes to try."""
    raw = resolve_url(str(row.get("map_service_url") or ""))
    candidates: list[tuple[str | None, str, str]] = []

    proxy_prefix, root = arcgis_parts(raw)
    candidates.append((proxy_prefix, root, "catalog"))

    # Several GISTARU catalog records themselves use proxy_geokkp/run.ashx
    # for ArcGIS REST. If a direct GISTARU MapServer returns HTML instead of
    # REST JSON, try that same public proxy pattern.
    parsed = urlsplit(root)
    if (
        proxy_prefix is None
        and parsed.netloc.lower() == "gistaru.atrbpn.go.id"
        and "/arcgis/rest/services/" in parsed.path
    ):
        candidates.append((
            "https://gistaru.atrbpn.go.id/proxy_geokkp/run.ashx?",
            root,
            "gistaru-proxy",
        ))

    # Deduplicate while preserving order.
    seen = set()
    unique = []
    for item in candidates:
        key = (item[0], item[1])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def arcgis_json(
    session: requests.Session,
    proxy_prefix: str | None,
    root: str,
    suffix: str,
    params: dict,
    timeout: int,
) -> tuple[dict | None, requests.Response]:
    url = arcgis_url(proxy_prefix, root, suffix, params)
    r = session.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "").lower()
    prefix = r.content[:500].lstrip().lower()

    if "html" in ctype or prefix.startswith(b"<!doctype html") or b"<html" in prefix:
        return None, r

    try:
        data = r.json()
    except ValueError:
        return None, r

    return data if isinstance(data, dict) else None, r


def is_arcgis_service_metadata(data: dict | None) -> bool:
    if not isinstance(data, dict) or not data or data.get("error"):
        return False
    # ArcGIS REST MapServer service metadata normally exposes currentVersion
    # plus one or more service-level fields. Do not accept arbitrary JSON as
    # a valid MapServer response.
    if "currentVersion" not in data:
        return False
    service_keys = {
        "layers", "tables", "mapName", "serviceDescription",
        "description", "fullExtent", "initialExtent",
        "supportedQueryFormats", "capabilities",
    }
    return any(key in data for key in service_keys)


def choose_arcgis_route(
    session: requests.Session,
    row: dict,
    timeout: int,
) -> tuple[str | None, str, str, dict]:
    errors = []
    for proxy_prefix, root, label in arcgis_candidates(row):
        try:
            data, r = arcgis_json(
                session, proxy_prefix, root, "", {"f": "pjson"}, timeout
            )
        except requests.RequestException as exc:
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
            continue

        if is_arcgis_service_metadata(data):
            return proxy_prefix, root, label, data

        if data is not None:
            if isinstance(data.get("error"), dict):
                err = data["error"]
                errors.append(
                    f"{label}: ArcGIS error "
                    f"code={err.get('code')} "
                    f"message={err.get('message')} "
                    f"details={err.get('details')}"
                )
            else:
                errors.append(
                    f"{label}: JSON diterima tetapi bukan metadata ArcGIS MapServer "
                    f"(keys={','.join(sorted(data.keys())[:20])})"
                )
            continue

        errors.append(
            f"{label}: HTTP {r.status_code} "
            f"Content-Type={r.headers.get('content-type', '')} "
            f"Final={r.url}"
        )

    raise RuntimeError(
        "ArcGIS REST metadata tidak tersedia sebagai JSON. "
        + " | ".join(errors)
    )


def arcgis_url(proxy_prefix: str | None, root: str, suffix: str, params: dict) -> str:
    target = root.rstrip("/") + "/" + suffix.lstrip("/")
    query = urlencode(params, doseq=True)
    if proxy_prefix:
        return proxy_prefix + target + ("?" + query if query else "")
    return target + ("?" + query if query else "")


def arcgis_probe(
    session: requests.Session,
    row: dict,
    timeout: int,
    output: Path | None,
) -> dict:
    proxy_prefix, root, route, data = choose_arcgis_route(
        session, row, timeout
    )

    print(f"ArcGIS route: {route}")
    print(f"ArcGIS root: {root}")
    print(f"service: {data.get('mapName') or data.get('name') or '(unknown)'}")
    print(f"maxRecordCount: {data.get('maxRecordCount')}")
    layers = data.get("layers") or []
    print(f"sublayers: {len(layers)}")
    for layer in layers[:200]:
        print(f"  {layer.get('id')}: {layer.get('name')}")

    if output:
        save_json(output, data)
        print(f"Saved: {output}")
    return data


def arcgis_download_geojson(
    session: requests.Session,
    row: dict,
    sublayer_id: int,
    bbox: tuple[float, float, float, float] | None,
    output: Path,
    timeout: int,
    delay: float,
) -> None:
    proxy_prefix, root, route, _service_meta = choose_arcgis_route(
        session, row, timeout
    )
    print(f"ArcGIS route: {route}")

    meta, meta_r = arcgis_json(
        session,
        proxy_prefix,
        root,
        str(sublayer_id),
        {"f": "pjson"},
        timeout,
    )
    if meta is None:
        raise RuntimeError(
            "ArcGIS sublayer metadata bukan JSON REST. "
            f"Content-Type={meta_r.headers.get('content-type', '')}"
        )
    page_size = int(meta.get("maxRecordCount") or 1000)
    page_size = max(1, min(page_size, 2000))

    all_features: list[dict] = []
    offset = 0

    while True:
        params: dict[str, str | int] = {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": page_size,
        }
        if bbox:
            minx, miny, maxx, maxy = bbox
            params.update({
                "geometry": f"{minx},{miny},{maxx},{maxy}",
                "geometryType": "esriGeometryEnvelope",
                "spatialRel": "esriSpatialRelIntersects",
                "inSR": "4326",
            })

        url = arcgis_url(
            proxy_prefix,
            root,
            f"{sublayer_id}/query",
            params,
        )
        r = session.get(url, timeout=timeout)
        r.raise_for_status()

        try:
            data = r.json()
        except ValueError as exc:
            raise RuntimeError(
                f"ArcGIS query bukan JSON/GeoJSON. Content-Type={r.headers.get('content-type')}"
            ) from exc

        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(
                "ArcGIS error: " + json.dumps(data["error"], ensure_ascii=False)
            )

        features = data.get("features", []) if isinstance(data, dict) else []
        all_features.extend(features)
        print(
            f"ArcGIS layer {sublayer_id}: offset={offset}, "
            f"received={len(features)}, total={len(all_features)}"
        )

        if len(features) < page_size:
            break

        offset += len(features)
        if delay:
            time.sleep(delay)

    collection = {
        "type": "FeatureCollection",
        "features": all_features,
    }
    save_json(output, collection)
    print(f"GeoJSON saved: {output} ({len(all_features)} features)")


def xml_layer_names(content: bytes) -> list[str]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    names: list[str] = []
    for elem in root.iter():
        tag = elem.tag.split("}", 1)[-1]
        if tag == "Name" and elem.text:
            value = elem.text.strip()
            if value and value not in names:
                names.append(value)
    return names


def wfs_feature_type_names(content: bytes) -> list[str]:
    """Return only WFS FeatureType/Name values from GetCapabilities."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    names: list[str] = []
    for elem in root.iter():
        if elem.tag.split("}", 1)[-1] != "FeatureType":
            continue
        for child in elem:
            if child.tag.split("}", 1)[-1] == "Name" and child.text:
                value = child.text.strip()
                if value and value not in names:
                    names.append(value)
                break
    return names


def resolve_wfs_typename(
    catalog_name: str,
    capabilities: bytes,
    forced: str | None = None,
) -> str:
    advertised = wfs_feature_type_names(capabilities)

    if forced:
        if advertised and forced not in advertised:
            raise RuntimeError(
                f"--typename {forced} tidak ada di WFS GetCapabilities."
            )
        return forced

    if not advertised:
        return catalog_name

    if catalog_name in advertised:
        return catalog_name

    catalog_local = catalog_name.split(":", 1)[-1].lower()

    # Exact local-name match regardless of namespace prefix.
    exact_local = [
        name for name in advertised
        if name.split(":", 1)[-1].lower() == catalog_local
    ]
    if len(exact_local) == 1:
        return exact_local[0]

    # Conservative fuzzy match: handles catalog drift such as
    # PTPRPublish -> PTPRPublished.
    local_map = {
        name.split(":", 1)[-1].lower(): name
        for name in advertised
    }
    matches = difflib.get_close_matches(
        catalog_local,
        list(local_map.keys()),
        n=5,
        cutoff=0.82,
    )
    if len(matches) == 1:
        return local_map[matches[0]]

    # Safe prefix/stem matching for catalog names with deployment suffixes,
    # e.g. foo_1_indonesia vs a WFS type with a slightly different suffix.
    parts = [p for p in catalog_local.split("_") if p]
    stems = []
    if len(parts) >= 2:
        stems.append("_".join(parts[:2]))
    if len(parts) >= 3:
        stems.append("_".join(parts[:3]))

    prefix_hits = []
    for stem in stems:
        hits = [
            name for local, name in local_map.items()
            if local.startswith(stem) or stem in local
        ]
        if hits:
            prefix_hits = sorted(set(hits))
            break

    if len(prefix_hits) == 1:
        return prefix_hits[0]

    # Diagnostics: show the best nearby names without auto-selecting an
    # ambiguous or unrelated feature type.
    ranked_locals = difflib.get_close_matches(
        catalog_local,
        list(local_map.keys()),
        n=10,
        cutoff=0.25,
    )
    ranked = [local_map[x] for x in ranked_locals]
    diagnostics = prefix_hits or ranked

    raise RuntimeError(
        "Layer katalog tidak ditemukan persis di WFS GetCapabilities. "
        f"catalog={catalog_name}; "
        f"kandidat={diagnostics or '(tidak ada)'}. "
        "Gunakan --typename <nama_feature_type> bila ingin memilih eksplisit."
    )


def wfs_bbox_params(
    url: str,
    bbox: tuple[float, float, float, float] | None,
) -> dict[str, str]:
    """Build BBOX parameters accepted by standard WFS and GISTARU wrapper."""
    if not bbox:
        return {}

    minx, miny, maxx, maxy = bbox
    coords = f"{minx},{miny},{maxx},{maxy}"

    if "gistaru-app.atrbpn.go.id/interoppublic/api/wms/" in url:
        return {
            "BBOX": coords,
            "SRS": "EPSG:4326",
        }

    return {
        "bbox": f"{coords},EPSG:4326",
    }


def parse_wfs_hits(content: bytes) -> int | None:
    """Parse WFS resultType=hits count from WFS 1.x/2.x response."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None

    for key in ("numberMatched", "numberOfFeatures"):
        value = root.attrib.get(key)
        if value is None:
            continue
        if str(value).lower() == "unknown":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    return None


def wfs_hit_count(
    session: requests.Session,
    url: str,
    typename: str,
    bbox: tuple[float, float, float, float],
    timeout: int,
) -> int | None:
    bbox_params = wfs_bbox_params(url, bbox)

    attempts = [
        ("2.0.0", "typeNames"),
        ("1.1.0", "typeName"),
        ("1.0.0", "typeName"),
    ]

    for version, type_param in attempts:
        params = {
            "service": "WFS",
            "version": version,
            "request": "GetFeature",
            type_param: typename,
            "resultType": "hits",
            "srsName": "EPSG:4326",
        }
        params.update(bbox_params)
        try:
            r = session.get(
                url,
                params=params,
                timeout=timeout,
                allow_redirects=True,
            )
        except requests.RequestException:
            continue

        if r.status_code >= 400:
            continue

        count = parse_wfs_hits(r.content)
        if count is not None:
            return count

    return None


def wfs_sample_has_feature(
    session: requests.Session,
    url: str,
    typename: str,
    bbox: tuple[float, float, float, float],
    timeout: int,
) -> bool | None:
    """
    Probe at most one feature inside BBOX.

    Some GISTARU WFS wrappers advertise WFS correctly but do not return a
    usable numberMatched/numberOfFeatures for resultType=hits. In that case,
    request one GeoJSON feature instead.
    """
    bbox_params = wfs_bbox_params(url, bbox)

    attempts = [
        ("2.0.0", "typeNames", "count", "application/json"),
        ("2.0.0", "typeNames", "count", "json"),
        ("1.1.0", "typeName", "maxFeatures", "application/json"),
        ("1.1.0", "typeName", "maxFeatures", "json"),
        ("1.0.0", "typeName", "maxFeatures", "application/json"),
        ("1.0.0", "typeName", "maxFeatures", "json"),
    ]

    saw_valid_empty = False

    for version, type_param, limit_param, output_format in attempts:
        params = {
            "service": "WFS",
            "version": version,
            "request": "GetFeature",
            type_param: typename,
            limit_param: "1",
            "outputFormat": output_format,
            "srsName": "EPSG:4326",
        }
        params.update(bbox_params)

        try:
            r = session.get(
                url,
                params=params,
                timeout=timeout,
                allow_redirects=True,
            )
        except requests.RequestException:
            continue

        if r.status_code >= 400:
            continue

        try:
            data = r.json()
        except ValueError:
            continue

        if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
            continue

        features = data.get("features")
        if not isinstance(features, list):
            continue

        if features:
            return True

        saw_valid_empty = True

    if saw_valid_empty:
        return False
    return None


def wfs_candidate_typenames(
    catalog_name: str,
    capabilities: bytes,
) -> list[str]:
    advertised = wfs_feature_type_names(capabilities)
    if not advertised:
        return []

    catalog_local = catalog_name.split(":", 1)[-1].lower()
    parts = [p for p in catalog_local.split("_") if p]

    stems = []
    if len(parts) >= 2:
        stems.append("_".join(parts[:2]))
    if len(parts) >= 3:
        stems.append("_".join(parts[:3]))

    local_map = {
        name.split(":", 1)[-1].lower(): name
        for name in advertised
    }

    for stem in stems:
        hits = sorted({
            name
            for local, name in local_map.items()
            if local.startswith(stem)
        })
        if hits:
            return hits

    return []


def auto_resolve_wfs_typename_by_bbox(
    session: requests.Session,
    url: str,
    catalog_name: str,
    capabilities: bytes,
    bbox: tuple[float, float, float, float],
    timeout: int,
) -> str | None:
    candidates = wfs_candidate_typenames(catalog_name, capabilities)
    if len(candidates) <= 1:
        return candidates[0] if candidates else None

    print(
        f"WFS typename ambigu ({len(candidates)} kandidat); "
        "menguji irisan BBOX..."
    )

    hit_matches: list[tuple[str, int]] = []
    sample_matches: list[str] = []

    for idx, candidate in enumerate(candidates, 1):
        count = wfs_hit_count(
            session,
            url,
            candidate,
            bbox,
            timeout,
        )

        if count is not None:
            print(f"  [{idx}/{len(candidates)}] {candidate}: hits={count}")
            if count > 0:
                hit_matches.append((candidate, count))
            continue

        sample = wfs_sample_has_feature(
            session,
            url,
            candidate,
            bbox,
            timeout,
        )

        if sample is True:
            print(
                f"  [{idx}/{len(candidates)}] {candidate}: "
                "hits=? sample=1"
            )
            sample_matches.append(candidate)
        elif sample is False:
            print(
                f"  [{idx}/{len(candidates)}] {candidate}: "
                "hits=? sample=0"
            )
        else:
            print(
                f"  [{idx}/{len(candidates)}] {candidate}: "
                "hits=? sample=?"
            )

    if hit_matches:
        hit_matches.sort(key=lambda item: item[1], reverse=True)
        if len(hit_matches) == 1 or hit_matches[0][1] > hit_matches[1][1]:
            chosen, count = hit_matches[0]
            print(
                f"WFS typename otomatis: {chosen} "
                f"(hits={count})"
            )
            return chosen

    if len(sample_matches) == 1:
        chosen = sample_matches[0]
        print(f"WFS typename otomatis: {chosen} (sample feature ditemukan)")
        return chosen

    if len(sample_matches) > 1:
        print(
            "BBOX beririsan dengan beberapa FeatureType berdasarkan sample:"
        )
        for name in sample_matches:
            print(f"  {name}")
        print(
            "Tidak memilih otomatis karena BBOX mungkin menyentuh lebih dari "
            "satu wilayah. Gunakan --typename eksplisit."
        )
        return None

    if len(hit_matches) > 1:
        print(
            "BBOX beririsan dengan beberapa FeatureType berdasarkan hits "
            "tanpa pemenang yang jelas:"
        )
        for name, count in hit_matches[:20]:
            print(f"  {name}: {count}")

    return None


def ogc_candidate_urls(base_url: str, service: str) -> list[str]:
    """Build standard GeoServer endpoint candidates from a catalog URL."""
    base = base_url.rstrip("/")
    service_l = service.lower()
    candidates = [base]

    # A catalog may point at a GeoServer workspace root:
    #   .../geoserver/<workspace>
    # while OGC operations live at .../<workspace>/wms or /wfs.
    if "/geoserver/" in base.lower():
        candidates.extend([
            f"{base}/{service_l}",
            f"{base}/ows",
        ])

    # Keep order and remove duplicates.
    out = []
    seen = set()
    for value in candidates:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def ogc_capabilities(
    session: requests.Session,
    url: str,
    service: str,
    timeout: int,
) -> tuple[bool, bytes, requests.Response]:
    r = session.get(
        url,
        params={
            "service": service,
            "request": "GetCapabilities",
        },
        timeout=timeout,
        allow_redirects=True,
    )
    body = r.content
    prefix = body[:4000].lower()
    ok = (
        r.status_code == 200
        and (
            b"capabilities" in prefix
            or b"featuretype" in prefix
            or b"wms_capabilities" in prefix
        )
        and b"<html" not in prefix
    )
    return ok, body, r


def find_ogc_endpoint(
    session: requests.Session,
    row: dict,
    service: str,
    timeout: int,
) -> tuple[str | None, bytes | None, requests.Response | None]:
    base = resolve_url(str(row.get("map_service_url") or ""))
    last_response = None
    for candidate in ogc_candidate_urls(base, service):
        try:
            ok, body, r = ogc_capabilities(
                session, candidate, service, timeout
            )
        except requests.RequestException:
            continue
        last_response = r
        if ok:
            return candidate, body, r
    return None, None, last_response


def ogc_probe(
    session: requests.Session,
    row: dict,
    timeout: int,
    output_dir: Path | None,
) -> None:
    base = resolve_url(str(row.get("map_service_url") or ""))
    for service in ("WMS", "WFS"):
        endpoint, body, r = find_ogc_endpoint(
            session, row, service, timeout
        )
        if endpoint and body is not None and r is not None:
            print(
                f"{service}: HTTP {r.status_code} "
                f"{r.headers.get('content-type', '')} OK"
            )
            print(f"  endpoint: {endpoint}")
            names = (
                wfs_feature_type_names(body)
                if service == "WFS"
                else xml_layer_names(body)
            )
            label = "feature types" if service == "WFS" else "advertised names"
            print(f"  {label}: {len(names)}")
            if service == "WFS":
                catalog_local = str(
                    row.get("map_service_layer_name") or ""
                ).split(":", 1)[-1].lower()
                stem = "_".join(
                    [p for p in catalog_local.split("_") if p][:2]
                )
                relevant = [
                    name for name in names
                    if (
                        catalog_local in name.lower()
                        or (stem and stem in name.lower())
                    )
                ]
                if relevant:
                    print("  relevant feature types:")
                    for name in relevant[:50]:
                        print(f"    {name}")
            for name in names[:50]:
                print(f"    {name}")
            if output_dir:
                output_dir.mkdir(parents=True, exist_ok=True)
                path = output_dir / f"{service.lower()}_capabilities.xml"
                path.write_bytes(body)
                print(f"  saved: {path}")
        else:
            if r is not None:
                print(
                    f"{service}: HTTP {r.status_code} "
                    f"{r.headers.get('content-type', '')} NO"
                )
            else:
                print(f"{service}: NO (no reachable candidate)")
            print(
                "  tried: "
                + ", ".join(ogc_candidate_urls(base, service))
            )


def wfs_diagnose(
    session: requests.Session,
    row: dict,
    bbox: tuple[float, float, float, float] | None,
    timeout: int,
    forced_typename: str | None = None,
) -> None:
    url, caps, _resp = find_ogc_endpoint(
        session, row, "WFS", timeout
    )
    if not url or caps is None:
        raise RuntimeError(
            "Tidak menemukan endpoint WFS GetCapabilities yang valid."
        )

    catalog_typename = str(row.get("map_service_layer_name") or "")
    typename = resolve_wfs_typename(
        catalog_typename,
        caps,
        forced=forced_typename,
    )

    print(f"WFS endpoint: {url}")
    print(f"WFS diagnose typename: {typename}")

    tests = [
        ("NO_BBOX", None),
        ("WITH_BBOX", bbox),
    ]

    for label, test_bbox in tests:
        if label == "WITH_BBOX" and test_bbox is None:
            continue

        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": typename,
            "count": "1",
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",
        }
        params.update(wfs_bbox_params(url, test_bbox))

        try:
            r = session.get(
                url,
                params=params,
                timeout=timeout,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            print(f"{label}: REQUEST_ERROR {exc}")
            continue

        print(
            f"{label}: HTTP {r.status_code} "
            f"Content-Type={r.headers.get('content-type', '')} "
            f"Bytes={len(r.content)}"
        )

        if r.status_code >= 400:
            print(f"  ERROR: {r.text[:1500].replace(chr(10), ' ')}")
            continue

        try:
            data = r.json()
        except ValueError:
            print(f"  NON_JSON: {r.text[:1000].replace(chr(10), ' ')}")
            continue

        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            features = data.get("features")
            count = len(features) if isinstance(features, list) else None
            print(f"  FeatureCollection features={count}")
            if isinstance(features, list) and features:
                feature = features[0]
                props = feature.get("properties", {}) if isinstance(feature, dict) else {}
                geom = feature.get("geometry", {}) if isinstance(feature, dict) else {}
                print(f"  sample properties keys={list(props.keys())[:30]}")
                print(f"  sample geometry type={geom.get('type') if isinstance(geom, dict) else None}")
            continue

        print(f"  JSON keys={list(data.keys())[:30] if isinstance(data, dict) else type(data).__name__}")


def wfs_download(
    session: requests.Session,
    row: dict,
    bbox: tuple[float, float, float, float] | None,
    output: Path,
    timeout: int,
    forced_typename: str | None = None,
) -> None:
    url, caps, _resp = find_ogc_endpoint(
        session, row, "WFS", timeout
    )
    if not url or caps is None:
        raise RuntimeError(
            "Tidak menemukan endpoint WFS GetCapabilities yang valid."
        )

    catalog_typename = str(row.get("map_service_layer_name") or "")

    print(f"WFS endpoint: {url}")

    try:
        typename = resolve_wfs_typename(
            catalog_typename,
            caps,
            forced=forced_typename,
        )
    except RuntimeError:
        if forced_typename or not bbox:
            raise

        typename = auto_resolve_wfs_typename_by_bbox(
            session,
            url,
            catalog_typename,
            caps,
            bbox,
            timeout,
        )
        if not typename:
            raise RuntimeError(
                "Tidak bisa memilih WFS FeatureType secara otomatis dari BBOX. "
                "Gunakan --probe lalu pilih --typename eksplisit tanpa backslash."
            )

    if typename != catalog_typename:
        print(
            f"WFS typename dikoreksi dari {catalog_typename} -> {typename} "
            "berdasarkan GetCapabilities"
        )
    else:
        print(f"WFS typename: {typename}")

    bbox_params = wfs_bbox_params(url, bbox)

    attempts = [
        ("2.0.0", "typeNames", "application/json"),
        ("2.0.0", "typeNames", "json"),
        ("1.1.0", "typeName", "application/json"),
        ("1.1.0", "typeName", "json"),
        ("1.0.0", "typeName", "application/json"),
        ("1.0.0", "typeName", "json"),
    ]

    errors: list[str] = []

    for version, type_param, output_format in attempts:
        params = {
            "service": "WFS",
            "version": version,
            "request": "GetFeature",
            type_param: typename,
            "outputFormat": output_format,
            "srsName": "EPSG:4326",
        }
        params.update(bbox_params)

        try:
            r = session.get(
                url,
                params=params,
                timeout=timeout,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            errors.append(
                f"WFS {version} {output_format}: "
                f"{type(exc).__name__}: {exc}"
            )
            continue

        if r.status_code >= 400:
            detail = r.text[:1200].replace("\n", " ")
            errors.append(
                f"WFS {version} {output_format}: HTTP {r.status_code} "
                f"{detail}"
            )
            continue

        try:
            data = r.json()
        except ValueError:
            detail = r.text[:1200].replace("\n", " ")
            errors.append(
                f"WFS {version} {output_format}: bukan JSON "
                f"Content-Type={r.headers.get('content-type', '')} {detail}"
            )
            continue

        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            save_json(output, data)
            features = data.get("features", [])
            print(
                f"WFS GeoJSON saved: {output} "
                f"({len(features) if isinstance(features, list) else '?'} features)"
            )
            print(
                f"WFS mode berhasil: version={version}, "
                f"outputFormat={output_format}"
            )
            return

        errors.append(
            f"WFS {version} {output_format}: JSON bukan FeatureCollection"
        )

    raise RuntimeError(
        "Semua varian GetFeature WFS gagal:\n- " + "\n- ".join(errors)
    )


def wms_download(
    session: requests.Session,
    row: dict,
    bbox: tuple[float, float, float, float],
    output: Path,
    timeout: int,
    width: int,
    height: int,
) -> None:
    url, _caps, _resp = find_ogc_endpoint(
        session, row, "WMS", timeout
    )
    if not url:
        raise RuntimeError(
            "Tidak menemukan endpoint WMS GetCapabilities yang valid."
        )
    print(f"WMS endpoint: {url}")
    layer = str(row.get("map_service_layer_name") or "")
    minx, miny, maxx, maxy = bbox
    params = {
        "service": "WMS",
        "version": "1.1.1",
        "request": "GetMap",
        "layers": layer,
        "styles": "",
        "srs": "EPSG:4326",
        "bbox": f"{minx},{miny},{maxx},{maxy}",
        "width": width,
        "height": height,
        "format": "image/png",
        "transparent": "true",
    }
    r = session.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    prefix = r.content[:2000].lstrip().lower()
    if prefix.startswith(b"<?xml") or b"<serviceexception" in prefix or b"<html" in prefix:
        raise RuntimeError(r.text[:3000])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(r.content)
    print(f"WMS image saved: {output} ({len(r.content)} bytes)")


def lon2tile(lon: float, zoom: int) -> int:
    return int((lon + 180.0) / 360.0 * (1 << zoom))


def lat2tile(lat: float, zoom: int) -> int:
    lat = max(min(lat, 85.05112878), -85.05112878)
    rad = math.radians(lat)
    n = 1 << zoom
    return int(
        (1.0 - math.asinh(math.tan(rad)) / math.pi) / 2.0 * n
    )


def xyz_download(
    session: requests.Session,
    row: dict,
    bbox: tuple[float, float, float, float],
    zoom: int,
    output_dir: Path,
    timeout: int,
    delay: float,
    max_tiles: int,
) -> None:
    template = resolve_url(str(row.get("map_service_url") or ""))
    minlon, minlat, maxlon, maxlat = bbox

    x0 = lon2tile(minlon, zoom)
    x1 = lon2tile(maxlon, zoom)
    y0 = lat2tile(maxlat, zoom)
    y1 = lat2tile(minlat, zoom)

    count = (x1 - x0 + 1) * (y1 - y0 + 1)
    if count > max_tiles:
        raise RuntimeError(
            f"Permintaan mencakup {count} tile, melewati --max-tiles={max_tiles}. "
            "Perkecil AOI/zoom atau naikkan limit secara sadar."
        )

    print(f"XYZ z={zoom}: x={x0}..{x1}, y={y0}..{y1}, tiles={count}")
    downloaded = 0

    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            url = (
                template
                .replace("{z}", str(zoom))
                .replace("{x}", str(x))
                .replace("{y}", str(y))
            )
            r = session.get(url, timeout=timeout)
            r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            ext = mimetypes.guess_extension(ctype.split(";", 1)[0]) or ".bin"
            if ext == ".jpe":
                ext = ".jpg"
            path = output_dir / str(zoom) / str(x) / f"{y}{ext}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
            downloaded += 1
            print(f"[{downloaded}/{count}] {path}")
            if delay:
                time.sleep(delay)


def fetch_metadata(
    session: requests.Session,
    row: dict,
    output: Path,
    timeout: int,
) -> None:
    url = resolve_url(str(row.get("map_service_url") or ""))
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(r.content)
    print(
        f"Metadata saved: {output} "
        f"({r.headers.get('content-type', '')}, {len(r.content)} bytes)"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Probe/download public BHUMI catalog services."
    )
    selector = ap.add_mutually_exclusive_group(required=True)
    selector.add_argument("--name")
    selector.add_argument("--id")

    action = ap.add_mutually_exclusive_group()
    action.add_argument("--probe", action="store_true")
    action.add_argument("--download", action="store_true")
    action.add_argument(
        "--diagnose-wfs",
        action="store_true",
        help="Bandingkan sample WFS tanpa BBOX vs dengan BBOX.",
    )

    ap.add_argument("--bbox", type=parse_bbox)
    ap.add_argument("--zoom", type=int)
    ap.add_argument("--arcgis-layer-id", type=int)
    ap.add_argument("--output")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--delay", type=float, default=0.2)
    ap.add_argument("--max-tiles", type=int, default=500)
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument(
        "--vector",
        action="store_true",
        help="Untuk WMS/OGC, download via WFS sebagai GeoJSON bila tersedia.",
    )
    ap.add_argument(
        "--typename",
        help="Override nama WFS FeatureType secara eksplisit.",
    )
    args = ap.parse_args()

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; demnas-bulk-downloader/1.0)",
        "Referer": f"{BASE}/peta",
        "Accept": "*/*",
    })

    try:
        rows = fetch_catalog(session, args.timeout)
        row = find_layer(rows, args.name, args.id)
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print_layer(row)

    category = classify(row)
    if not args.probe and not args.download:
        return 0

    try:
        if args.diagnose_wfs:
            if category not in {"wms", "ogc", "geoserver"}:
                print(
                    "ERROR: --diagnose-wfs hanya untuk layer WFS/OGC/WMS.",
                    file=sys.stderr,
                )
                return 4
            wfs_diagnose(
                session,
                row,
                args.bbox,
                args.timeout,
                forced_typename=args.typename,
            )
            return 0

        if category == "bhumi-wrapper":
            print(
                "\nLayer ini memakai BHUMI application wrapper. "
                "Tool public downloader tidak mencoba bulk-download dari wrapper tersebut."
            )
            return 3

        if category == "arcgis":
            if args.download:
                if args.arcgis_layer_id is None:
                    print(
                        "ERROR: download ArcGIS memerlukan --arcgis-layer-id. "
                        "Jalankan --probe dulu untuk melihat daftar sublayer.",
                        file=sys.stderr,
                    )
                    return 4
                out = Path(args.output or f"output/arcgis_{args.arcgis_layer_id}.geojson")
                arcgis_download_geojson(
                    session, row, args.arcgis_layer_id, args.bbox,
                    out, args.timeout, args.delay,
                )
            else:
                out = Path(args.output) if args.output else None
                arcgis_probe(session, row, args.timeout, out)
            return 0

        if category in {"ogc", "geoserver"}:
            if args.download:
                out = Path(args.output or "output/ogc_layer.geojson")
                wfs_download(
                    session, row, args.bbox, out, args.timeout,
                    forced_typename=args.typename,
                )
            else:
                outdir = Path(args.output) if args.output else None
                ogc_probe(session, row, args.timeout, outdir)
            return 0

        if category == "wms":
            if args.download:
                if args.vector:
                    out = Path(args.output or "output/wfs_layer.geojson")
                    wfs_download(
                        session, row, args.bbox, out, args.timeout,
                        forced_typename=args.typename,
                    )
                else:
                    if not args.bbox:
                        print("ERROR: WMS download memerlukan --bbox.", file=sys.stderr)
                        return 4
                    out = Path(args.output or "output/wms_layer.png")
                    wms_download(
                        session, row, args.bbox, out,
                        args.timeout, args.width, args.height,
                    )
            else:
                outdir = Path(args.output) if args.output else None
                ogc_probe(session, row, args.timeout, outdir)
            return 0

        if category == "xyz":
            if args.download:
                if not args.bbox or args.zoom is None:
                    print(
                        "ERROR: XYZ download memerlukan --bbox dan --zoom.",
                        file=sys.stderr,
                    )
                    return 4
                outdir = Path(args.output or "output/xyz")
                xyz_download(
                    session, row, args.bbox, args.zoom, outdir,
                    args.timeout, args.delay, args.max_tiles,
                )
            else:
                url = resolve_url(str(row.get("map_service_url") or ""))
                print(f"XYZ template: {url}")
            return 0

        if category == "3d-tiles":
            out = Path(args.output or "output/tileset.json")
            fetch_metadata(session, row, out, args.timeout)
            return 0

        if category == "terrain":
            out = Path(args.output or "output/terrain_tiles.json")
            fetch_metadata(session, row, out, args.timeout)
            return 0

        print(f"Belum ada adapter untuk category={category}", file=sys.stderr)
        return 5

    except (requests.RequestException, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 6


if __name__ == "__main__":
    raise SystemExit(main())