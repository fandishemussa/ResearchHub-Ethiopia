# Caching

Redis is application-scoped and connection-bounded. Use `researchhub:cache:<scope>:<resource>:<version>` keys with explicit TTLs. Private results must include user, tenant, visibility scope, and permission version. Never serve stale private data if Redis fails.

Safe candidates include public dashboard aggregates, university directories, public facets, trend summaries, and provider health. Invalidate after publication/import/harvest completion, source or visibility changes, role changes, duplicate merges, and trend recalculation. Database reads remain available when optional caching is unavailable; operations requiring distributed locks fail closed.
