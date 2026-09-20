# Data Model

Registry identity is SHA-256(scope, operation, raw key). Records contain only bounded scope/operation, request fingerprint, event ID, status, and timestamps. Raw keys are never persisted or logged.
