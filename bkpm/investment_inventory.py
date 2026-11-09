#!/usr/bin/env python3
"""Public BKPM investment catalog inventory; NOT a hidden API enumerator.

Fetch only observed/linked public pages. Catalog pages != downloaded data.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from .resource_extract import extract_resources

SINGLE = "https://data.bkpm.go.id/dataset"
PIR = "https://regionalinvestment.bkpm.go.id"
PIR_PAGES = ("/peluang_investasi", "/daerah", "/hilirisasi", "/kawasan")
# Detail URLs publicly observed in search results; never synthesize numeric IDs.
SEEDS = (
    PIR + "/peluang_investasi/detailed/868",
    PIR + "/peluang_investasi/detailed/1133",
    PIR + "/peluang_investasi/detailed/1311",
    PIR + "/peluang_investasi/detailed/1267",
    PIR + "/peluang_investasi/detailed/1276",
    "https://data.bkpm.go.id/dataset-detail/data-realisasi-investasi-triwulan-iii-tahun-2026",
    "https://data.bkpm.go.id/dataset-detail/nilai-pma-dan-pmdn-tahun-2025-dwTJ1Nh",
    "https://data.bkpm.go.id/dataset-detail/nilai-realisasi-penanaman-modal-di-bidang-hilirisasi-tahun-2025-IEecpti",
    "https://data.bkpm.go.id/dataset-detail/nilai-pma-kawasan-ekonomi-khusus-tahun-2025-data-sementara",
)

def safe_url(raw: str, base: str | None = None) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    p = urlparse(urljoin(base, raw.strip()) if base else raw.strip())
    if p.scheme != "https" or p.username or p.password or p.port:
        return None
    path = p.path.rstrip("/") or "/"
    if p.hostname == "data.bkpm.go.id":
        ok = path == "/dataset" or path.startswith("/dataset-detail/")
    elif p.hostname == "regionalinvestment.bkpm.go.id":
        ok = path in PIR_PAGES or path.startswith((
            "/peluang_investasi/detailed/", "/daerah/provinsi/", "/kawasan/"
        ))
    else:
        return None
    if not ok or re.search(r"(?:^|/)(?:admin|login|logout|api)(?:/|$)", path, re.I):
        return None
    return urlunparse(("https", p.hostname, path, "", p.query, ""))

def kind(url: str) -> str:
    path = urlparse(url).path
    if path.startswith("/dataset-detail/"):
        return "realisasi_dataset_detail"
    if path.startswith("/peluang_investasi/detailed/"):
        return "peluang_proyek_detail"
    if path.startswith("/daerah/provinsi/"):
        return "daerah_provinsi"
    if path.startswith("/kawasan/"):
        return "kawasan_detail"
    return "catalog_index"

def links_from(html: str, base: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = set()
    for a in soup.select("a[href]"):
        link = safe_url(a.get("href"), base)
        if link and kind(link) != "catalog_index":
            urls.add(link)
    return sorted(urls)

def capture(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text, re.I)
    return m.group(1).strip(" \t\r\n:;,.") if m else None

def parse_detail(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script,style,noscript,nav,footer"):
        tag.decompose()
    text = " ".join(soup.stripped_strings)
    heading = soup.find("h1") or soup.find("h2") or soup.find("h3")
    row = {"url": url, "kind": kind(url),
           "title_raw": heading.get_text(" ", strip=True) if heading else None,
           "text_chars": len(text),
           "parse_status": "metadata_only_unverified"}
    if kind(url) == "peluang_proyek_detail":
        patterns = {
            "kbli_raw": r"Kode\s+KBLI\s*:\s*(.*?)(?=\s*Nilai\s+Investasi\s*:|$)",
            "investment_raw": r"Nilai\s+Investasi\s*:\s*(Rp\s*[\d.,]+\s*(?:T|M|Rb|Juta|Miliar|Triliun)?)",
            "year_raw": r"\bTahun\s*:\s*(\d{4})",
            "irr_raw": r"\bIRR\s*:\s*([\d.,]+\s*%)",
            "npv_raw": r"\bNPV\s*:\s*(Rp\s*[\d.,]+\s*(?:T|M|Rb|Juta|Miliar|Triliun)?)",
            "payback_raw": r"Payback\s+Period\s*:\s*([\d.,]+\s*Tahun)",
            "longitude_raw": r"\bLongitude\s*:\s*(-?\d+(?:\.\d+)?)",
            "latitude_raw": r"\bLatitude\s*:\s*(-?\d+(?:\.\d+)?)",
        }
        row.update({key: capture(text, pat) for key, pat in patterns.items()})
        try:
            x, y = float(row["longitude_raw"]), float(row["latitude_raw"])
            row["coordinate_qc"] = "range_ok_location_unverified" if -180 <= x <= 180 and -90 <= y <= 90 else "out_of_range"
        except (TypeError, ValueError):
            row["coordinate_qc"] = "missing"
    if kind(url) == "realisasi_dataset_detail":
        row["advertised_formats"] = ",".join(sorted(set(re.findall(
            r"\((CSV|JSON|XLSX?|PDF)\)", text, re.I
        ))))
        row["download_label_visible"] = "Unduh Data" in text
        row["direct_file_href_visible"] = any(re.search(
            r"\.(?:csv|json|xlsx?|pdf)(?:\?|$)", a.get("href", ""), re.I
        ) for a in soup.select("a[href]"))
    return row

class Client:
    def __init__(self, delay: float):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "demnas-bkpm-public-catalog-audit/0.2"
        self.delay = max(delay, 1.0)
        self.last = 0.0
        self.stopped_hosts: set[str] = set()

    def fetch(self, url: str) -> tuple[str, int, str]:
        if not safe_url(url):
            raise RuntimeError("URL outside allowlist")
        host = urlparse(url).hostname
        if host in self.stopped_hosts:
            raise RuntimeError("Host stopped after 403/429")
        waiting = self.delay - (time.monotonic() - self.last)
        if waiting > 0:
            time.sleep(waiting)
        self.last = time.monotonic()
        try:
            with self.s.get(url, timeout=(12, 40), stream=True,
                            allow_redirects=False) as resp:
                if resp.status_code in (403, 429):
                    self.stopped_hosts.add(host)
                    raise RuntimeError(f"HTTP {resp.status_code}: stop requests to host")
                if resp.is_redirect:
                    raise RuntimeError("redirect (inspect URL manually)")
                resp.raise_for_status()
                if "html" not in resp.headers.get("Content-Type", "").lower():
                    raise RuntimeError("Response is not HTML")
                raw = bytearray()
                for chunk in resp.iter_content(65536):
                    raw.extend(chunk)
                    if len(raw) > 8 * 1024 * 1024:
                        raise RuntimeError("HTML exceeds 8 MiB")
                return raw.decode(resp.encoding or "utf-8", errors="replace"), resp.status_code, hashlib.sha256(raw).hexdigest()
        except requests.RequestException as exc:
            raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc

def save_csv(path: Path, records: list[dict], initial: list[str]) -> None:
    keys = list(initial)
    for row in records:
        for k in row:
            if k not in keys:
                keys.append(k)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(records)

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=Path("data/bkpm/investment"))
    p.add_argument("--catalog-pages", type=int, default=12)
    p.add_argument("--max-details", type=int, default=150)
    p.add_argument("--delay", type=float, default=1.5)
    p.add_argument("--index-only", action="store_true")
    p.add_argument("--seeds-file", type=Path,
                   help="Optional file with observed public detail URLs, one per line")
    args = p.parse_args(argv)
    if not 1 <= args.catalog_pages <= 30 or not 0 <= args.max_details <= 500:
        p.error("Catalog pages 1..30; max details 0..500")
    args.output.mkdir(parents=True, exist_ok=True)
    client = Client(args.delay)
    pages: list[dict] = []
    details: list[dict] = []
    resources: list[dict] = []
    discovered = set(SEEDS)

    def visit(url: str, role: str):
        print("GET", url, flush=True)
        rec = {"url": url, "role": role, "kind": kind(url)}
        try:
            html, code, digest = client.fetch(url)
            rec.update(status="ok", http_status=code, sha256=digest)
            parsed = parse_detail(html, url)
            rec.update(parsed)
            new_links = links_from(html, url)
            rec["links_found"] = len(new_links)
            discovered.update(new_links)
            if role == "detail":
                details.append(parsed)
                if kind(url) == "realisasi_dataset_detail":
                    resources.extend(extract_resources(html, url))
            print(" OK", code, "links", len(new_links))
        except (RuntimeError, ValueError) as exc:
            rec.update(status="error", error=str(exc))
            print(" ERROR", exc)
        pages.append(rec)

    for number in range(1, args.catalog_pages + 1):
        visit(f"{SINGLE}?page={number}", "index")
    for path in PIR_PAGES:
        visit(PIR + path, "index")

    if args.seeds_file:
        for line in args.seeds_file.read_text(encoding="utf-8").splitlines():
            link = safe_url(line.strip())
            if link and kind(link) != "catalog_index":
                discovered.add(link)

    if not args.index_only:
        for link in sorted(discovered)[:args.max_details]:
            visit(link, "detail")

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "inventory publicly linked pages, not download entire BKPM datasets",
        "page_outcomes": dict(Counter(p["status"] for p in pages)),
        "total_page_requests": len(pages),
        "unique_detail_url_candidates": len(discovered),
        "detail_requests": sum(p["role"] == "detail" for p in pages),
        "limitations": [
            "HTML may be dynamically rendered; missing links are not evidence of no data",
            "CSV/JSON download button URLs require direct browser verification",
            "No private endpoints, numeric ID enumeration, or access control bypass",
            "Project opportunities are NOT realized investment amounts",
            "Currency and project coordinates require QC before statistical/GIS use",
        ],
    }
    (args.output / "audit.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.output / "pages.json").write_text(json.dumps(pages, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.output / "discovered_urls.txt").write_text("\n".join(sorted(discovered)) + "\n", encoding="utf-8")
    save_csv(args.output / "pages.csv", pages, ["url", "kind", "role", "status", "http_status", "error"])
    save_csv(args.output / "details.csv", details, ["url", "kind", "title_raw"])
    save_csv(args.output / "resources.csv", resources, ["dataset_page", "resource_name", "resource_format", "direct_file_url_candidate", "file_download_verified", "note"])
    summary["advertised_resources_found"] = len(resources)
    summary["direct_file_url_candidates"] = sum(bool(r["direct_file_url_candidate"]) for r in resources)
    (args.output / "audit.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("AUDIT", json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if any(p["status"] == "ok" for p in pages) else 2

if __name__ == "__main__":
    raise SystemExit(main())
