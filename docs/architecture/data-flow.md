# Data Flow

## Ingestion

`HTTP -> validate/rate limit -> local queue -> persistence worker -> MongoDB -> ACK local message`

ES and Redis are not in the durability path.

## Search projection

`MongoDB insert change stream -> search projector -> ES stable alias (+ rebuild target while active) -> persist resume token`

Checkpoint persistence occurs after ES success.

## Canonical query

`HTTP -> validated filters/cursor -> Mongo repository -> response`

## Analytics

`HTTP -> bounded range/bucket -> Mongo aggregation -> response`

## Realtime stats

`HTTP -> Redis lookup -> HIT response | MISS/BYPASS -> Mongo aggregation -> optional Redis SETEX -> response`

## Search

`HTTP -> validated query/filter/search_after -> Elasticsearch alias -> response`
