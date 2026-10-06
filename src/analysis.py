"""Delivery metrics, the open-bug risk register, and charts for the three repos."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from build import build  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
FIG = ROOT / "figures"
STALE_DAYS = 90


def compute(con) -> dict:
    window = con.execute("SELECT covered_from, snapshot_utc FROM coverage, run_meta").fetchone()
    closed_in_window = con.execute(
        "SELECT COUNT(*) FROM pop_items WHERE closed_at IS NOT NULL"
    ).fetchone()[0]
    weeks = con.execute(
        "SELECT COUNT(DISTINCT week_start) FROM mart_weekly_throughput"
    ).fetchone()[0]
    throughput = con.execute(
        "SELECT ROUND(SUM(closed_items) / ?, 1) FROM mart_weekly_throughput", [weeks]
    ).fetchone()[0]
    cycle = con.execute(
        "SELECT repo, kind, closed_items, ROUND(median_days,1), ROUND(p85_days,1) "
        "FROM mart_cycle_time ORDER BY repo, kind"
    ).fetchall()
    open_wip = con.execute(
        "SELECT COUNT(*), SUM((age_days > ?)::INT), SUM(is_bug::INT), "
        "SUM((is_bug AND age_days > ?)::INT), MEDIAN(age_days) FROM mart_open_backlog",
        [STALE_DAYS, STALE_DAYS],
    ).fetchone()
    by_repo_open = con.execute(
        "SELECT repo, COUNT(*), SUM((age_days > ?)::INT) FROM mart_open_backlog "
        "GROUP BY repo ORDER BY repo", [STALE_DAYS]
    ).fetchall()
    register = con.execute(
        "SELECT repo, number, kind, title, age_days, html_url FROM mart_open_backlog "
        "WHERE is_bug AND age_days > ? ORDER BY age_days DESC LIMIT 50", [STALE_DAYS]
    ).fetchall()
    weekly = con.execute(
        "SELECT week_start, SUM(closed_items) FROM mart_weekly_throughput "
        "GROUP BY week_start ORDER BY week_start"
    ).fetchall()
    return {
        "covered_from": str(window[0]),
        "snapshot_utc": str(window[1]),
        "closed_items_in_window": closed_in_window,
        "avg_items_closed_per_week": throughput,
        "cycle_time_days": [list(r) for r in cycle],
        "open_items": open_wip[0],
        "open_items_stale_over_90d": int(open_wip[1] or 0),
        "open_bugs": int(open_wip[2] or 0),
        "open_bugs_stale_over_90d": int(open_wip[3] or 0),
        "median_open_age_days": round(open_wip[4], 1) if open_wip[4] is not None else None,
        "open_by_repo": [list(r) for r in by_repo_open],
        "risk_register_top": [list(r) for r in register],
        "weekly_closed": [[str(w), int(n)] for w, n in weekly],
    }


def write_register(register: list) -> None:
    OUT.mkdir(exist_ok=True)
    lines = ["repo,number,kind,age_days,title,url"]
    for repo, number, kind, title, age, url in register:
        safe_title = '"' + title.replace('"', '""') + '"'
        lines.append(f"{repo},{number},{kind},{age},{safe_title},{url}")
    (OUT / "risk_register_open_bugs.csv").write_text("\n".join(lines) + "\n")


def charts(metrics: dict) -> None:
    FIG.mkdir(exist_ok=True)
    weekly = metrics["weekly_closed"]
    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.bar([w[0] for w in weekly], [w[1] for w in weekly], width=5, color="#2a6f97")
    ax.set_title("Items closed per week (all three repos)")
    ax.set_ylabel("Closed items")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(FIG / "weekly_throughput.png", dpi=150)
    plt.close(fig)


def main() -> None:
    con = build()
    metrics = compute(con)
    OUT.mkdir(exist_ok=True)
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))
    write_register(metrics["risk_register_top"])
    charts(metrics)
    print(json.dumps({k: v for k, v in metrics.items() if k != "weekly_closed"}, indent=2, default=str))


if __name__ == "__main__":
    main()
