"""Read publicly disclosed BKPM download metadata; do NOT submit user forms.

This parser never records HAR cookies, CSRF tokens, or personal information.
A declared download URL is NOT proof that a file was downloaded or that the
site's disclaimer and terms can be bypassed.
"""
from __future__ import annotations
import json
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup

HOST = "data.bkpm.go.id"
PATH = re.compile(r"^/dataset/generate-download-zip/([0-9a-fA-F-]{36})/file$")
ONCLICK = re.compile(
    r"""handleUnduhDisclamer\(\s*event\s*,\s*['"]file['"]\s*,\s*['"]([0-9a-fA-F-]{36})['"]\s*,\s*(\d+)\s*\)"""
)

def accepted_public_link(url: str) -> tuple[str, str] | None:
    from urllib.parse import parse_qs
    p = urlparse(url)
    if p.scheme != "https" or p.hostname != HOST or p.username or p.password or p.port:
        return None
    match = PATH.fullmatch(p.path)
    if not match:
        return None
    query = parse_qs(p.query)
    if set(query).difference({"upload_file_id"}):
        return None
    if "upload_file_id" in query and not all(
        x.isdecimal() for x in query["upload_file_id"]
    ):
        return None
    file_id = query.get("upload_file_id", [""])[0]
    return match.group(1), file_id

def _walk_urls(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get("contentUrl"), str):
            yield obj["contentUrl"]
        for value in obj.values():
            yield from _walk_urls(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_urls(value)

def extract_download_manifest(html: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    declared = {}
    buttons = {}
    requires_form = "store-disclamer" in html

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            tree = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        for url in _walk_urls(tree):
            accepted = accepted_public_link(url)
            if accepted:
                declared[accepted[0]] = url

    # Buttons actually present in HTML, not inferred from ranges of IDs.
    for button in soup.select("[onclick]"):
        match = ONCLICK.search(button.get("onclick", ""))
        if not match:
            continue
        uid, file_id = match.groups()
        url = (
            "https://data.bkpm.go.id/dataset/generate-download-zip/"
            f"{uid}/file?upload_file_id={file_id}"
        )
        if accepted_public_link(url):
            buttons[(uid, file_id)] = url

    ids = sorted(set(declared) | {uid for uid, _ in buttons})
    rows = []
    for uid in ids:
        sub = [(fid, url) for (identifier, fid), url in buttons.items()
               if identifier == uid]
        if not sub:
            sub = [("", "")]
        for file_id, button_url in sub:
            rows.append({
                "dataset_page": page_url,
                "source_uuid": uid,
                "upload_file_id": file_id,
                "jsonld_content_url": declared.get(uid, ""),
                "button_url": button_url,
                "disclaimer_form_present": requires_form,
                "download_verified": False,
                "status": "declared_in_public_html_only",
            })
    return rows
