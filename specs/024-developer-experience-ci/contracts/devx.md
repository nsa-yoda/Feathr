# Developer Experience Contract

Make targets are the stable local interface. Python dependencies use `uv run --locked`; Compose commands use `.env.example`; reset is the only target that removes volumes. CI repeats static and test targets independently and records unavailable service-backed checks explicitly.
