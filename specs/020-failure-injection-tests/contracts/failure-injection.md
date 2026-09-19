# Failure Injection Contract

## Determinism

Faults are injected through explicit fake ports, finite failure counters, manual clocks, or immediate awaitable sleeps. Tests MUST NOT depend on process termination, random packet loss, real unavailable services, arbitrary long sleeps, or host-specific port races.

## Safe evidence

Assertions use typed state, bounded reason codes, counts, and status values. Diagnostics MUST NOT include credentials, raw dependency exception text, full event metadata, request bodies, or resume-token contents.

## Disposition

- Canonical persistence failures leave the current delivery available for visibility retry until the configured receive limit.
- Successful persistence is followed by acknowledgement/removal.
- Same-payload redelivery is acknowledged as a duplicate without a second canonical record.
- Exhaustion or permanent invalid input creates one DLQ entry and removes the source delivery exactly once.

## Projection

A projection checkpoint advances only after the derived write succeeds. Invalid resume history returns `reconciliation_required`; the source is not opened with `resume_after=None` as a silent latest-only fallback.

## Derived dependencies

Elasticsearch failure does not prevent canonical Mongo operations. Redis failure uses realtime canonical bypass and conservative local rate limiting. A rebuild alias changes only after target verification and a successful atomic swap.

Unexpected rebuild dependency or cleanup exceptions are classified as
`rebuild_unexpected_failure`, recorded as failed state when possible, and do
not suppress target cleanup or live-target deactivation diagnostics.
