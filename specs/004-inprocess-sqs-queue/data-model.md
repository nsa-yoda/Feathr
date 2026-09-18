# Feature 004 Data Model

- `Delivery`: stable `message_id`, immutable body, current receipt handle, receive count, and enqueue time.
- `QueueStats`: capacity, total depth, visible count, in-flight count, and DLQ count.
- Internal message state: enqueue time, visibility deadline, receive count, current receipt handle, and body.
