# Composition Contract

- Network clients are still created and closed by lifespan.
- Required and optional dependencies are explicit in `ApplicationServices`.
- Factories are small and directly testable; no service locator or general DI framework is introduced.
