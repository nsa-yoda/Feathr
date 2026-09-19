# Feature 017 Quickstart

1. Set `EVENT_PLATFORM_REQUEST_BODY_MAX_BYTES=1024` and start the app with `TestClient` or Uvicorn.
2. Send an event body larger than 1 KiB; expect `413 application/problem+json`, `error_code=request_body_too_large`, no stack trace, and security headers.
3. Set `EVENT_PLATFORM_CORS_ALLOWED_ORIGIN=https://ui.example.test`; an `OPTIONS` request from that origin receives the allow-origin/method/header response, while `https://evil.example.test` does not.
4. Send `X-Forwarded-For` with the default trusted-hop setting; rate-limit identity remains the direct peer. Set a valid trusted hop count and complete chain to opt in.
5. Build the application and UI images and inspect their declared runtime users; both must be non-root.

The full repository gates remain `make format-check`, `make lint`, `make typecheck`, `make test-unit`, `make test-integration`, and `make test-failure`.
