# Enterprise Prototype Known Limitations

1. Full university/department tenant isolation is not yet verified across every service query.
2. The enterprise administration area, user/role editor and immutable audit-log UI are not complete.
3. Researcher profiles are basic author records; claims, verification, CV generation, collaboration
   networks and external ORCID/Scopus synchronization are not implemented.
4. Metadata quality calculation exists, but the DETECTED-to-CLOSED correction/approval workflow is
   not persisted or presented end to end.
5. Organizational hierarchy stops at university/faculty/department. Campus, research center and
   research group are planned entities.
6. Document metadata/chunk browsing exists, but re-extract/re-chunk/re-embed/delete administration
   actions and complete embargo/restriction policy are incomplete.
7. The assistant is a grounded prototype. Live Ollama use requires a completely downloaded model;
   local extractive fallback is not equivalent to a generative model.
8. Search relevance and performance have not been measured on an approved representative corpus.
9. Grafana, Prometheus, worker health and alert delivery require deployment validation.
10. Backup scripts have dry-run validation, but a database dump and isolated restore drill have not
    been executed in this audit environment.
11. The local `.venv` is Python 3.10 while the project declares Python 3.13. Full backend runtime,
    type-check and test verification must use a rebuilt Python 3.13 environment.
12. Demo records are synthetic and labelled. They are not official Haramaya University research,
    performance, ranking, financial or policy data.

None of the above should be described as production-ready. Existing imported research and document
data must not be deleted to make a showcase appear complete.
