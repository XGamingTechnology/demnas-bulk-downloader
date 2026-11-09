# BKPM Investment Inventory (experimental)

This module inventories **publicly accessible HTML metadata and explicitly linked pages**, from BKPM's official portals. It does NOT claim to download all investment data, bypass access controls, discover private endpoints, or retrieve the full CSV/JSON datasets from JavaScript download buttons.

## Sources

- https://regionalinvestment.bkpm.go.id/peluang_investasi — investment opportunities
- https://regionalinvestment.bkpm.go.id/daerah — province/regional profile
- https://regionalinvestment.bkpm.go.id/hilirisasi — downstream industrialization
- https://regionalinvestment.bkpm.go.id/kawasan — industrial/economic zones
- https://data.bkpm.go.id/dataset — official Satu Data catalog

Several **publicly observed** detail URLs are seeded as leads, not inferred from sequential IDs. Live existence/fields must be verified by running the collector. All source fields remain raw strings unless validated.

## Run on VPS

```bash
cd ~/geo-experiments/bkpm-demnas
source .venv/bin/activate
python -m pip install requests beautifulsoup4
python -m unittest discover -s bkpm/tests -v
python -m bkpm.investment_inventory --catalog-pages 5 --max-details 30
```

Output in `data/bkpm/investment/`:

- `audit.json` — counts of successes, failures and limitations
- `pages.json`, `pages.csv` — all attempted pages, HTTP status and hashes
- `details.csv` — conservative parsed metadata (not a bulk dataset export)
- `discovered_urls.txt` — URL leads observed from public pages

Use `--catalog-pages 12 --max-details 150` for broader catalog metadata after checking initial results. Requests are deliberately rate-limited (at least one second per request); HTTP 403/429 halts attempts to that host. Do not run in repeated loops or parallel jobs. For new leads, create a text file of URLs actually observed in a browser and pass `--seeds-file observed.txt`. It does not generate URLs by guessing IDs.

## How to acquire the actual data

1. On the official dataset detail page, identify the specific CSV/JSON file and license/use conditions.
2. Inspect the browser Network panel only when opening a public download link, and preserve the exact response URL, HTTP status, MIME type, filename and dataset metadata.
3. Download using the website's own public links, after checking any applicable rate limits and terms.
4. Store per-resource metadata: dataset title, reporting period, source URL, units (Rp, juta, miliar, trillion), PMA/PMDN, geographic hierarchy, and publication date.
5. Audit for duplicate periods, revised data, missing values and coordinate correctness before joining or aggregating data.

**Do not merge opportunity investment value into realized LKPM value.** BKPM province boundaries observed to date contain 34 unique province names; validate against official current administrative boundaries before spatial joins.

## Important

This is a separate exploratory branch; `main` and the existing DEMNAS/BHUMI worktree remain untouched. No DEMNAS raster is needed for investment metadata inventory.
