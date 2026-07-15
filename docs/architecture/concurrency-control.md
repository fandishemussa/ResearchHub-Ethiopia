# Concurrency control

- Refresh-token rotation and one-time recovery tokens use PostgreSQL row locks.
- Harvest submission takes a short transaction-scoped advisory lock, locks the source row, rejects a second active source job, and enforces global capacity.
- Import confirmation locks the job before changing it from pending to running.
- Redis locks use owner tokens, expiration, compare-and-delete release, and lease renewal under `researchhub:lock:*`.
- Redis rate-limit keys use `researchhub:rate-limit:*` and atomic Lua increments.

Database constraints remain the final consistency layer. Never depend on disabled frontend buttons for correctness. Lock scope must cover only validation and durable state transition; no external request should execute while a database lock is held.
