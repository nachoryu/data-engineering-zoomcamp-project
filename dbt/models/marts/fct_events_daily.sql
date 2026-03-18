-- Fact table: daily GitHub activity summary
-- Powers the time-series tile in Looker Studio dashboard.
-- Materialized as TABLE for fast dashboard queries.

with daily as (
    select
        event_date,
        count(*)                                        as total_events,
        count(distinct actor_login)                     as unique_actors,
        count(distinct repo_name)                       as unique_repos,

        -- Event type breakdown per day
        countif(event_type = 'PushEvent')               as push_events,
        countif(event_type = 'PullRequestEvent')        as pr_events,
        countif(event_type = 'IssuesEvent')             as issue_events,
        countif(event_type = 'WatchEvent')              as watch_events,
        countif(event_type = 'ForkEvent')               as fork_events,
        countif(event_type = 'CreateEvent')             as create_events,
        countif(event_type = 'IssueCommentEvent')       as issue_comment_events,
        countif(event_type = 'PullRequestReviewEvent')  as pr_review_events

    from {{ ref('stg_github_events') }}
    group by event_date
)

select
    event_date,
    total_events,
    unique_actors,
    unique_repos,
    push_events,
    pr_events,
    issue_events,
    watch_events,
    fork_events,
    create_events,
    issue_comment_events,
    pr_review_events,

    -- 7-day rolling average for smoothed trend line
    avg(total_events) over (
        order by event_date
        rows between 6 preceding and current row
    )                                                   as total_events_7d_avg

from daily
order by event_date
