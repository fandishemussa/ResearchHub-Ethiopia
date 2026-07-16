export interface Publication {
  id: string;
  title: string;
  abstract: string | null;
  publication_year: number | null;
  language: string | null;
  doi: string | null;
  article_url: string | null;
  pdf_url: string | null;
  publisher: string | null;
  source: string;
  source_type: string;
  authors: string[];
  keywords: string[];
  subjects: string[];
  quality_score: string | null;
  is_deleted: boolean;
  updated_at: string;
}
export interface DashboardSummary {
  counts: { total_publications: number; deleted_publications: number };
  source_status: Array<{
    name: string;
    platform: string;
    is_active: boolean;
    last_harvested_at: string | null;
    publication_count: number;
  }>;
}
export interface TrendPoint {
  year: number;
  count: number;
}
export interface KeywordPoint {
  keyword: string;
  count: number;
}

export interface University {
  id: string;
  code: string;
  name: string;
  country: string;
  city: string | null;
  website_url: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
}

export type SourceType =
  | "oai_pmh"
  | "dspace_oai"
  | "dspace_discovery"
  | "ojs_oai"
  | "xml_import"
  | "json_import"
  | "csv_import";
export interface Source {
  id: string;
  university_id: string | null;
  repository_id: string | null;
  journal_id: string | null;
  name: string;
  slug: string;
  description: string | null;
  source_type: string;
  base_url: string | null;
  api_url: string | null;
  oai_endpoint: string | null;
  metadata_prefix: string;
  set_spec: string | null;
  supported_formats: string[];
  is_active: boolean;
  is_public: boolean;
  status: string;
  last_health_check_at: string | null;
  last_successful_harvest_at: string | null;
  last_failed_harvest_at: string | null;
  last_error: string | null;
  consecutive_failure_count: number;
  total_records_harvested: number;
  total_active_records: number;
  total_deleted_records: number;
  created_at: string;
  updated_at: string;
}
export interface SourceCreate {
  university_id: string;
  name: string;
  slug: string;
  source_type: SourceType;
  description?: string;
  base_url?: string;
  api_url?: string;
  oai_endpoint?: string;
  metadata_prefix: string;
  set_spec?: string;
  is_active: boolean;
  is_public: boolean;
}
export interface SourceUpdate {
  name?: string;
  description?: string | null;
  base_url?: string | null;
  api_url?: string | null;
  oai_endpoint?: string | null;
  metadata_prefix?: string;
  set_spec?: string | null;
  supported_formats?: string[];
  is_active?: boolean;
  is_public?: boolean;
}
export interface SourceConnectionTest {
  success: boolean;
  response_time_ms: number;
  repository_name: string | null;
  protocol_version: string | null;
  supported_metadata_formats: string[];
  warnings: string[];
  errors: string[];
}
export interface HarvestJob {
  id: string;
  connector_id: string;
  job_type: string;
  mode: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  duration_ms: number | null;
  total_pages: number;
  processed_pages: number;
  total_records: number;
  fetched_records: number;
  created_records: number;
  updated_records: number;
  unchanged_records: number;
  deleted_records: number;
  duplicate_records: number;
  skipped_records: number;
  failed_records: number;
  checkpoint: Record<string, unknown>;
  resumption_token: string | null;
  dry_run: boolean;
  error_summary: Record<string, unknown>;
  result_summary: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}
export interface HarvestEvent {
  id: string;
  harvest_job_id: string;
  level: string;
  event_type: string;
  message: string;
  details: Record<string, unknown>;
  created_at: string;
}
export interface HarvestFailure {
  id: string;
  harvest_job_id: string;
  external_id: string | null;
  record_index: number | null;
  error_type: string;
  error_message: string;
  retryable: boolean;
  retry_count: number;
  resolved: boolean;
  created_at: string;
}
export interface ImportPreview {
  detected_format: string;
  total_records: number;
  valid_records: number;
  invalid_records: number;
  active_records: number;
  deleted_records: number;
  likely_creates: number;
  likely_updates: number;
  possible_duplicates: number;
  sample_records: Array<{
    external_id: string | null;
    title: string;
    publication_year: number | null;
    is_deleted: boolean;
  }>;
  validation_errors: Array<{ record_index: number; message: string }>;
}

export interface SemanticSearchResult {
  id: string;
  title: string;
  abstract_preview: string | null;
  publication_year: number | null;
  source: string;
  article_url: string | null;
  similarity: number;
}

export interface SemanticSearchResponse {
  query: string;
  model: string;
  count: number;
  results: SemanticSearchResult[];
}

export interface SemanticSearchParams {
  query: string;
  limit?: number;
  source?: string;
  minSimilarity?: number;
  signal?: AbortSignal;
}

export interface SimilarPublicationResult {
  id: string;
  title: string;
  abstract_preview: string | null;
  publication_year: number | null;
  source: string;
  article_url: string | null;
  similarity_score: number;
  shared_keywords: string[];
  shared_topics: string[];
  explanation: string[];
}

export interface PublicationSimilarityResponse {
  publication_id: string;
  model: string;
  count: number;
  results: SimilarPublicationResult[];
  status: "ready" | "embedding_required";
  message: string | null;
  minimum_similarity: number | null;
}

export interface PublicationSummary {
  id: string | null;
  publication_id: string;
  summary_type: string;
  summary_text: string | null;
  summary: string | null;
  model_name: string | null;
  source_fields: string[];
  confidence_score: string | null;
  is_verified: boolean;
  generated_at: string | null;
  status: "ready" | "processing" | "unavailable";
  summary_source:
    | "full_text"
    | "downloaded_document"
    | "newly_downloaded_document"
    | "abstract"
    | "metadata"
    | "unavailable";
  summary_style: string;
  research_document_id: string | null;
  document_status: string | null;
  pages_used: number[];
  chunk_count: number;
  provider: string | null;
  cached: boolean;
  warnings: string[];
  processing_job_id: string | null;
  message: string | null;
}

export interface EmbeddingAdministrationStatus {
  total_publications: number;
  embedded_publications: number;
  missing_embeddings: number;
  stale_embeddings: number;
  failed_embeddings: number;
  embedding_model: string;
  vector_dimension: number;
  queue: string;
}

export interface AIKeyword {
  id: string;
  publication_id: string;
  keyword: string;
  confidence_score: string;
  extraction_method: string;
  status: string;
}

export interface PublicationCitation {
  id: string;
  publication_id: string;
  citation_style: string;
  citation_text: string;
  metadata_version: string;
  is_verified: boolean;
}

export interface Researcher {
  id: string;
  full_name: string;
  normalized_name: string | null;
  orcid: string | null;
  affiliation: string | null;
}

export interface QualitySummary {
  total_reports: number;
  assessed_publications: number;
  active_publications: number;
  deleted_publications: number;
  average_final_score: string;
  grade_distribution: Record<string, number>;
  dimension_averages: Record<string, string>;
  generated_at: string;
  ruleset_version: string;
}

export interface QualityIssue {
  publication_id: string;
  report_id: string;
  grade: string;
  final_score: string;
  issue_type: string;
  category: string;
  message: string;
  assessed_at: string;
}

export interface QualityIssuePage {
  items: QualityIssue[];
  total: number;
  limit: number;
  offset: number;
}

export interface SystemHealth {
  status: "ok" | "degraded";
  instance_id: string;
  checks: Record<string, string>;
}

export interface AuthorizationMatrix {
  roles: Record<string, string[]>;
  permissions: string[];
}
