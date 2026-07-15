# Background workers

Celery routes isolate `harvest`, `imports`, `ai_embeddings`, `ai_generation`, `ai_analysis`, `ai_chat`, `documents`, `notifications`, and `maintenance`. The scaling Compose profile starts dedicated queue consumers. Prefetch is one; tasks use bounded soft/hard time limits, late acknowledgement, worker-loss rejection, and expiring results.

Run the development mixed worker for convenience. For production-like isolation, stop or scale it to zero and start the `scaling` profile. Tasks acknowledged late must be idempotent because worker loss can redeliver them.
