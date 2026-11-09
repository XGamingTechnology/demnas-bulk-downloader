"""Conservatively identify downloadable resources advertised on BKPM detail pages.

This module reads public HTML only. A resource name ending in "(CSV)" does
not establish a downloadable URL or prove that file content was acquired.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse
from bs4 import BeautifulSoup

RESOURCE_LABEL = re.compile(
    r"^(?P<name>.+?)\s*\((?P<format>CSV|JSON|XLSX?|PDF|ZIP)\)\s*$", re.I
)
DIRECT_FILE = re.compile(r"\.(?:csv|json|xlsx?|pdf|zip)(?:$|\?)", re.I)

def extract_resources(html: str, page_url: str) -> list[dict]:
    """Find format-labelled source headings and explicitly linked file URLs.

    Never guess missing download links. The recorded link is a candidate,
    not a file that has been verified or downloaded.
    """
    soup = BeautifulSoup(html, "html.parser")
    result = []
    seen = set()
    allowed = {"data.bkpm.go.id", "regionalinvestment.bkpm.go.id"}
    for tag in soup.find_all(["h3", "h4", "h5", "h6", "strong"]):
        raw = tag.get_text(" ", strip=True)
        match = RESOURCE_LABEL.match(raw)
        if not match:
            continue
        label = match.group("name").strip()
        fmt = match.group("format").upper()
        if not label or len(label) > 250:
            continue
        key = (label, fmt)
        if key in seen:
            continue
        seen.add(key)
        # A link is only recorded when the HTML explicitly contains a
        # link to a matching file in the same short source section.
        parent = tag.parent
        hrefs = []
        if parent:
            for link in parent.select("a[href]"):
                href = link.get("href", "")
                candidate = urljoin(page_url, href)
                parts = urlparse(candidate)
                if (parts.scheme == "https"
                    and parts.hostname in allowed
                    and not parts.username and not parts.password
                    and DIRECT_FILE.search(parts.path)):
                    hrefs.append(urlunparse((parts.scheme, parts.netloc,
                                            parts.path, "", parts.query, "")))
        result.append({
            "dataset_page": page_url,
            "resource_name": label,
            "resource_format": fmt,
            "direct_file_url_candidate": sorted(set(hrefs))[0] if hrefs else "",
            "file_download_verified": False,
            "note": ("HTML link only; response not tested" if hrefs
                     else "No direct file URL visible in this HTML"),
        })
    return result
