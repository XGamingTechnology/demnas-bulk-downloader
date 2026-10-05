#!/usr/bin/env python3
"""
Local BHUMI WMS reverse proxy and endpoint probe.

Purpose:
- listen locally on http://127.0.0.1:8765/bhumi/wms
- forward OGC WMS requests to a configurable upstream endpoint
- probe known/publicly observed BHUMI GeoServer candidates without bypassing auth

Examples:
  python3 bhumi/proxy_wms.py --probe
  python3 bhumi/proxy_wms.py --upstream https://example/geoserver/workspace/wms
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

# Historical/publicly observed candidates. They are probes only, not assumed current.
CANDIDATES = [
    "https://bhumi.atrbpn.go.id/geoserver/umum/wms",
    "https://geosvc.atrbpn.go.id/geoserver/umum/wms",
    "https://bhumi.atrbpn.go.id/proxy/http://10.20.20.142:80/geoserver/umum/wms",
]


def capabilities_url(base: str) -> str:
    params = {
        "service": "WMS",
        "request": "GetCapabilities",
        "version": "1.1.1",
    }
    return base + ("&" if "?" in base else "?") + urllib.parse.urlencode(params)


def looks_like_wms_capabilities(resp: requests.Response) -> bool:
    if resp.status_code != 200:
        return False
    content = resp.content[:20000].lower()
    return (
        b"wmt_ms_capabilities" in content
        or b"wms_capabilities" in content
        or b"serviceexceptionreport" in content
    )


def probe(candidates: list[str], timeout: int = 20) -> list[tuple[str, str]]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "demnas-bulk-downloader/bhumi-probe",
            "Accept": "application/xml,text/xml,*/*",
        }
    )

    results = []
    for upstream in candidates:
        url = capabilities_url(upstream)
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            ctype = resp.headers.get("content-type", "")
            ok = looks_like_wms_capabilities(resp)
            status = (
                f"OK HTTP {resp.status_code} {ctype}"
                if ok
                else f"NO HTTP {resp.status_code} {ctype}"
            )
        except requests.RequestException as exc:
            status = f"ERROR {type(exc).__name__}: {exc}"

        results.append((upstream, status))

    return results


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream = ""
    timeout = 90

    hop_by_hop = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[bhumi-proxy] " + (fmt % args) + "\n")

    def do_HEAD(self) -> None:
        self._proxy(send_body=False)

    def do_GET(self) -> None:
        self._proxy(send_body=True)

    def _proxy(self, send_body: bool) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path.rstrip("/") not in {"", "/bhumi/wms"}:
            self.send_error(404, "Use /bhumi/wms")
            return

        target = self.upstream
        if parsed.query:
            target += ("&" if "?" in target else "?") + parsed.query

        headers = {
            "User-Agent": self.headers.get(
                "User-Agent", "demnas-bulk-downloader/bhumi-proxy"
            ),
            "Accept": self.headers.get("Accept", "*/*"),
        }

        try:
            resp = requests.get(
                target,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True,
                stream=True,
            )
        except requests.RequestException as exc:
            body = f"Upstream request failed: {exc}\n".encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if send_body:
                self.wfile.write(body)
            return

        body = resp.content
        self.send_response(resp.status_code)

        for key, value in resp.headers.items():
            if key.lower() in self.hop_by_hop or key.lower() == "content-length":
                continue
            self.send_header(key, value)

        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        if send_body:
            self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="BHUMI WMS local reverse proxy")
    parser.add_argument(
        "--upstream",
        default=os.environ.get("BHUMI_UPSTREAM_WMS"),
        help="Upstream BHUMI/GeoServer WMS URL",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Probe known BHUMI WMS candidates and exit unless --upstream is also given",
    )
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="Additional WMS candidate to probe (repeatable)",
    )
    args = parser.parse_args()

    if args.probe:
        candidates = args.candidate + CANDIDATES
        print("=== BHUMI WMS PROBE ===")
        good = []
        for upstream, status in probe(candidates, timeout=min(args.timeout, 30)):
            print(f"{status}\n  {upstream}")
            if status.startswith("OK "):
                good.append(upstream)

        if good:
            print("\nCandidate WMS yang merespons:")
            for item in good:
                print(f"  {item}")
        else:
            print(
                "\nBelum ada candidate publik yang terverifikasi sebagai WMS. "
                "Ambil endpoint aktual dari Network/HAR BHUMI lalu jalankan "
                "--candidate URL atau --upstream URL."
            )

        if not args.upstream:
            return 0

    if not args.upstream:
        parser.error(
            "Proxy membutuhkan --upstream URL atau environment BHUMI_UPSTREAM_WMS. "
            "Gunakan --probe untuk audit kandidat terlebih dahulu."
        )

    ProxyHandler.upstream = args.upstream.rstrip("?&")
    ProxyHandler.timeout = args.timeout

    server = ThreadingHTTPServer((args.host, args.port), ProxyHandler)
    print(f"BHUMI proxy listening: http://{args.host}:{args.port}/bhumi/wms")
    print(f"Upstream: {ProxyHandler.upstream}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
