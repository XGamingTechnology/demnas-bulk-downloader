"""Optional Chromium rendering for public BKPM project pages.

Use only for previously observed, public URLs, and do not bypass
authentication or challenge pages. No cookies or session data are persisted.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

WAIT_COORDINATES_JS = r"""() => {
  const text = document.body ? document.body.innerText : "";
  return /Longitude\s*[:：]?\s*-?\d+(?:[.,]\d+)?/i.test(text)
      && /Latitude\s*[:：]?\s*-?\d+(?:[.,]\d+)?/i.test(text);
}"""


class BrowserRenderer:
    def __init__(self, timeout_ms: int = 25000):
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._context = None

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright belum terpasang: python -m pip install playwright"
            ) from exc
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=True)
            self._context = self._browser.new_context(
                locale="id-ID", service_workers="block"
            )
        except Exception:
            self._playwright.stop()
            raise
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def get_html(self, url: str) -> tuple[str, int, str]:
        if urlparse(url).hostname != "regionalinvestment.bkpm.go.id":
            raise ValueError("Host tidak diizinkan untuk browser render")
        if "/peluang_investasi/detailed/" not in urlparse(url).path:
            raise ValueError("URL bukan detail peluang investasi")
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        page = self._context.new_page()
        try:
            response = page.goto(
                url, wait_until="domcontentloaded", timeout=self.timeout_ms
            )
            if response is None:
                raise RuntimeError("Tidak ada respons navigasi halaman")
            if response.status in (401, 403, 429):
                raise RuntimeError(
                    f"HTTP {response.status}: akses ditolak; tidak mencoba bypass"
                )
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}")
            wait_state = "coords_detected"
            try:
                page.wait_for_function(
                    WAIT_COORDINATES_JS, timeout=self.timeout_ms
                )
            except PlaywrightTimeout:
                wait_state = "timeout_waiting_for_coordinates"
            html = page.content()
            return html, response.status, wait_state
        finally:
            page.close()
