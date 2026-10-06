"""Flatten the raw GitHub JSON into DuckDB and build the delivery-metric marts."""
import json
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB = ROOT / "warehouse" / "delivery.duckdb"
SNAPSHOT_FILE = RAW / "manifest.json"


def flatten() -> pd.DataFrame:
    rows = []
    for path in sorted(RAW.glob("*__*.json")):
        repo = path.stem.replace("__", "/")
        for item in json.loads(path.read_text()):
            labels = [label["name"] for label in item.get("labels", [])]
            rows.append(
                {
                    "repo": repo,
                    "number": item["number"],
                    "kind": "pull_request" if "pull_request" in item else "issue",
                    "state": item["state"],
                    "created_at": item["created_at"],
                    "closed_at": item.get("closed_at"),
                    "comments": item.get("comments", 0),
                    "labels": ", ".join(labels),
                    # Matches "bug", "type: bug", and variants such as "bug V2" used by pydantic.
                    "is_bug": any(label.lower().startswith(("bug", "type: bug")) for label in labels),
                    "title": item["title"],
                    "html_url": item["html_url"],
                }
            )
    return pd.DataFrame(rows)


def covered_from(items: pd.DataFrame, manifest: dict) -> str:
    """Latest 'earliest item' date among repos that hit the pagination cap.

    A capped repo only returns its most recent items, so any period before its earliest
    returned item is incomplete. Repos that were not capped are complete over the window and
    do not limit the analysis start.
    """
    capped = [repo for repo, info in manifest["repos"].items() if info["truncated_at_cap"]]
    earliest = items[items["repo"].isin(capped)].groupby("repo")["created_at"].min()
    return earliest.max()


def build(db_path: Path = DB) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    items = flatten()
    manifest = json.loads(SNAPSHOT_FILE.read_text())
    con.register("items_df", items)
    con.execute("CREATE OR REPLACE TABLE raw_items AS SELECT * FROM items_df")
    snapshot_utc = manifest["snapshot_utc"][:19].replace("T", " ")  # naive UTC, no tz conversion needed
    con.execute(f"CREATE OR REPLACE TABLE run_meta AS SELECT TIMESTAMP '{snapshot_utc}' AS snapshot_utc")
    con.execute(
        f"CREATE OR REPLACE TABLE coverage AS SELECT TIMESTAMP '{covered_from(items, manifest)[:19].replace('T', ' ')}' AS covered_from"
    )
    for sql_file in ("01_staging.sql", "02_marts.sql"):
        con.execute((ROOT / "sql" / sql_file).read_text())
    return con


if __name__ == "__main__":
    con = build()
    n = con.execute("SELECT COUNT(*) FROM stg_items").fetchone()[0]
    print(f"Built {DB.relative_to(ROOT)} with {n:,} items")
