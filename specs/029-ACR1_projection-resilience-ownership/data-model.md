# Data Model

Projection checkpoints contain projector, resume token, state, owner, and non-negative generation. `projection_owner_lost` is an allowlisted safe error. Batch size is bounded to 1,000 changes per call.
