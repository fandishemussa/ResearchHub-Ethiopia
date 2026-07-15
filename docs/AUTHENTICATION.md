# Authentication foundation

Migration `0010_authentication_foundation` adds users, roles, permissions,
role joins, revocable refresh sessions, password reset tokens, and email
verification tokens.

Passwords use Argon2. Access tokens are short-lived signed JWTs with issuer,
audience, type, subject, JTI, issued-at, not-before, and expiration claims.
Refresh tokens are high-entropy opaque values; only their SHA-256 hashes are
stored. Each refresh rotates the session. Reuse of a revoked refresh token
revokes every active session for that user.

## Configuration

Set a random secret before production deployment:

```dotenv
RESEARCHHUB_AUTH_JWT_SECRET=replace-with-at-least-32-random-characters
RESEARCHHUB_AUTH_JWT_ISSUER=researchhub-ethiopia
RESEARCHHUB_AUTH_JWT_AUDIENCE=researchhub-api
RESEARCHHUB_AUTH_ACCESS_TOKEN_MINUTES=15
RESEARCHHUB_AUTH_REFRESH_TOKEN_DAYS=30
RESEARCHHUB_AUTH_MAX_FAILED_ATTEMPTS=5
RESEARCHHUB_AUTH_LOCKOUT_MINUTES=15
```

Production startup rejects the documented development secret. Login and reset
requests use Redis counters without storing raw email addresses or usernames in
rate-limit keys.

## Initial administrator

No public registration endpoint is exposed. Bootstrap an initial verified user
from the trusted host terminal:

```powershell
docker compose run --rm api python /app/scripts/create_admin_user.py `
  --email admin@example.edu.et `
  --username admin `
  --full-name "Platform Administrator" `
  --password "use-a-long-random-password"
```

Roles and permissions are attached in Phase 2; the script creates identity
only and does not falsely grant an unimplemented role.

## Endpoints

- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `POST /api/auth/logout-all`
- `GET /api/auth/me`
- `GET /api/auth/sessions`
- `DELETE /api/auth/sessions/{id}`
- `POST /api/auth/password/change`
- `POST /api/auth/password/forgot`
- `POST /api/auth/password/reset`
- `POST /api/auth/email/verify`

The forgot-password endpoint always returns the same accepted response and
stores a hashed, expiring reset token when an account exists. Email delivery is
not configured in this checkout, so reset and verification token delivery must
be connected to an approved institutional mail provider before those user-facing
flows are production-operational. Tokens are never returned or logged.

Phase 1 deliberately does not protect existing routes. Phase 2 must seed and
assign the RBAC vocabulary, implement institutional scope dependencies, and
apply them route-by-route before administrative controls are considered secure.
