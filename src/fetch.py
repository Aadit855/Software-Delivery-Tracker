"""Fetch issues and pull requests from public GitHub repos into data/raw, with a snapshot manifest.

Live API data cannot be checksum-pinned like a static file, so each run writes a manifest
that records the snapshot time, the window, and row counts. Set GITHUB_TOKEN to raise the
rate limit from 60 to 5,000 requests per hour.
"""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
REPOS = ["pallets/flask", "psf/requests", "pydantic/pydantic"]
SINCE = "2025-10-01T00:00:00Z"  # 12-month window ending at the snapshot
MAX_PAGES = 12  # 1,200 items per repo; keeps the run inside the anonymous rate limit
PER_PAGE = 100


def get(url: str) -> list:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "delivery-metrics-portfolio"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        if err.code == 403:
            raise SystemExit("GitHub rate limit reached. Wait an hour or set GITHUB_TOKEN.") from err
        raise


def fetch_repo(repo: str) -> tuple[list, bool]:
    """Return (items, truncated). GitHub refuses list pages past ~1,000 results with HTTP 422."""
    items = []
    for page in range(1, MAX_PAGES + 1):
        url = (
            f"https://api.github.com/repos/{repo}/issues?state=all"
            f"&since={SINCE}&per_page={PER_PAGE}&page={page}"
        )
        try:
            batch = get(url)
        except urllib.error.HTTPError as err:
            if err.code == 422:
                return items, True
            raise
        items.extend(batch)
        if len(batch) < PER_PAGE:
            return items, False
        time.sleep(0.5)
    return items, True


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    snapshot = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest = {"snapshot_utc": snapshot, "window_since": SINCE, "repos": {}}
    for repo in REPOS:
        items, truncated = fetch_repo(repo)
        slug = repo.replace("/", "__")
        (RAW / f"{slug}.json").write_text(json.dumps(items))
        manifest["repos"][repo] = {"items": len(items), "truncated_at_cap": truncated}
        print(f"{repo}: {len(items)} items{' (truncated at cap)' if truncated else ''}")
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
