# Reviewer Operations UI

Feature 023 provides the lightweight reviewer console in `public/index.html`.
It is served by the existing unprivileged nginx image, uses same-origin `/api/`
proxy requests, caps event bursts at 20, and keeps operations data read-only and
secret-safe. Open `http://localhost:3000` from the Compose stack.
