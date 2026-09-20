# Queue Durability Contract

- Ordinary ready receive and visibility expiry use indexed scheduling.
- Stale receipts cannot delete or extend a later delivery.
- Local acceptance is explicitly volatile and is not a production durability guarantee.
