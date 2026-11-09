"""Conservative BKPM opportunity project-title extraction.

The overall page and recommendation cards often contain unrelated headings.
Use only the current detail breadcrumb or the text immediately following the
current-page breadcrumb in the pre-"Informasi" section. When no reliable
current-page title is present, return None rather than choosing a related
project. Never invent titles based on project IDs or coordinates.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

GENERIC = {
    "beranda", "peluang investasi", "potensi investasi regional",
    "informasi", "deskripsi", "insentif", "infografis & infomemo",
    "galeri", "kontak", "loading", "unduh dokumen",
    "industri", "agro industri", "infrastruktur", "pariwisata",
    "jasa dan kawasan", "energi terbarukan", "sumber daya alam",
    "perdagangan karbon", "primer", "sekunder", "tersier",
    "selengkapnya", "produk terkait", "proyek terkait",
}
PROVINCES = {
    "aceh", "sumatera utara", "sumatera barat", "riau", "jambi",
    "sumatera selatan", "bengkulu", "lampung", "bangka belitung",
    "kepulauan bangka belitung", "kepulauan riau", "jakarta raya",
    "dki jakarta", "jawa barat", "jawa tengah", "jawa timur", "banten",
    "yogyakarta", "daerah istimewa yogyakarta", "bali",
    "nusa tenggara barat", "nusa tenggara timur", "kalimantan barat",
    "kalimantan tengah", "kalimantan selatan", "kalimantan timur",
    "kalimantan utara", "sulawesi utara", "sulawesi tengah",
    "sulawesi selatan", "sulawesi tenggara", "sulawesi barat",
    "gorontalo", "maluku", "maluku utara", "papua", "papua barat",
    "papua selatan", "papua tengah", "papua pegunungan",
    "papua barat daya",
}


def clean_title(value: str | None) -> str | None:
    s = " ".join((value or "").split()).strip(" |-–—:")
    if not 7 <= len(s) <= 180 or s.casefold() in GENERIC | PROVINCES:
        return None
    if re.fullmatch(r"[\d.,%\s]+", s):
        return None
    if re.match(
        r"^(kabupaten|kota|provinsi|kecamatan|rp\s|longitude|latitude|kode kbli)\b",
        s, re.I
    ):
        return None
    if re.search(
        r"(disukai|sukai proyek ini|pengunjung|tahun\s*:|informasi|nilai investasi|npv|irr)",
        s, re.I
    ):
        return None
    return s


def _jsonld_breadcrumb(soup: BeautifulSoup) -> str | None:
    def visit(obj):
        if isinstance(obj, list):
            for value in obj:
                yield from visit(value)
        elif isinstance(obj, dict):
            types = obj.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if "BreadcrumbList" in types:
                yield obj
            for value in obj.values():
                yield from visit(value)

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        for breadcrumb in visit(data):
            parts = breadcrumb.get("itemListElement", [])
            if not isinstance(parts, list):
                continue
            sorted_parts = sorted(
                (part for part in parts if isinstance(part, dict)),
                key=lambda part: int(part.get("position", 0))
                if str(part.get("position", "0")).isdigit() else 0
            )
            for part in reversed(sorted_parts):
                item = part.get("item")
                name = part.get("name") or (
                    item.get("name") if isinstance(item, dict) else None
                )
                title = clean_title(name)
                if title:
                    return title
    return None


def _dom_breadcrumb(soup: BeautifulSoup) -> str | None:
    # Select only recognized breadcrumb containers, never all h2/h3 headings.
    selectors = [
        '[aria-current="page"]',
        'nav[aria-label*="breadcrumb" i]',
        '.breadcrumb',
        '[class*="breadcrumb" i]',
    ]
    for selector in selectors:
        for container in soup.select(selector):
            if container.get("aria-current") == "page":
                text = clean_title(container.get_text(" ", strip=True))
                if text:
                    return text
            parts = container.select("li, [aria-current='page']")
            if not parts:
                continue
            for part in reversed(parts):
                title = clean_title(part.get_text(" ", strip=True))
                if title:
                    return title
    return None


def _near_project_info(soup: BeautifulSoup) -> str | None:
    # Search in the rendered text *before* the detail section ("Informasi").
    # The last "Peluang Investasi" in a breadcrumb followed by the project
    # name is a stronger signal than an arbitrary heading anywhere on page.
    raw = [" ".join(s.split()) for s in soup.stripped_strings]
    info_indexes = [
        i for i, value in enumerate(raw)
        if value.casefold().strip(" :") == "informasi"
    ]
    for info in info_indexes:
        # Project details have KBLI/financial/coordinate labels nearby.
        after = " ".join(raw[info + 1:info + 14]).lower()
        if not any(marker in after for marker in (
            "kode kbli", "nilai investasi", "longitude", "latitude"
        )):
            continue
        start = max(0, info - 35)
        for index in range(info - 1, start - 1, -1):
            if raw[index].casefold() != "peluang investasi":
                continue
            # Require "Beranda" in the same short breadcrumb sequence; this
            # disambiguates navigation tabs from the current-page breadcrumb.
            if "beranda" not in {
                value.casefold() for value in raw[max(0, index - 6):index]
            }:
                continue
            for candidate in raw[index + 1:min(info, index + 5)]:
                title = clean_title(candidate)
                if title:
                    return title
    return None


def get_project_title(html: str) -> tuple[str | None, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = _jsonld_breadcrumb(soup)
    if title:
        return title, "jsonld_breadcrumb"

    for element in soup.select("script,style,noscript,footer"):
        element.decompose()
    title = _dom_breadcrumb(soup)
    if title:
        return title, "dom_breadcrumb"
    title = _near_project_info(soup)
    if title:
        return title, "breadcrumb_text_near_details"
    return None, "not_found"
