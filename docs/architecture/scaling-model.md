# Scaling Model

The demo proves semantics under a constrained single-process runtime. The production scaling path is deliberately incremental:

1. replace local queue with SQS without changing application service interfaces;
2. split API and persistence workers into independent deployments;
3. scale worker concurrency from measured queue age/depth and Mongo capacity;
4. tune Mongo indexes before sharding;
5. scale ES projection consumers and cluster resources from lag/indexing metrics;
6. introduce materialized aggregates when analytics scans become the dominant Mongo workload;
7. add tenant/API-key-aware rate limits when an identity system exists.

Document measured bottlenecks before applying distributed-system machinery.
