export interface ResearchDocument {
  id: string;
  publication_id: string | null;
  source: string;
  title: string | null;
  document_url: string | null;
  landing_url: string | null;
  mime_type: string | null;
  file_size_bytes: number | null;
  page_count: number | null;
  extraction_status: string;
  extraction_error: string | null;
  metadata: Record<string, unknown>;
  extracted_at: string | null;
  chunk_count: number;
  character_count: number;
  embedded_chunk_count: number;
  embedding_model: string | null;
}
export interface ResearchDocumentPage {
  items: ResearchDocument[];
  total: number;
  limit: number;
  offset: number;
}
export interface DocumentChunk {
  id: string;
  document_id: string;
  chunk_index: number;
  page_start: number | null;
  page_end: number | null;
  section_title: string | null;
  content: string;
  character_count: number;
  embedding_model: string | null;
  embedded_at: string | null;
  content_type: string | null;
}
export interface DocumentChunkPage {
  items: DocumentChunk[];
  total: number;
  limit: number;
  offset: number;
}
