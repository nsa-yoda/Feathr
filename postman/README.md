# Postman Reviewer Suite

Feature 022 provides a Postman Collection v2.1 and a non-secret local environment.
Import these files into Postman:

- `Distributed Event Processing Platform.postman_collection.json`
- `Local Docker.postman_environment.json`

Run folders in numeric order from `00 Environment Verification` through `11
End-to-End Demo Scenario`. The ingestion request generates a unique user,
timestamp, and idempotency key, then stores `eventId` and `requestId`; the canonical query captures
`nextCursor` when the event becomes visible for later requests. Query and search use bounded Postman polling
with `pollDeadlineMs` and `pollIntervalMs`; they do not assume immediate
persistence or projection.

## Newman

With a running API (the Feature 021 Compose quickstart is the default):

```bash
make postman
# or
newman run "postman/Distributed Event Processing Platform.postman_collection.json" \
  -e "postman/Local Docker.postman_environment.json"
```

The wrapper exits `2` when Newman or either JSON asset is missing and propagates
Newman/API failures. If the API is unavailable, Newman reports the failed health
request rather than passing silently. The environment contains no credentials;
set `baseUrl` in a local copy for another API origin.
