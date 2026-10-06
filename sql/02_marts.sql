-- 02_marts.sql
-- Delivery metrics. Cycle time = closed_at - created_at, measured only on items created inside the covered window.

CREATE OR REPLACE TABLE pop_items AS
SELECT i.*
FROM stg_items i, coverage c
WHERE i.created_at >= c.covered_from;

-- Weekly throughput: items closed per ISO week, by kind.
CREATE OR REPLACE TABLE mart_weekly_throughput AS
SELECT
    date_trunc('week', closed_at)::DATE              AS week_start,
    kind,
    COUNT(*)                                         AS closed_items
FROM pop_items
WHERE closed_at IS NOT NULL
GROUP BY ALL
ORDER BY week_start;

-- Cycle time for closed items, by repo and kind.
CREATE OR REPLACE TABLE mart_cycle_time AS
SELECT
    repo,
    kind,
    COUNT(*)                                                       AS closed_items,
    MEDIAN(date_diff('second', created_at, closed_at)) / 86400.0          AS median_days,
    QUANTILE_CONT(date_diff('second', created_at, closed_at), 0.85) / 86400.0 AS p85_days
FROM pop_items
WHERE closed_at IS NOT NULL
GROUP BY ALL
ORDER BY repo, kind;

-- Open backlog at the snapshot, with age. Basis for WIP and the stale-work risk register.
CREATE OR REPLACE TABLE mart_open_backlog AS
SELECT
    i.repo,
    i.number,
    i.kind,
    i.is_bug,
    i.title,
    i.html_url,
    i.created_at,
    date_diff('day', i.created_at, r.snapshot_utc)   AS age_days
FROM pop_items i, run_meta r
WHERE i.state = 'open';
