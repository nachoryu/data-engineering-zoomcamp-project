-- Fact table: hourly activity heatmap data
-- Optional third tile: shows which hours of the day are most active globally.

select
    event_hour,
    event_day_of_week,
    count(*)                    as total_events,
    count(distinct actor_login) as unique_actors
from {{ ref('stg_github_events') }}
group by event_hour, event_day_of_week
order by event_day_of_week, event_hour
