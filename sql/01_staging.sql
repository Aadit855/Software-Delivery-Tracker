-- 01_staging.sql
-- Typed work items (issues and pull requests share one table). Grain: one row per repo + number.

CREATE OR REPLACE TABLE stg_items AS
SELECT
    repo,
    number,
    kind,
    state,
    CAST(created_at AS TIMESTAMP)                    AS created_at,
    CAST(closed_at AS TIMESTAMP)                     AS closed_at,
    comments,
    labels,
    is_bug,
    title,
    html_url
FROM raw_items;

