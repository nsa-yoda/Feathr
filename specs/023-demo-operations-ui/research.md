# Feature 023 Research

- The Compose UI service serves `frontend/public` through nginx on port 8080 and proxies `/api/` to the API container.
- Public backend surfaces include health, events ingestion/query, search, hourly analytics, realtime statistics, and metrics.
- Health component summaries expose mongo, elasticsearch, redis, queue, persistence_worker, and search_projector states.
- The UI must treat Mongo as canonical, Elasticsearch as eventually consistent, and Redis as optional acceleration.
