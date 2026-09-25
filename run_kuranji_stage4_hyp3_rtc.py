#!/usr/bin/env python3
"""Submit, monitor and download Kuranji Stage-4 Sentinel-1 RTC products via ASF HyP3.

Why HyP3
--------
The Kuranji VPS does not currently have ESA SNAP gpt/Java/GDAL installed, while
ASF HyP3 can generate analysis-ready Sentinel-1 RTC GeoTIFFs from the selected
GRD scenes. This avoids downloading and locally preprocessing the large raw GRD
archives.

Security
--------
Authentication uses an Earthdata Login bearer token entered through a hidden
prompt (`HyP3(prompt='token')`). The token is NOT written to disk by this script.
Do not commit tokens or passwords to the repository.

Input
-----
data/work/kuranji/17_stage4_sentinel1_prepare/SELECTED_SENTINEL1_TRIPLET.csv

Selected RTC settings
---------------------
- radiometry       : gamma0
- resolution       : 20 m
- scale            : power
- dem_matching     : True
- include_inc_map  : True
- speckle_filter   : False
- DEM              : Copernicus

Rationale: 20 m is consistent with the effective spatial resolution of IW GRD,
gamma0 RTC reduces terrain-related radiometric effects, and filtering is deferred
so exactly the same filter/change workflow can be applied later to all dates.

Usage
-----
Install once:
    python -m pip install hyp3_sdk

Check authentication/access/credits:
    python run_kuranji_stage4_hyp3_rtc.py --check

Submit the 3 RTC jobs:
    python run_kuranji_stage4_hyp3_rtc.py --submit

Check status:
    python run_kuranji_stage4_hyp3_rtc.py --status

Wait for completion and download:
    python run_kuranji_stage4_hyp3_rtc.py --watch-download

Outputs
-------
data/work/kuranji/18_stage4_sentinel1_rtc/
  hyp3_job_manifest.json
  products/   # downloaded HyP3 RTC ZIPs/products
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREP = ROOT / "data/work/kuranji/17_stage4_sentinel1_prepare"
MANIFEST = PREP / "SELECTED_SENTINEL1_TRIPLET.csv"
OUT = ROOT / "data/work/kuranji/18_stage4_sentinel1_rtc"
PRODUCTS = OUT / "products"
STATE = OUT / "hyp3_job_manifest.json"
OUT.mkdir(parents=True, exist_ok=True)
PRODUCTS.mkdir(parents=True, exist_ok=True)

JOB_NAMES = {
    "PRE": "KURANJI_S1_PRE_RTC",
    "EVENT": "KURANJI_S1_EVENT_RTC",
    "POST": "KURANJI_S1_POST_RTC",
}

RTC_OPTIONS = {
    "dem_matching": True,
    "include_dem": False,
    "include_inc_map": True,
    "include_rgb": False,
    "include_scattering_area": False,
    "radiometry": "gamma0",
    "resolution": 20,
    "scale": "power",
    "speckle_filter": False,
    "dem_name": "copernicus",
}


def load_sdk():
    try:
        import hyp3_sdk as sdk
        return sdk
    except ImportError:
        print("ERROR: hyp3_sdk is not installed in this virtual environment.")
        print("Install with:")
        print("  python -m pip install hyp3_sdk")
        sys.exit(2)


def load_selected():
    if not MANIFEST.exists():
        raise FileNotFoundError(MANIFEST)
    with MANIFEST.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    by_role = {str(r.get("role", "")).upper(): r for r in rows}
    missing = [r for r in ["PRE", "EVENT", "POST"] if r not in by_role]
    if missing:
        raise RuntimeError(f"Missing role(s) in selected triplet: {missing}")
    return by_role


def get_hyp3(sdk):
    print("Earthdata Login bearer token will be requested securely.")
    print("The token is not saved by this script.\n")
    return sdk.HyP3(prompt="token")


def summarize_job(job):
    return {
        "job_id": getattr(job, "job_id", ""),
        "name": getattr(job, "name", ""),
        "status_code": getattr(job, "status_code", ""),
        "request_time": str(getattr(job, "request_time", "")),
        "expiration_time": str(getattr(job, "expiration_time", "")),
        "job_type": getattr(job, "job_type", ""),
        "files": [
            {
                "filename": getattr(f, "filename", ""),
                "url": getattr(f, "url", ""),
                "size": getattr(f, "size", ""),
            }
            for f in (getattr(job, "files", None) or [])
        ],
    }


def find_named_jobs(hyp3):
    result = {}
    for role, name in JOB_NAMES.items():
        batch = hyp3.find_jobs(name=name)
        result[role] = batch
    return result


def save_state(selected, jobs_by_role, credits=None):
    state = {
        "selected_scenes": {
            role: {
                "scene_name": selected[role].get("scene_name", ""),
                "platform": selected[role].get("platform", ""),
                "acquisition_utc": selected[role].get("acquisition_utc", ""),
                "coverage_pct": selected[role].get("coverage_pct", ""),
            }
            for role in ["PRE", "EVENT", "POST"]
        },
        "rtc_options": RTC_OPTIONS,
        "remaining_credits_at_check": credits,
        "jobs": {},
    }
    for role, batch in jobs_by_role.items():
        state["jobs"][role] = [summarize_job(j) for j in batch]
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def print_selected(selected):
    print("=== SELECTED SENTINEL-1 SCENES ===")
    for role in ["PRE", "EVENT", "POST"]:
        r = selected[role]
        print(f"{role:<5}: {r.get('scene_name','')}")
        print(f"       {r.get('acquisition_utc','')} | {r.get('platform','')} | coverage={r.get('coverage_pct','')}%")


def check_access(hyp3):
    info = hyp3.my_info()
    credits = hyp3.check_credits()
    print("\n=== HYP3 ACCESS ===")
    print("Authenticated user :", info.get("user_id") or info.get("username") or "OK")
    print("Remaining credits  :", credits)
    return credits


def do_check(hyp3, selected):
    credits = check_access(hyp3)
    print_selected(selected)
    try:
        costs = hyp3.costs()
        print("\nHyP3 costs endpoint available: YES")
        print(json.dumps(costs, indent=2)[:3000])
    except Exception as e:
        print("\nHyP3 costs endpoint check: unavailable/non-fatal:", e)
    jobs = find_named_jobs(hyp3)
    save_state(selected, jobs, credits)
    print("\nState written:", STATE)


def do_submit(hyp3, selected):
    credits = check_access(hyp3)
    print_selected(selected)
    print("\nRTC options:")
    print(json.dumps(RTC_OPTIONS, indent=2))

    existing = find_named_jobs(hyp3)
    submitted = {}
    for role in ["PRE", "EVENT", "POST"]:
        if len(existing[role]) > 0:
            print(f"\n{role}: existing HyP3 job(s) already found with name {JOB_NAMES[role]}; not resubmitting.")
            for existing_job in existing[role]:
                print("  job_id:", getattr(existing_job, "job_id", ""))
                print("  status:", getattr(existing_job, "status_code", ""))
            submitted[role] = existing[role]
            continue

        scene = selected[role].get("scene_name", "")
        if not scene:
            raise RuntimeError(f"Missing scene_name for {role}")

        print(f"\nSubmitting {role}: {scene}")
        batch = hyp3.submit_rtc_job(
            granule=scene,
            name=JOB_NAMES[role],
            **RTC_OPTIONS,
        )

        # hyp3_sdk v7.7.8 returns a Batch, even for one submitted RTC job.
        if len(batch) == 0:
            raise RuntimeError(f"HyP3 returned an empty Batch after submitting {role}")
        for submitted_job in batch:
            print("  job_id:", getattr(submitted_job, "job_id", ""))
            print("  status:", getattr(submitted_job, "status_code", ""))

        # Re-query by stable name so reruns remain idempotent and the state file
        # always contains the server-side representation of the job.
        submitted[role] = hyp3.find_jobs(name=JOB_NAMES[role])

    save_state(selected, submitted, credits)
    print("\nSubmitted/state saved:", STATE)
    print("Next: python run_kuranji_stage4_hyp3_rtc.py --status")


def do_status(hyp3, selected):
    credits = check_access(hyp3)
    batches = find_named_jobs(hyp3)
    print("\n=== JOB STATUS ===")
    for role in ["PRE", "EVENT", "POST"]:
        batch = batches[role]
        if len(batch) == 0:
            print(f"{role:<5}: NO JOB FOUND")
            continue
        for job in batch:
            print(f"{role:<5}: {job.job_id}  {job.status_code}  name={job.name}")
    save_state(selected, batches, credits)
    print("\nState updated:", STATE)


def do_watch_download(hyp3, selected):
    credits = check_access(hyp3)
    batches = find_named_jobs(hyp3)
    missing = [r for r in ["PRE", "EVENT", "POST"] if len(batches[r]) == 0]
    if missing:
        raise RuntimeError(f"No submitted job found for: {missing}. Run --submit first.")

    print("\nWatching jobs until completion...")
    completed = {}
    for role in ["PRE", "EVENT", "POST"]:
        print(f"\nWatching {role}...")
        batch = hyp3.watch(batches[role])
        completed[role] = batch
        for job in batch:
            print(f"  {job.job_id}: {job.status_code}")

    failed = []
    for role, batch in completed.items():
        for job in batch:
            if str(job.status_code).upper() == "FAILED":
                failed.append((role, job.job_id))
    if failed:
        save_state(selected, completed, credits)
        raise RuntimeError(f"HyP3 job failure(s): {failed}")

    print("\nDownloading completed RTC products to:", PRODUCTS)
    for role in ["PRE", "EVENT", "POST"]:
        batch = completed[role]
        succeeded = batch.filter_jobs(succeeded=True, pending=False, running=False, failed=False)
        if len(succeeded) == 0:
            print(f"  {role}: no succeeded product to download")
            continue
        files = succeeded.download_files(location=PRODUCTS)
        print(f"  {role}: downloaded {len(files)} file(s)")
        for p in files:
            print("     ", p)

    save_state(selected, completed, credits)
    print("\nDONE. State:", STATE)
    print("Products:", PRODUCTS)
    print("NEXT: inspect/unzip RTC products and build aligned VV/VH PRE-EVENT-POST change rasters clipped to DAS.")


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--submit", action="store_true")
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--watch-download", action="store_true")
    args = parser.parse_args()

    sdk = load_sdk()
    selected = load_selected()
    hyp3 = get_hyp3(sdk)

    try:
        if args.check:
            do_check(hyp3, selected)
        elif args.submit:
            do_submit(hyp3, selected)
        elif args.status:
            do_status(hyp3, selected)
        elif args.watch_download:
            do_watch_download(hyp3, selected)
    except Exception as e:
        print("\nERROR:", e)
        print("\nIf this is an authentication/access error:")
        print("1. Confirm you have a NASA Earthdata Login account.")
        print("2. Generate a current Earthdata bearer token.")
        print("3. New HyP3 users may need to request/activate On Demand access in ASF Vertex.")
        print("4. Do NOT paste credentials or tokens into GitHub or chat.")
        raise


if __name__ == "__main__":
    main()
