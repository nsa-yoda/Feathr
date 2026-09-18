# Feature Request: Retry, Backoff, and Simulated DLQ

## Intent

Make every processing failure disposition explicit.

## Retry taxonomy

Define transient Mongo/network/timeouts versus permanent invariant/data errors. Unknown infrastructure errors may receive bounded retry but never infinite retry.

## Backoff

Exponential backoff with configurable base/cap and bounded jitter. Retry is implemented by changing visibility / scheduling next availability, not by sleeping while holding worker capacity.

## Attempts

Define whether the first delivery counts as attempt 1 and keep the rule consistent in logs/metrics/DLQ. Default max receive count should be modest (e.g. 5) and configurable.

## DLQ

On exhaustion/permanent conflict, move a copy of the envelope plus safe diagnostic metadata to a simulated in-process DLQ, then delete the source message. The DLQ is also volatile in this demo; document real SQS redrive differences.

## Observability

Log each retry schedule with event/message ID, attempt, classified error code, and delay — never full metadata. Metrics for retry count, DLQ count, oldest queue age.

## Tests

Backoff bounds with deterministic jitter, transient succeeds after retries, permanent skips retries where appropriate, exhaustion to DLQ, no source-message ghost after DLQ.


## Dependencies

004, 006

## Mandatory Spec Kit execution

Use this REQUEST as input to `$speckit-specify`; then run clarify, plan, checklist, tasks, analyze, implement, converge, staff review, and full review. Generated Spec Kit artifacts belong in this feature directory according to the installed Spec Kit workflow. Do not bypass clarification when a semantic choice remains open.
