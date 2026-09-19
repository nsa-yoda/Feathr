# UI Contract

The UI calls same-origin `/api` paths through nginx. Public contracts remain those of the API: 202 queued event responses, EventPage/SearchPage, StatsResponse, RealtimeStatsResponse, HealthSnapshot, and ProblemResponse. The client must render only bounded summaries and problem fields; it must not display raw DLQ payloads or credentials.
