# ResearchHub load tests

Run only against a dedicated test database with `RESEARCHHUB_LOAD_TEST_MODE=true`. The default workload is read-only apart from optional login/logout and never starts harvesting or imports.

```powershell
python -m pip install -r load-tests/requirements.txt
locust -f load-tests/locustfile.py --headless --users 5 --spawn-rate 1 --run-time 2m --host http://localhost:8111 --csv load-tests/reports/smoke
```

Stages: smoke `5/2m`; baseline `25/10m`; normal `100/20m`; high `250/20m`; target `1000/30m`; soak `2-8h`. Do not claim capacity from configuration alone. Record hardware, replicas, active users, RPS, percentiles, error rate, and resource metrics using the report template.
