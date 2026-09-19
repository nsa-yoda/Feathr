# Postman Contract

The collection is Postman v2.1 JSON. Folder names begin with `00` through `11` and run in numeric order. Every request has a `test` event asserting its status and response contract.

Polling scripts use `pm.sendRequest` until `Date.now()` reaches `pollDeadlineMs`; they never use an unbounded loop or shell sleep. Degraded dependency responses must be `503` problem documents with `status`, `detail`, `error_code`, and `request_id`.

The Newman wrapper exits 2 when Newman is unavailable and propagates nonzero Newman/API failures.
