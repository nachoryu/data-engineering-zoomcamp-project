-- Staging model: clean and flatten raw GitHub Archive events
-- Materialised as a VIEW to avoid data duplication;
-- downstream mart queries filter by date so BigQuery partition pruning still applies.

with source as (
    select *
    from {{ source('raw', 'raw_github_events') }}
),

renamed as (
    select
        id                                      as event_id,
        type                                    as event_type,

        -- Actor fields
        actor.id                                as actor_id,
        actor.login                             as actor_login,

        -- Repo fields
        repo.id                                 as repo_id,
        repo.name                               as repo_name,

        -- Org fields (nullable)
        org.login                               as org_login,

        -- Time dimensions
        created_at,
        date(created_at)                        as event_date,
        extract(hour from created_at)           as event_hour,
        extract(dayofweek from created_at)      as event_day_of_week,  -- 1=Sun … 7=Sat

        public

    from source
    where id is not null
      and type is not null
      and created_at is not null
)

select * from renamed
