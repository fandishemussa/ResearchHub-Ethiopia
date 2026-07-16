# Enterprise Prototype Authorization Matrix

## Policy model

ResearchHub uses persisted users, roles, permissions, user-role assignments and role-permission
grants. The canonical vocabulary is defined in `researchhub.core.permissions`; database seeding is
idempotent through `seed_authorization_vocabulary`. Route handlers use reusable dependencies from
`researchhub.api.v1.dependencies` and must not compare role-name strings.

Authorization is **deny by default**. Authentication proves identity; it does not grant a
permission. `PLATFORM_ADMIN` is the only policy-level superuser role. University and department
scope are separate checks and must still be applied to tenant-owned records.

## Permission meaning

| Permission | Purpose |
|---|---|
| `sources.read` | View managed sources, health, history and harvest jobs |
| `sources.manage` | Create, edit, test, enable, disable or remove sources |
| `harvest.start` | Start, resume or retry harvest jobs |
| `harvest.cancel` | Cancel a running harvest job |
| `imports.create` | Upload, preview, confirm or cancel metadata imports |
| `publications.read` | Read catalogue records |
| `publications.manage` | Create or change catalogue records |
| `metadata.correct` | Propose corrections and recalculate individual quality reports |
| `metadata.approve` | Approve corrections and run bounded bulk recalculation |
| `documents.read` | View indexed-document metadata and chunks |
| `documents.manage` | Register, reprocess or delete documents |
| `documents.download` | Preview or download managed document content |
| `ai.use` | Use assistant and research-intelligence endpoints |
| `ai.manage` | Configure approved AI providers and operational policy |
| `users.read` | View user directory and assignments |
| `users.manage` | Activate, suspend and assign tenant membership |
| `roles.manage` | Change role definitions and grants |
| `audit.read` | View/export security and business audit events |
| `reports.export` | Export approved reports |
| `settings.manage` | Change platform-level settings and institution configuration |

## Prototype role matrix

`✓` means the role is granted the permission by the canonical seed. A blank means denied.

| Role | src read | src manage | harvest | import | pub manage | correct | approve | doc read/download | doc manage | AI use/manage | users read/manage | roles | audit | export | settings |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PLATFORM_ADMIN | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓/✓ | ✓/✓ | ✓ | ✓ | ✓ | ✓ |
| UNIVERSITY_ADMIN | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓/✓ | ✓/✓ |  | ✓ | ✓ |  |
| ICT_ADMIN | ✓ | ✓ | ✓ |  |  |  |  | ✓/ | ✓ | /✓ | ✓/ |  | ✓ |  | ✓ |
| RESEARCH_OFFICE_DIRECTOR | ✓ |  |  |  | ✓ | ✓ | ✓ | ✓/ |  | ✓/ | ✓/ |  | ✓ | ✓ |  |
| RESEARCH_OFFICE_OFFICER | ✓ |  |  |  | ✓ | ✓ |  | ✓/ |  | ✓/ |  |  |  | ✓ |  |
| LIBRARY_ADMIN | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓/✓ | ✓ |  |  |  |  | ✓ |  |
| METADATA_OFFICER | ✓ |  |  | ✓ | ✓ | ✓ |  | ✓/ | ✓ |  |  |  |  |  |  |
| COLLEGE_ADMIN | ✓ |  |  |  |  |  |  | ✓/ |  | ✓/ | ✓/ |  |  | ✓ |  |
| DEPARTMENT_COORDINATOR | ✓ |  |  |  |  | ✓ |  | ✓/ |  | ✓/ |  |  |  | ✓ |  |
| RESEARCHER | ✓ |  |  |  |  |  |  | ✓/✓ |  | ✓/ |  |  |  |  |  |
| GRADUATE_STUDENT | ✓ |  |  |  |  |  |  | ✓/✓ |  | ✓/ |  |  |  |  |  |
| PUBLIC_USER |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| AUDITOR | ✓ |  |  |  |  |  |  | ✓/ |  |  |  |  | ✓ | ✓ |  |

All roles except `PUBLIC_USER` also receive `publications.read` through the read-only bundle.
`PUBLIC_USER` receives only `publications.read`.

## Enforced route boundaries

The current prototype enforces:

- all `/sources` access: `sources.read`; source mutation/test: `sources.manage`;
- source harvest and retry/resume: `harvest.start`; cancellation: `harvest.cancel`;
- all `/import` upload/preview/confirm/cancel operations: `imports.create`;
- all `/harvest` inspection: `sources.read` plus action-specific permission;
- all indexed-document metadata/chunks: `documents.read`; content: `documents.download`;
- all `/ai` endpoints: `ai.use`; AI document preview also requires `documents.download`;
- publication creation: `publications.manage`;
- quality recalculation: `metadata.correct` or `metadata.approve`;
- university creation: `settings.manage`.

Catalogue reads, dashboard aggregates, university reads, publication search, and semantic search
require an authenticated account with `publications.read`. The frontend validates the stored session
before mounting application pages, and the API enforces the same permission independently.

## Tenant scope

Reusable university and department scope dependencies exist, but scope enforcement is not yet
complete across every query. Until record-by-record scope tests pass, only `PLATFORM_ADMIN` should
be used for cross-university administration and the platform must not claim complete multi-tenant
isolation. Services that accept `university_id` or return institution-owned operational records are
the next enforcement targets.

## Provisioning

The administrator creation command seeds the complete vocabulary and assigns `PLATFORM_ADMIN`.
The password is read from `RESEARCHHUB_ADMIN_PASSWORD` or a hidden prompt; it is not accepted as a
command-line value and no default credential is committed.

```powershell
python scripts/create_admin_user.py --email admin@example.edu --username platform-admin --full-name "Platform Administrator"
```

The command prompts for the password without echoing it. Automation should inject
`RESEARCHHUB_ADMIN_PASSWORD` through the deployment secret store rather than shell history.

Do not use the illustrative address in a real deployment. Rotate bootstrap credentials after first
use and review active refresh sessions.

## Remaining security work

- Apply university/department predicates to all tenant-owned reads and mutations.
- Add user/role administration APIs and complete per-action permission controls in the frontend.
- Add immutable audit events for assignments, suspensions, login outcomes and sensitive actions.
- Add explicit restricted/embargo document policy and tests.
- Complete unauthorized (401), forbidden (403), allowed and cross-tenant (403/404) route tests on
  Python 3.13 with PostgreSQL and Redis available.
