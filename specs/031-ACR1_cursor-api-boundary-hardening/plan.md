# Implementation Plan: ACR1 Cursor API Boundary Hardening

## Summary

Move cursor signing from per-process generated keys to shared configuration with bounded previous-key rotation, normalize public event DTOs, reject URL credentials, and preserve bounded UTC cursor behavior.

## Design

- Production settings require a shared cursor signing key; optional previous key supports overlap.
- Query cursors use configured current/previous keys and emit with current key.
- Public query/search responses use `PublicEvent`, excluding payload hashes and idempotency controls.
- Event and query URL validation rejects userinfo credentials.
