"""Checks for the delivery-metric pipeline. Run from the project root: python -m pytest -q

These tests use the snapshot in data/raw. They verify internal consistency, not live GitHub state.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from build import build, flatten  # noqa: E402

RAW = ROOT / "data" / "raw"


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    if not (RAW / "manifest.json").exists():
        pytest.skip("Run src/fetch.py first to create the snapshot.")
    return build(tmp_path_factory.mktemp("wh") / "test.duckdb")


def test_flattened_count_matches_raw_json():
    raw_total = sum(len(json.loads(p.read_text())) for p in RAW.glob("*__*.json"))
    assert len(flatten()) == raw_total


def test_items_are_unique_per_repo(con):
    dupes = con.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT (repo, number)) FROM stg_items"
    ).fetchone()[0]
    assert dupes == 0


def test_open_items_have_no_close_date(con):
    bad = con.execute(
        "SELECT COUNT(*) FROM stg_items WHERE state = 'open' AND closed_at IS NOT NULL"
    ).fetchone()[0]
    assert bad == 0


def test_closed_items_close_after_creation(con):
    bad = con.execute(
        "SELECT COUNT(*) FROM pop_items WHERE closed_at < created_at"
    ).fetchone()[0]
    assert bad == 0


def test_population_respects_coverage_cutoff(con):
    before = con.execute(
        "SELECT COUNT(*) FROM pop_items i, coverage c WHERE i.created_at < c.covered_from"
    ).fetchone()[0]
    assert before == 0


def test_open_backlog_matches_open_population(con):
    open_pop = con.execute("SELECT COUNT(*) FROM pop_items WHERE state = 'open'").fetchone()[0]
    backlog = con.execute("SELECT COUNT(*) FROM mart_open_backlog").fetchone()[0]
    assert backlog == open_pop


def test_bug_label_variant_is_detected(con):
    # pydantic labels its bugs "bug V2"; the exact-match version of this check would miss them.
    assert con.execute(
        "SELECT COUNT(*) FROM stg_items WHERE repo = 'pydantic/pydantic' AND is_bug"
    ).fetchone()[0] > 0
