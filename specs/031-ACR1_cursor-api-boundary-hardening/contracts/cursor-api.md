# Cursor API Contract

- Production startup requires `EVENT_PLATFORM_CURSOR_SIGNING_KEY`.
- Current key signs new cursors; one configured previous key may verify during rotation.
- Public event DTOs omit schema version, payload hash, and idempotency hash.
- URL credentials and userinfo are invalid input.
