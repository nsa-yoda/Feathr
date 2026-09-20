# Implementation Plan: ACR1 Rebuild Convergence Operations

## Summary

Harden rebuild state and cutover boundaries: persist fencing values and historical identifiers, make status lookup identifier-aware, and preserve the serving target after an alias swap even if post-swap metadata persistence fails.

## Design

- Extend the typed rebuild record with source high-water/checkpoint fields and a monotonic fencing token.
- Increment fencing on lease acquisition and require owner identity for renew/save.
- Add historical `get(rebuild_id)` lookup to the Mongo state adapter and status route.
- Treat alias swap as a commit barrier; failure state recording after swap must not delete the serving index.
