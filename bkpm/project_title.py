"""Extract BKPM project titles from the project page, not the generic H1.

Do not substitute guessed/project-ID-based names. Ambiguous titles remain null.
"""
from __future__ import annotations

import re
from bs4 import BeautifulSoup

GENERIC = {
    "beranda", "peluang investasi", "potensi investasi regional",
    "informasi", "deskripsi", "insentif", "infografis & infomemo",
    "galeri", "kontak", "loading", "unduh dokumen",
    "industri", "agro industri", "infrastruktur", "pariwisata",
    "jasa dan kawasan", "energi terbarukan", "sumber daya alam",
    "perdagangan karbon", "primer", "sekunder", "tersier",
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
    if re.match(r"^(kabupaten|kota|provinsi|kecamatan|rp\s|longitude|latitude|kode kbli)\b", s, re.I):
        return None
    if re.search(r"(disukai|sukai proyek ini|pengunjung|tahun\s*:|informasi)", s, re.I):
        return None
    return s


def get_project_title(html: str) -> tuple[str | None, str]:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.select("script,style,noscript,footer"):
        element.decompose()

    # Detail title is usually a heading distinct from the generic H1.
    for el in soup.select("main h2, main h3, main h4, main h5, main h6, h2, h3, h4, h5, h6"):
        text = clean_title(el.get_text(" ", strip=True))
        if text:
            return text, "detail_heading"

    # Some page layouts use a breadcrumb instead of heading tags.
    for el in soup.select('[aria-current="page"], nav[aria-label*="breadcrumb"] li:last-child, .breadcrumb li:last-child, [class*="breadcrumb"] li:last-child'):
        text = clean_title(el.get_text(" ", strip=True))
        if text:
            return text, "breadcrumb"

    # On the detail page the project name precedes the "Informasi"
    # label. Restrict to a short window and reject geography/category/UI.
    raw_strings = [" ".join(s.split()) for s in soup.stripped_strings]
    label_positions = [i for i, s in enumerate(raw_strings)
                       if s.casefold() == "informasi"]
    if label_positions:
        i = label_positions[0]
        window = raw_strings[max(0, i-16):i]
        candidates = []
        for idx, raw in enumerate(window):
            text = clean_title(raw)
            if text:
                candidates.append((len(text), -idx, text))
        if candidates:
            # Prefer informative phrase, but do not invent a title.
            candidates.sort(reverse=True)
            return candidates[0][2], "pre_information_text"

    for tag in soup.select('meta[property="og:title"], meta[name="twitter:title"]'):
        text = clean_title(tag.get("content"))
        if text:
            return text, "metadata"

    return None, "not_found"
