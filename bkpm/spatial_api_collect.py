#!/usr/bin/env python3
"""Export observed public BKPM investment opportunities as audited GeoJSON.

Uses the exact public URLs observed in the browser Network log. The list
response has 'page', 'pageSize', 'totalPage' and 'totalRecords', but support
for the ?page= query parameter is NOT assumed: page 2 is checked and
pagination stops on mismatch/repeated records. No login or guessed IDs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE = "https://regionalinvestment.bkpm.go.id"
REGIONS = BASE + "/be/peluang/peluang_investasi_wilayah"
COMMODITIES = BASE + "/data/komoditas.geojson"
MAX_BYTES = 12 * 1024 * 1024


def fetch_json(session, url: str):
    """Only two observed public URL routes; no redirect or auth forwarding."""
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname != "regionalinvestment.bkpm.go.id"
        or parsed.path not in {urlparse(REGIONS).path, urlparse(COMMODITIES).path}
        or parsed.username or parsed.password or parsed.port):
        raise ValueError("Non-allowlisted URL")
    if parsed.path == urlparse(COMMODITIES).path and parsed.query:
        raise ValueError("No query parameters allowed for commodity GeoJSON")
    if parsed.path == urlparse(REGIONS).path:
        if parsed.query and not (parsed.query.startswith("page=")
                                 and parsed.query[5:].isdigit()):
            raise ValueError("Only ?page=N may be tested")
    with session.get(url, timeout=(12, 45), stream=True, allow_redirects=False) as response:
        if response.status_code in (401, 403, 429):
            raise RuntimeError(f"HTTP {response.status_code}: access restricted; stop")
        if response.is_redirect:
            raise RuntimeError(f"HTTP {response.status_code}: redirect not followed")
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower().split(";")[0].strip()
        if content_type not in {"application/json", "application/geo+json"}:
            raise RuntimeError(f"Unexpected content type: {content_type}")
        body = bytearray()
        for chunk in response.iter_content(65536):
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise RuntimeError("Response exceeds 12 MiB safety cap")
        return json.loads(body), hashlib.sha256(body).hexdigest()


def make_point(record: dict):
    """Return (feature, QA code); never infer coordinates from place names."""
    if not isinstance(record, dict):
        return None, "record_not_object"
    project_id = record.get("id_peluang")
    if isinstance(project_id, bool) or not isinstance(project_id, int) or project_id <= 0:
        return None, "missing_or_invalid_project_id"
    try:
        if isinstance(record.get("lon"), bool) or isinstance(record.get("lat"), bool):
            raise ValueError()
        lon, lat = float(record["lon"]), float(record["lat"])
    except (ValueError, TypeError, KeyError):
        return None, "missing_or_invalid_coordinate"
    if not (math.isfinite(lon) and math.isfinite(lat)
            and -180 <= lon <= 180 and -90 <= lat <= 90):
        return None, "coordinate_out_of_global_range"
    if not (94 <= lon <= 142 and -12 <= lat <= 7):
        return None, "coordinate_outside_indonesia_bbox"
    # Preserve source property strings, units, project status & identifiers.
    properties = dict(record)
    properties.update({
        "source_url": REGIONS,
        "source_project_id": project_id,
        "dataset_role": "investment_opportunity_not_realization",
        "coordinate_qc": "range_ok_site_unverified",
        "location_accuracy": "publisher_point_not_site_validated",
    })
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": properties,
    }, "ok"


def parse_region_payload(payload: dict):
    """Return records and authoritative pagination metadata when provided."""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("API did not confirm success=true")
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("No list in data")
    meta = {}
    for name in ("page", "pageSize", "totalPage", "totalRecords"):
        val = payload.get(name)
        if val is not None and (isinstance(val, bool) or not isinstance(val, int)):
            raise ValueError(f"Non-integer pagination field: {name}")
        meta[name] = val
    return data, meta


def export_commodities(payload: dict):
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("Commodity response is not a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("GeoJSON features is not a list")
    counts = Counter()
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            counts["bad_feature"] += 1
            continue
        geom = feature.get("geometry")
        if not isinstance(geom, dict):
            counts["no_geometry"] += 1
            continue
        typ = geom.get("type")
        counts[str(typ)] += 1
        if typ == "Point":
            coords = geom.get("coordinates")
            if not (isinstance(coords, list) and len(coords) >= 2
                    and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                            and math.isfinite(v) for v in coords[:2])):
                counts["bad_point_coordinates"] += 1
    crs = payload.get("crs")
    crs_name = None
    if isinstance(crs, dict):
        props = crs.get("properties")
        if isinstance(props, dict):
            crs_name = props.get("name")
    return {"features": len(features), "geometry_counts": dict(counts),
            "declared_crs": crs_name or "not_declared",
            "crs_verification": "do_not_assume_epsg4326_from_structure_only"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=Path("data/bkpm/spatial_api"))
    p.add_argument("--max-pages", type=int, default=3,
                   help="Maximum region pages to test; hard cap 30")
    p.add_argument("--delay", type=float, default=2.0)
    args = p.parse_args(argv)
    if not (1 <= args.max_pages <= 30):
        p.error("max-pages must be 1..30")
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "BKPM-public-spatial-audit/0.1"
    pages = []
    all_records = []
    seen_ids = set()
    issues = Counter()
    pagination_status = "unverified"
    expected_total = None
    next_page = 1

    for attempt in range(args.max_pages):
        # First fetch uses exactly the public URL observed in Network.
        url = REGIONS if attempt == 0 else REGIONS + f"?page={next_page}"
        print("FETCH", url, flush=True)
        try:
            payload, digest = fetch_json(session, url)
            records, meta = parse_region_payload(payload)
        except (ValueError, RuntimeError, requests.RequestException, json.JSONDecodeError) as exc:
            pagination_status = "error_or_rejected"
            issues["fetch_or_schema_error"] += 1
            pages.append({"url": url, "error": str(exc)})
            break
        returned_page = meta.get("page")
        if attempt == 0:
            expected_total = meta.get("totalRecords")
            if returned_page not in (None, 1):
                pagination_status = "initial_page_not_one"
                pages.append({"url": url, "metadata": meta, "sha256": digest,
                              "error": "Initial page metadata is not 1"})
                break
        elif returned_page != next_page:
            pagination_status = "page_query_ignored_or_unsupported"
            pages.append({"url": url, "metadata": meta, "sha256": digest,
                          "error": "Returned page number differs from requested page"})
            break
        new_records = []
        page_ids = set()
        for record in records:
            pid = record.get("id_peluang") if isinstance(record, dict) else None
            if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
                issues["invalid_project_id"] += 1
                continue
            if pid in page_ids:
                issues["duplicate_id_within_page"] += 1
                continue
            page_ids.add(pid)
            if pid in seen_ids:
                issues["duplicate_id_across_pages"] += 1
                continue
            new_records.append(record)
        if attempt and not new_records:
            pagination_status = "page_repeated_or_no_new_projects"
            pages.append({"url": url, "metadata": meta,
                          "sha256": digest, "new_records": 0})
            break
        seen_ids.update(page_ids)
        all_records.extend(new_records)
        pages.append({"url": url, "metadata": meta,
                      "sha256": digest, "new_records": len(new_records)})
        if len(records) == 0:
            pagination_status = "empty_page"
            break
        total_pages = meta.get("totalPage")
        if total_pages is not None and returned_page is not None and returned_page >= total_pages:
            pagination_status = "all_reported_pages_reached"
            break
        if expected_total is not None and len(all_records) >= expected_total:
            pagination_status = "reported_total_reached"
            break
        if args.max_pages == 1:
            pagination_status = "first_page_only"
            break
        next_page = (returned_page or 1) + 1
        pagination_status = "page_query_under_test"
        time.sleep(max(1.0, args.delay))
    else:
        pagination_status = "max_pages_reached_not_complete"

    features = []
    for record in all_records:
        feature, reason = make_point(record)
        issues[reason] += 1
        if feature:
            features.append(feature)
    fc = {"type": "FeatureCollection", "features": features}
    (output / "bkpm_opportunities_api_points.geojson").write_text(
        json.dumps(fc, indent=2, ensure_ascii=False), encoding="utf-8")
    (output / "region_records.json").write_text(
        json.dumps({"source": REGIONS, "records": all_records,
                    "metadata": pages}, ensure_ascii=False, indent=2), encoding="utf-8")

    commodity_result = {"status": "not_checked"}
    try:
        time.sleep(max(1.0, args.delay))
        commodity, digest = fetch_json(session, COMMODITIES)
        commodity_result = export_commodities(commodity)
        commodity_result["sha256"] = digest
        (output / "bkpm_komoditas_original.geojson").write_text(
            json.dumps(commodity, ensure_ascii=False), encoding="utf-8")
        commodity_result["status"] = "saved_unmodified"
    except (ValueError, RuntimeError, requests.RequestException, json.JSONDecodeError) as exc:
        commodity_result = {"status": "error", "error": str(exc)}

    summary = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "region_source": REGIONS,
        "region_pages_accepted": sum("new_records" in row and row["new_records"] > 0 for row in pages),
        "region_pages_audit": pages,
        "reported_total_records": expected_total,
        "unique_region_records": len(all_records),
        "point_features_exported": len(features),
        "point_quality_counts": dict(issues),
        "pagination_status": pagination_status,
        "commodity_layer": commodity_result,
        "warnings": [
            "Coordinates are public publisher points; project sites are not field-validated",
            "Opportunity project values must not be added to LKPM realized-investment totals",
            "Pagination is only valid when the response confirms the requested page",
            "Commodity GeoJSON retains original CRS; verify before spatial overlays",
            "Outputs are local data snapshots; do not commit generated raw datasets automatically",
        ],
    }
    (output / "audit.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "pages_accepted": summary["region_pages_accepted"],
        "unique_region_records": len(all_records),
        "point_features_exported": len(features),
        "pagination_status": pagination_status,
        "commodity": commodity_result,
        "output_directory": str(output),
    }, indent=2, ensure_ascii=False))
    return 0 if features or commodity_result.get("status") == "saved_unmodified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
