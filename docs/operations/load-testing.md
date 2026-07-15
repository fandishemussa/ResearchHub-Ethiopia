# Load testing

Use a dedicated database and `RESEARCHHUB_LOAD_TEST_MODE=true`. Install `load-tests/requirements.txt`, then run the documented smoke stage. Archive Locust CSV/HTML output and infrastructure metrics.

Progress only after the prior stage meets its SLO: smoke 5 users/2m; baseline 25/10m; normal 100/20m; high 250/20m; target 1,000 connected users/30m with realistic waits; stress to the SLO boundary; spike; soak 2-8h; recovery by terminating one replica in a safe environment.

Never start real harvesting, send real email, or use paid AI during general load tests. Failure tests must never target production.
