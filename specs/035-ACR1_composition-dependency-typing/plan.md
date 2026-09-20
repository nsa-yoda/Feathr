# Implementation Plan: ACR1 Composition and Dependency Typing

## Summary

Add a typed application-services container and factory at the composition boundary, wire it from lifespan-owned clients, and keep route/infrastructure construction separated without introducing a generic DI framework.

## Design

- `ApplicationServices` declares queue/metrics/health as required and storage/search/operational dependencies as optional typed ports.
- Lifespan builds the container once, then fills owned dependencies as clients become available.
- Existing state attributes remain compatible while the typed container becomes the testable composition seam.
