# Enterprise Prototype Showcase Script

Use only scenarios whose release-checklist dependencies pass on the presentation host. Seeded
records are visibly marked **Demonstration** and must never be described as official research.
Total target duration: 25–35 minutes.

| Scenario | Presenter steps | Expected screen/result | Offline fallback | Time |
|---|---|---|---|---:|
| 1. Executive overview | Sign in as an approved university administrator; open Dashboard; show year/topic/source summaries; drill into Publications | Aggregate cards, publication trend, topics and repository health; data freshness is explained verbally | Use labelled demo records and state that the role-specific executive dashboard is still a foundation | 4 min |
| 2. Repository integration | Open Repositories; choose a managed source; Test connection; start Dry run; open job detail | Structured connection feedback and a queued/running/completed job with counters/events | Open the seeded disabled demonstration source and a completed demo job; do not imply a live external call | 4 min |
| 3. Metadata quality | Open a publication and quality information; show missing-field issues and recalculate if authorized | Quality dimensions and actionable issues | Explain that scoring works but assignment/correction approval is not yet an end-to-end workflow | 3 min |
| 4. Full-text document | Open Indexed documents; choose a verified indexed PDF; preview; inspect page-aware chunks and embedding status | Inline PDF, chunk pages/content and 384-dimension indexing status | Use screenshots only if approved; otherwise skip because no fake PDF is seeded | 4 min |
| 5. Grounded assistant | Open AI research assistant; select repository/university scope; ask a prepared corpus question; open a page citation; export | Grounding label, evidence excerpts, page references, retrieval/model diagnostics appropriate to prototype | Switch to local extractive provider or show a saved, clearly labelled demo interaction; never invent a citation | 5 min |
| 6. Researcher expertise | Open Authors/available catalogue evidence and search an expertise topic | Basic author/publication evidence | State explicitly that the enterprise researcher directory/CV workflow is planned and skip profile claims | 2 min |
| 7. Administration | Demonstrate sign-in/session and explain permission matrix; use CLI-provisioned roles | Protected APIs return 401/403 without grants and succeed with approved role | Show `docs/authorization-matrix.md`; user editor and audit UI are not yet showcase-ready | 3 min |
| 8. Operations | Open health URLs, Prometheus targets and Grafana; run feature checker | Database/Redis/API/frontend checks PASS and metrics targets are healthy | Show the JSON verifier with UNAVAILABLE values and explain the dependency honestly | 4 min |

## Presenter preparation

1. Run the release checklist and save output; do not troubleshoot live without a fallback.
2. Verify the exact administrator account via approved secret management.
3. Run the demo seed and verifier; confirm all synthetic labels are visible.
4. Test the repository endpoint and one bounded dry run without importing production data.
5. Verify one lawful PDF, its chunks and citations. Prepare a question answerable by that PDF.
6. Confirm Ollama model/provider status or select local fallback before the audience arrives.
7. Keep `enterprise-prototype-known-limitations.md` available for questions.

## Expected opening and closing

Opening: “This is an enterprise prototype showing verified ingestion, discovery and grounded
research-intelligence foundations. Demonstration records are synthetic; production security,
tenant isolation and capacity validation remain formal next steps.”

Closing: summarize verified workflows, show the limitations/release gate, and propose a controlled
pilot with representative data and agreed acceptance metrics. Do not claim rankings, financial
impact, production user capacity or official institutional findings.
