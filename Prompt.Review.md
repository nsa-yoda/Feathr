Perform a comprehensive, senior-level architecture and code review of this entire project repository. Because this is a large-scale system comparable to Reddit, analyze the codebase across correctness, redundancy, performance, security, maintainability, and over-engineering.

Do not just rubber-stamp or provide superficial comments. Structure your findings into a prioritized Markdown report.

## Review Scope & Focus Areas

1. Architecture & Modularity:
   - Evaluate directory structure, service boundaries, and separation of concerns (e.g., API layers, background workers, database access).
   - Identify tight coupling, circular dependencies, or monolithic bottlenecks.

2. Correctness & Logic Errors:
   - Look for subtle race conditions, concurrency issues, deadlocks, and incorrect state management.
   - Check edge cases in core domain logic (e.g., voting algorithms, nested comment threading, pagination limits, caching invalidation).

3. Performance & Scalability:
   - Spot N+1 query problems, inefficient database indexing strategies, unoptimized data structures, and missing caching layers.
   - Flag synchronous blocking calls in high-throughput or asynchronous paths.

4. Security & Robustness:
   - Check for injection vulnerabilities (SQL, NoSQL, XSS), broken access controls (authorization checks on posts/comments/moderation tools), and insecure data exposure.
   - Verify proper input validation, rate limiting considerations, and secret handling.

5. Maintainability & Redundancy:
   - Identify dead code, duplicated logic across modules, and over-engineered abstractions.
   - Assess test coverage gaps and error-handling consistency.

## Required Output Format

Provide a prioritized Markdown report containing:
- Executive Summary: High-level health score and key architectural takeaways.
- Action Items (Prioritized P0 to P3):
  - P0: Critical security flaws, data loss risks, or major system breakers.
  - P1: Performance bottlenecks or severe logic bugs.
  - P2: Maintainability issues, technical debt, or architectural cleanup.
  - P3: Minor optimizations or style/readability suggestions.
- Quick Wins: Low-effort, high-impact changes that can be done immediately.
- Redundancy Removal Log: Specific duplicate files, functions, or blocks of code safe to delete or refactor.

