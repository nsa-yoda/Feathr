# Queue Contract

`InProcessQueue` is the local implementation of the future SQS-shaped port. Callers never mutate internal messages and must delete or change visibility using the receipt handle returned by the matching receive call.
