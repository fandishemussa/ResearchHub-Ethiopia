# AI research intelligence

Publication summaries use the priority: indexed chunks, registered local document, safely reachable direct PDF, validated repository landing-page PDF, abstract, then metadata. The response always includes `summary_source`, document state, evidence pages, chunk count, warnings, model/provider provenance, and cache state.

`POST /api/ai/publications/{id}/summary` accepts `summary_scope` (`auto`, `full_text`, `abstract`, `metadata`) and `summary_style`. The legacy `/summarize` route remains available. A document that needs work returns `status: processing`; clients poll without invented percentages.

Full-text summaries use ordered, de-duplicated page chunks and explicit structured sections. Missing evidence is rendered as “Not clearly identified in the indexed document.” A checksum/chunk/model/prompt change creates a new cache key and older abstract summaries become stale when full text becomes available.

Document probes block unsupported schemes, credentials in URLs, and private-network destinations unless the host is explicitly trusted. Downloads enforce timeouts, redirects, maximum bytes, and PDF magic-byte validation.
