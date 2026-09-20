# Research

The normal integration target intentionally uses an empty-safe skip hook for local development, while CI did not have a strict counterpart. The repository already has a locked uv workflow and ignored cache patterns; explicit scripts close the auditability gap without adding dependencies.
