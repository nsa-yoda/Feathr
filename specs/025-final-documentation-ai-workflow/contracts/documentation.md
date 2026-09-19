# Documentation Contract

MongoDB is canonical event state. Elasticsearch is an eventually consistent rebuildable projection. Redis is non-authoritative cache/rate-limit state. The local 202 response acknowledges process-local queue admission and is not crash durable. At-least-once semantics remain the public guarantee. Documentation must preserve these terms and distinguish static/unit/failure/integration-skip/live Compose/Postman/browser/hosted-CI evidence.
