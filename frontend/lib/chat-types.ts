export type ResearchMode =
  | "ask"
  | "summarize"
  | "compare"
  | "methodology"
  | "evidence"
  | "literature_review"
  | "citation"
  | "explain";

export type GroundingStatus = "strong" | "partial" | "insufficient";

export interface ChatSource {
  index: number;
  publicationId?: string;
  documentId?: string;
  title: string;
  authors: string[];
  university?: string;
  repository?: string;
  sourceCode?: string;
  year?: number;
  pageStart?: number;
  pageEnd?: number;
  excerpt?: string;
  similarity?: number;
  documentUrl?: string;
  landingUrl?: string;
  previewUrl?: string;
  documentType?: string;
  chunkId?: string;
}

export interface ResearchChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  status: "pending" | "streaming" | "complete" | "failed" | "cancelled";
  citations: ChatSource[];
  retrievedDocumentCount?: number;
  retrievedChunkCount?: number;
  latencyMs?: number;
  modelName?: string;
  grounding?: GroundingStatus;
  mode?: ResearchMode;
  filters?: ChatFilters;
  warnings?: string[];
  followUpQuestions?: string[];
}

export interface ChatFilters {
  repositories: string[];
  universities: string[];
  documentTypes: string[];
  languages: string[];
  yearFrom?: number;
  yearTo?: number;
  minimumSimilarity: number;
  topDocuments: number;
  topChunks: number;
}

export interface ChatSettings {
  hybridSearch: boolean;
  includeFullText: boolean;
  includeMetadata: boolean;
  reranking: boolean;
  citationStrictness: "high" | "balanced";
  answerLength: "concise" | "balanced" | "detailed";
  responseLanguage: string;
}

export interface ResearchChatRequest {
  message: string;
  session_id?: string;
  mode?: ResearchMode;
  filters?: {
    repositories?: string[];
    universities?: string[];
    document_types?: string[];
    languages?: string[];
    year_from?: number;
    year_to?: number;
    minimum_similarity?: number;
  };
  retrieval?: {
    top_documents?: number;
    top_chunks?: number;
    hybrid_search?: boolean;
    rerank?: boolean;
    include_full_text?: boolean;
    include_metadata?: boolean;
    citation_strictness?: "high" | "balanced";
    answer_length?: "concise" | "balanced" | "detailed";
    response_language?: string;
  };
  publication_ids?: string[];
  document_ids?: string[];
  pinned_chunk_ids?: string[];
}

export interface ResearchChatResponse {
  session_id: string;
  message_id: string;
  answer: string;
  citations: Array<{
    index: number;
    publication_id?: string | null;
    document_id?: string | null;
    chunk_id?: string | null;
    title: string;
    authors?: string[];
    publication_year?: number | null;
    university?: string | null;
    repository?: string | null;
    source?: string | null;
    source_type?: string | null;
    page_start?: number | null;
    page_end?: number | null;
    excerpt?: string | null;
    similarity_score?: number | null;
    document_url?: string | null;
    landing_url?: string | null;
    preview_url?: string | null;
    document_type?: string | null;
  }>;
  retrieved_publications: string[];
  retrieved_document_count: number;
  retrieved_chunk_count: number;
  grounding_status: GroundingStatus;
  confidence: number;
  model: string;
  model_name: string;
  latency_ms: number | null;
  usage: Record<string, number>;
  warnings: string[];
  follow_up_questions: string[];
}

export interface WorkspaceAttachment {
  id: string;
  file: File;
  status: "ready" | "unsupported" | "too-large";
}

export interface ChatSessionSummary {
  id: string;
  university_id: string | null;
  title: string;
  is_pinned: boolean;
  last_model_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface StoredChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  citations: ResearchChatResponse["citations"];
  retrieved_publication_ids: string[];
  model_name: string | null;
  latency_ms: number | null;
  usage: Record<string, number>;
  warnings: string[];
  created_at: string;
}

export const defaultFilters: ChatFilters = {
  repositories: [],
  universities: [],
  documentTypes: [],
  languages: [],
  minimumSimilarity: 0.35,
  topDocuments: 5,
  topChunks: 10,
};

export const defaultSettings: ChatSettings = {
  hybridSearch: true,
  includeFullText: true,
  includeMetadata: true,
  reranking: true,
  citationStrictness: "high",
  answerLength: "balanced",
  responseLanguage: "English",
};
