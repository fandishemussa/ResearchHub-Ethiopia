# Connector Framework

The harvester is designed so each source adapter emits the same normalized
publication model.

## Implemented in v0.1

### OAI-PMH

The OAI-PMH connector supports:

- `Identify`
- `ListRecords`
- `ListIdentifiers`
- `ListSets`
- `ListMetadataFormats`
- `requests.Session()` transport
- connection pooling with mounted HTTP adapters
- retry strategy for transient HTTP failures
- exponential backoff
- `resumptionToken`
- deleted records
- incremental harvesting with `from` and `until`
- multiple metadata formats
- XML import for replay and recovery
- duplicate detection
- metadata quality scoring
- simple rate limiting
- structured operational logging hooks

The connector normalizes Dublin Core fields into the canonical publication model:

- `dc:title` -> `title`
- `dc:creator` -> `authors`
- `dc:description` -> `abstract`
- `dc:date` -> `publication_date` and `publication_year`
- `dc:subject` -> `subjects` and `keywords`
- `dc:identifier` and `dc:relation` -> DOI, article URL, PDF URL, ISSN
- `dc:language` -> ISO-like language code
- `dc:rights` -> license
- OAI header identifier -> `external_id` and `repository_identifier`

The connector exposes synchronous methods such as `identify_sync`,
`list_records_sync`, `collect_sync`, and `collect_normalized_sync` for worker
processes. It also preserves async wrappers required by the platform
`MetadataConnector` contract.

### DSpace REST Discovery

The DSpace Discovery connector supports DSpace 7 HAL responses from
`/server/api/discover/search/objects`:

- API-base or full-search URL normalization
- `page`/`size` pagination controlled by ResearchHub
- configurable page size with retry and exponential backoff
- full harvest and maximum-record dry runs
- incremental filtering through item `lastModified`
- embedded Dublin Core metadata and locale normalization
- canonical publication validation, deduplication, provenance, and quality scoring

The default page size is 25 because public DSpace installations can produce large HAL documents.
Provider-specific `connection_config.page_size` may tune it from 1 to 100. DSpace Discovery results
do not provide deleted-item tombstones; this connector therefore cannot infer every remote deletion.

## Registered Extension Points

The following connectors are registered as configuration targets and intentionally
raise `NotImplementedError` until their provider-specific logic is added:

- OpenAlex
- Crossref
- DataCite
- ORCID

This makes the platform shape explicit without pretending that incomplete external
API behavior is production-ready.

## Adding a Connector

1. Create a class implementing `MetadataConnector`.
2. Add it to `CONNECTORS` in `researchhub_harvester.connectors.registry`.
3. Add provider-specific normalization tests.
4. Add rate-limit and retry policy settings to connector configuration.
5. Store the connector in the backend `connectors` table.
