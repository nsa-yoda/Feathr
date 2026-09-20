# Data Model

Queue state consists of a message map keyed by ID, ready deque, visibility expiry heap, current receipt handle, and volatile DLQ. The adapter capability reports `durable=False`.
