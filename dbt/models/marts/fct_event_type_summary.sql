-- Fact table: GitHub event type distribution summary
-- Powers the categorical distribution tile in Looker Studio dashboard.
-- Materialized as TABLE for fast dashboard queries.

with type_counts as (
    select
        event_type,
        count(*)                    as event_count,
        count(distinct actor_login) as unique_actors,
        count(distinct repo_name)   as unique_repos,
        min(event_date)             as first_seen_date,
        max(event_date)             as last_seen_date
    from {{ ref('stg_github_events') }}
    group by event_type
),

with_pct as (
    select
        event_type,
        event_count,
        unique_actors,
        unique_repos,
        first_seen_date,
        last_seen_date,
        round(
            event_count * 100.0 / sum(event_count) over (),
            2
        ) as pct_of_total
    from type_counts
)

select *
from with_pct
order by event_count desc
