# Enterprise Prototype Release Checklist

Status values: **PASS**, **FAIL**, **NOT_RUN**, **PARTIAL**, **NOT_APPLICABLE**.

| Check | Status on 2026-07-16 | Evidence/action |
|---|---|---|
| Docker build and services healthy | NOT_RUN | Run manually on the target Docker host; Ollama model download must complete |
| Exactly one Alembic head | PASS | `0013_chat_workspace (head)` |
| Database current/schema matches models | NOT_RUN | PostgreSQL was not running; execute `current` and `check` |
| Backend Ruff | PASS | Touched backend/scripts and repository backend tree passed after import fix |
| Backend mypy | NOT_RUN | `.venv` lacks mypy and is Python 3.10, not declared 3.13 |
| Backend pytest | PARTIAL | 121 non-blocked tests plus 6 focused regressions pass; 3 modules cannot collect in incomplete Python 3.10 environment |
| Frontend format | PASS | Repository `npm run format` completed |
| Frontend lint | PASS | `npm run lint` |
| Frontend type check | PASS | `npm run type-check` |
| Frontend tests | PASS | 6 files, 23 tests |
| Frontend production build | PASS | Next.js 16.2.10 generated 15 application routes |
| Authentication | PARTIAL | Backend foundation plus login UI; live DB/Redis flow pending |
| Sensitive route permissions | PARTIAL | Major sensitive groups protected; tenant/query review remains |
| University scope | FAIL | Helpers exist; complete route/service enforcement absent |
| Source test/dry-run/import preview | NOT_RUN | Requires running services and configured source |
| Publication/semantic search | PARTIAL | Code/tests exist; live corpus evaluation pending |
| PDF/chunks/preview | PARTIAL | Model drift and test collection fixed; live indexed PDF pending |
| Assistant page-linked citation | PARTIAL | Code/tests exist; live Ollama/provider validation pending |
| Executive dashboard | FAIL | Basic aggregate dashboard only |
| Researcher directory | PARTIAL | Searchable normalized author directory added; verified profiles/CV/claims remain missing |
| Metadata correction workflow | FAIL | Quality scoring exists; stewardship workflow missing |
| Audit events visible | FAIL | General audit model/UI missing |
| Health and metrics | PARTIAL | Health UI/endpoints/config exist; services were not running |
| Backup | PARTIAL | Safe scripts and dry runs pass; real dump/restore drill pending |
| Showcase seed/verifier | PARTIAL | Implemented; requires Python 3.13/PostgreSQL execution |
| Known limitations | PASS | See `enterprise-prototype-known-limitations.md` |
| No committed real secrets | PARTIAL | No new secret committed; run repository secret scan before release |
| No unsupported capacity claim | PASS | Performance values remain NOT_MEASURED |

The release gate remains **NOT READY** until every required FAIL is either completed or explicitly
removed from the showcase claim, and all NOT_RUN runtime checks pass on the presentation host.
