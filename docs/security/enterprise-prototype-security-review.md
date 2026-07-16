# Enterprise Prototype Security Review

**Reviewed:** 2026-07-16  
**Disposition:** suitable only for a controlled prototype network after the P0 setup steps below

## Fixed in this review

- Added centralized permission and role vocabulary and a database-backed authorization service.
- Added reusable authenticated-user, single/any-permission, admin, university-scope and
  department-scope dependencies.
- Protected catalogue/dashboard reads, search, source management, harvest actions, imports,
  indexed documents, document content, AI endpoints, publication creation, quality recalculation,
  and university creation.
- Added a browser sign-in flow. Tokens are held in tab-scoped `sessionStorage`, accessed only in
  client code, and attached centrally to fetch/XHR requests.
- Administrator provisioning no longer accepts a password on the command line. It uses a hidden
  prompt or a secret-store-provided environment variable.
- Document content is served by managed document ID with a neutral filename; local filesystem paths
  are not returned in the public response schema.

## Existing positive controls

- Argon2 password hashing; short-lived JWT access tokens; opaque hashed refresh tokens; refresh
  rotation, revocation and reuse handling; account suspension and failed-login lockout.
- Redis-backed authentication rate limiting fails closed when the rate limiter is unavailable.
- Import size limits and managed storage configuration exist; document path resolution has explicit
  managed-root checks.
- SQLAlchemy parameterization is used for normal ORM work. Explicit SQL in indexing uses bound
  parameters rather than string interpolation.
- AI context diagnostics are disabled in production configuration and local paths are not intended
  for assistant responses.

## Open high-risk items

| Finding | Severity | Current mitigation | Required closure |
|---|---|---|---|
| Tenant scope is not enforced on every institution-owned query | High | Controlled single-institution prototype; centralized scope helpers exist | Add service predicates and cross-tenant IDOR tests before multi-tenant use |
| No immutable audit-event store | High | Operational logs exist for harvest/AI | Add redacted audit model, middleware/service hooks and review UI |
| Restricted/embargo document policy is incomplete | High | Document routes now require read/download grants | Persist access classification and enforce it in preview, retrieval and AI context |
| Browser tokens are readable by JavaScript | Medium | Tab-scoped storage; CSP/XSS review still required | Prefer same-site secure HttpOnly cookie/BFF design for production |
| Refresh is not automatically rotated by the browser client | Medium | Users can sign in again; backend rotation is implemented | Add single-flight refresh with forced logout on reuse/failure |
| Catalogue/search field disclosure still needs a completed review | Medium | Authentication and `publications.read` are required; no local paths/raw embeddings are exposed | Approve field-level data policy before granting broad reader access |

## Deployment controls

Before exposing the prototype: replace the JWT placeholder with at least 32 random bytes from a
secret store; use TLS; restrict CORS to exact origins; do not publish PostgreSQL, Redis, Celery,
Ollama, Prometheus or Grafana directly; rotate bootstrap credentials; verify Nginx upload/timeouts;
disable debug/context diagnostics; review logs for tokens and prompts; and run the negative
authorization/IDOR suite.

CSRF is limited while bearer tokens are explicitly attached rather than ambient cookies. If the
production design moves to cookies, implement same-site policy and CSRF protection. Markdown and
external links must remain sanitized and use `noopener noreferrer`; `javascript:` and unsafe
schemes must be rejected.

## Non-claim

This review is source-based and is not a penetration test, dependency vulnerability scan, privacy
impact assessment or production security accreditation.
