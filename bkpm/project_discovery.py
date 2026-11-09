#!/usr/bin/env python3
"""Discover publicly observed BKPM project URLs using Chromium.

No project-ID enumeration, login bypass, hidden APIs, or private data capture.
The collector records rendered route evidence; it does not infer missing URLs.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

HOST = "regionalinvestment.bkpm.go.id"
LISTINGS = (
    f"https://{HOST}/peluang_investasi",
    f"https://{HOST}/",
)
DETAIL_PATH = re.compile(r"^/peluang_investasi/detailed/([0-9]{1,9})/?$")
ROUTE = re.compile(
    r"(?<![\\w./@-])(?:https://regionalinvestment\\.bkpm\\.go\\.id)?"
    r"/peluang_investasi/detailed/[0-9]{1,9}(?![0-9])", re.I
)
NEXT = re.compile(r"^(?:next|selanjutnya|berikutnya|›|»)$", re.I)


def accepted_project_url(raw: str, base: str = "") -> str | None:
    if not isinstance(raw, str):
        return None
    p = urlparse(urljoin(base, raw))
    if (p.scheme != "https" or p.hostname != HOST or p.username
            or p.password or p.port is not None or not DETAIL_PATH.fullmatch(p.path)):
        return None
    return f"https://{HOST}{p.path.rstrip('/')}"


def observed_links(html: str, page_url: str) -> list[dict]:
    """Record URLs genuinely present in the *rendered* HTML."""
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, set[str]] = {}
    for node in soup.select("a[href], [data-href], [data-url], [onclick]"):
        for attr in ("href", "data-href", "data-url", "onclick"):
            value = node.get(attr)
            if not isinstance(value, str):
                continue
            direct = accepted_project_url(value, page_url)
            if direct:
                found.setdefault(direct, set()).add(f"dom_{attr}")
            for match in ROUTE.finditer(value):
                u = accepted_project_url(match.group(0), page_url)
                if u:
                    found.setdefault(u, set()).add(f"dom_{attr}_route")
    for match in ROUTE.finditer(html):
        u = accepted_project_url(match.group(0), page_url)
        if u:
            found.setdefault(u, set()).add("rendered_html_route")
    return [
        {"url": url, "source_page": page_url,
         "evidence": ",".join(sorted(origins))}
        for url, origins in sorted(found.items())
    ]


def write_csv(path: Path, rows: list[dict], keys: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=Path("data/bkpm/discovery"))
    p.add_argument("--scroll-rounds", type=int, default=4)
    p.add_argument("--max-next-clicks", type=int, default=3)
    p.add_argument("--max-detail-clicks", type=int, default=0,
                   help="Optional: click visible Selengkapnya controls (limit 10)")
    args = p.parse_args(argv)
    if not (0 <= args.scroll_rounds <= 15
            and 0 <= args.max_next_clicks <= 10
            and 0 <= args.max_detail_clicks <= 10):
        p.error("Scope exceeds safety limits")
    args.output.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    evidence = []
    pages = []
    network = Counter()

    def sample(page, listing: str, stage: str):
        evidence.extend({**entry, "phase": stage}
                        for entry in observed_links(page.content(), listing))
        pages.append({
            "listing": listing, "phase": stage, "page_url": page.url,
            "unique_discovered": len({entry["url"] for entry in evidence}),
            "project_card_headings": page.locator("h3").count(),
            "selengkapnya_controls": page.get_by_text("Selengkapnya", exact=True).count(),
            "body_text_length": len(page.locator("body").inner_text(timeout=7000)),
            "no_information_message": "Belum ada informasi tersedia" in page.locator("body").inner_text(timeout=7000),
            "sample_headings": " | ".join([
                s.strip()[:80] for s in page.locator("h3").all_inner_texts()[:8]
            ])[:500],
        })

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(locale="id-ID", service_workers="block")
            for listing in LISTINGS:
                page = context.new_page()

                def record_response(response):
                    parsed = urlparse(response.url)
                    if parsed.hostname == HOST:
                        # Never keep query strings, cookies or response bodies.
                        network[(parsed.path, response.status,
                                 response.headers.get("content-type", "").split(";")[0])] += 1
                page.on("response", record_response)
                print("RENDER", listing, flush=True)
                try:
                    resp = page.goto(listing, wait_until="domcontentloaded", timeout=30000)
                    if resp is None or resp.status >= 400:
                        pages.append({"listing": listing, "phase": "navigation_error",
                                      "error": str(resp.status if resp else "no_response")})
                        if resp and resp.status in (403, 429):
                            print("STOP: access restricted", flush=True)
                            break
                        continue
                    page.wait_for_timeout(1600)
                    sample(page, listing, "initial")
                    for i in range(args.scroll_rounds):
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(1600)
                        sample(page, listing, f"scroll_{i+1}")
                    for i in range(args.max_next_clicks):
                        buttons = page.get_by_role("button", name=NEXT)
                        if buttons.count() == 0:
                            buttons = page.get_by_role("link", name=NEXT)
                        if buttons.count() == 0 or not buttons.last.is_visible() or not buttons.last.is_enabled():
                            break
                        prior = page.content()
                        buttons.last.click(timeout=6000)
                        page.wait_for_timeout(1700)
                        sample(page, listing, f"next_{i+1}")
                        if page.content() == prior or urlparse(page.url).hostname != HOST:
                            break
                    for i in range(args.max_detail_clicks):
                        page.goto(listing, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(1600)
                        buttons = page.get_by_text("Selengkapnya", exact=True)
                        if i >= buttons.count():
                            break
                        buttons.nth(i).click(timeout=6000)
                        page.wait_for_timeout(1600)
                        url = accepted_project_url(page.url)
                        if url:
                            evidence.append({
                                "url": url, "source_page": listing,
                                "evidence": "observed_button_navigation",
                                "phase": f"button_{i+1}",
                            })
                except Exception as exc:
                    pages.append({"listing": listing, "phase": "error",
                                  "error": str(exc)[:180]})
                finally:
                    page.close()
            context.close()
        finally:
            browser.close()

    unique = sorted({r["url"] for r in evidence})
    write_csv(args.output / "evidence.csv", evidence,
              ["url", "source_page", "evidence", "phase"])
    write_csv(args.output / "page_audit.csv", pages,
              ["listing", "phase", "page_url", "unique_discovered",
               "project_card_headings", "selengkapnya_controls",
               "body_text_length", "no_information_message", "sample_headings", "error"])
    write_csv(args.output / "network_paths.csv", [
        {"path": key[0], "http_status": key[1], "content_type": key[2],
         "count": n} for key, n in sorted(network.items())
    ], ["path", "http_status", "content_type", "count"])
    (args.output / "observed_project_urls.txt").write_text(
        "\n".join(unique) + ("\n" if unique else ""), encoding="utf-8"
    )
    summary = {
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "unique_observed_detail_urls": len(unique),
        "total_evidence_rows": len(evidence),
        "listing_pages_attempted": len(LISTINGS),
        "limitations": [
            "Counts are observed links, NOT necessarily all projects on portal",
            "Javascript search filters or hidden pagination may require more inspection",
            "No ID guessing or access-control bypass",
            "Network log saves same-origin paths/status/content-type only",
        ],
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if unique else 2


if __name__ == "__main__":
    raise SystemExit(main())
