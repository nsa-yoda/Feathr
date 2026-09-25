Assignment
Staff Backend Software Engineer — Take-Home Assignment
Company: Feathr
Talent Contact: Kaitlyn McGowan, HR Director - kaitlyn.mcgowan@feathr.co



Overview
Design and implement a Distributed Event Processing Platform — a production-grade system for ingesting, processing, querying, and caching high-volume web events. This assignment is intentionally broader in scope than a typical take-home. We're not just evaluating whether you can write correct code — we're evaluating how you think about systems, communicate architectural decisions, and make principled tradeoffs under realistic constraints.



The architecture document is a first-class deliverable alongside the code.





AI Usage Policy
We expect and actively encourage the use of AI tools in this assignment.

AI-assisted development is a core part of how we work at Feathr daily. What we're evaluating is not whether you used AI, but how thoughtfully and effectively you leveraged it.

In your README, please include an "AI in My Workflow" section that addresses:

Which AI tools you used (e.g., GitHub Copilot, ChatGPT, Claude, Cursor, etc.)

Specific examples of how AI helped you — architecture decisions, scaffolding, code review, testing, etc.

Where you pushed back on or corrected AI output, and why

How AI shaped your overall approach or development speed

At a principal level, we're particularly interested in how you use AI to explore architectural tradeoffs, stress-test your own assumptions, and raise the quality of your output — not just to generate boilerplate.





Tech Stack
Framework: Python with FastAPI or Flask — your choice

Primary store: MongoDB (event storage and aggregations)

Search/analytics layer: Elasticsearch (full-text search and analytics queries)

Caching layer: Redis

Async processing: Simulated event queue (in-process, modeled after SQS-style processing)





Core Requirements
1. Async Event Ingestion Pipeline
Rather than writing events synchronously to MongoDB on each request, implement an async ingestion pipeline:

POST /events — Accept event data, validate it, and enqueue it for async processing

A background worker consumes from the queue and writes events to MongoDB

If processing fails, events should be retried with a basic backoff strategy

Document your queue design: what guarantees does it provide, and what would you change if this were a real SQS implementation?

Event structure:

Event type (string: e.g., "pageview", "click", "conversion")

Timestamp

User ID (string)

Source URL

Metadata (flexible JSON object: browser info, device type, feature-specific data)

2. Querying & Analytics
GET /events — Filter events by type, date range, user ID, or source URL

GET /events/stats — MongoDB aggregation pipeline returning counts grouped by event type and configurable time bucket (hourly, daily, weekly)

GET /events/search — Full-text search across event metadata using Elasticsearch

GET /events/stats/realtime — Return a lightweight stats summary served from Redis cache, with a configurable TTL

3. Caching Strategy
Implement Redis caching for the /events/stats/realtime endpoint

Document your caching strategy: TTL rationale, cache invalidation approach, and what you'd do differently under higher write volume

4. Indexing Strategy
Implement appropriate MongoDB indexes for your query patterns and document your reasoning

Define an Elasticsearch index mapping for event documents and explain your field type and analyzer choices

Identify any indexes you deliberately chose not to add and why

5. Architecture Document
This is a required deliverable — not optional README notes. Include a dedicated ARCHITECTURE.md in your repository that covers:

System diagram — A simple text or ASCII diagram (or linked image) showing data flow from ingestion to storage to query

Component responsibilities — What each layer (API, queue, worker, MongoDB, Elasticsearch, Redis) owns and why

Storage rationale — Why you split responsibility between MongoDB, Elasticsearch, and Redis the way you did

Failure modes — What happens if MongoDB is unavailable? If the worker crashes mid-batch? How does the system degrade gracefully?

Scaling considerations — If event volume 10x'd, what breaks first and how would you address it?

What you'd do differently — Given more time or a real production environment, what would you change and why?

6. Testing
Unit tests covering core business logic and error paths

Integration tests covering at least two full request lifecycles (e.g., ingest → worker processes → query returns result)

A brief note in your README on your testing philosophy and what you'd prioritize with more time

pytest preferred

7. Code Quality & Standards
Clear module boundaries — ingestion, processing, storage, querying, and caching are distinct concerns

Meaningful error handling with appropriate HTTP responses and internal logging

Code should be written as if a team of engineers will maintain it — not just as a demo





Evaluation Criteria
Architecture document — Clarity of thinking, honesty about tradeoffs, and depth of systems reasoning

Async pipeline design — Correctness, failure handling, and awareness of real-world queue semantics

MongoDB proficiency — Schema design, aggregation pipelines, indexing rationale

Elasticsearch integration — Index mapping design, query construction, appropriate use of ES vs. Mongo

Redis caching — Strategy soundness, TTL reasoning, invalidation approach

Code quality — Readability, modularity, and maintainability at a team scale

Testing — Meaningful coverage with a clear philosophy behind what was tested and why

AI workflow — Evidence of using AI strategically to accelerate, not just to fill space





Bonus Points (Optional)
Dockerfile / docker-compose setup covering all services (MongoDB, Elasticsearch, Redis, app)

Basic rate limiting or abuse prevention middleware

Event deduplication logic in the worker

Dead letter queue simulation for events that exhaust retries

AWS SQS drop-in design notes — what would change if you replaced the in-process queue with real SQS?





Important Note
This is strictly a backend assessment. There are no points awarded for frontend development, UI components, or styling.





Submission Format
A GitHub repository containing:

Source code with clear module structure

ARCHITECTURE.md as a standalone document

Unit and integration tests

README.md with setup instructions, endpoint documentation, testing approach, and AI in My Workflow section





Timeline
Candidates are given one week to complete the project. The timeframe is intentional — a principal engineer with a clear architectural vision should be able to execute this efficiently with the right AI tooling. We want to see you lean into AI as a force multiplier. The architecture document is as important as the code, so budget time for it accordingly.





Evaluation
Your submission will be reviewed by a panel of engineers who will evaluate your work and prepare questions for a follow-up technical discussion. Be prepared to walk through your architecture document, defend your storage and caching decisions, and discuss how you'd evolve the system over time.

If you have any questions, please reach out to your Talent Acquisition contact.
