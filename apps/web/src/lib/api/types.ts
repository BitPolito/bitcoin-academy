// ── Processing pipeline stages ──────────────────────────────────────────
export type ProcessingStage =
  | 'queued'
  | 'uploading'
  | 'parsing'
  | 'normalizing'
  | 'chunking'
  | 'indexing'
  | 'done'
  | 'error';

export type DocumentStatus = 'uploading' | 'processing' | 'ready' | 'error';

// ── Wire types (raw JSON from API) ─────────────────────────────────────

export interface ApiCourse {
  id: number | string;
  title: string;
  description?: string;
}

export interface ApiLesson {
  id: number | string;
  title: string;
  content?: string;
}

export type MaterialType = 'lecture' | 'past_exam' | 'supplement';

export interface ApiDocumentListItem {
  id: string;
  course_id: string;
  filename: string;
  mime_type: string | null;
  size: number;
  status: DocumentStatus;
  processing_stage: ProcessingStage;
  error_message: string | null;
  indexing_status?: string | null;
  document_type: MaterialType;
  created_at: string;
  updated_at: string;
}

export interface ApiDocumentStatusResponse {
  id: string;
  status: DocumentStatus;
  processing_stage: ProcessingStage;
  error_message: string | null;
}

export interface ApiDocumentDetail {
  id: string;
  course_id: string;
  filename: string;
  mime_type: string | null;
  size: number;
  status: DocumentStatus;
  processing_stage: ProcessingStage;
  error_message: string | null;
  document_type: MaterialType;
  parser_used: string | null;
  page_count: number | null;
  chunk_count: number | null;
  indexing_status: string | null;
  metadata_json: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApiPreviewChunk {
  text: string;
  label: string | null;
  section: string | null;
}

export interface ApiDocumentPreview {
  id: string;
  filename: string;
  extracted_text_preview: string | null;
  page_count: number | null;
  chunk_count: number | null;
  sections: string[] | null;
  sample_chunks: ApiPreviewChunk[] | null;
}

export interface CreateCourseRequest {
  title: string;
  description?: string;
}

// ── UI types (consumed by components) ───────────────────────────────────

// ── Evidence pack (study action retrieval context) ──────────────────────

export interface CitationAnchor {
  doc_id: string;
  doc_name: string;
  section: string | null;
  page: number | null;
  slide: number | null;
  chunk_id: string;
  chunk_type: string;
}

export interface EvidenceChunk {
  chunk_id: string;
  text: string;
  score: number;
  anchor: CitationAnchor;
}

export interface EvidencePack {
  query: string;
  action: string;
  chunks: EvidenceChunk[];
  total_candidates: number;
}

export type StudyAction =
  | 'explain'
  | 'summarize'
  | 'retrieve'
  | 'open_questions'
  | 'quiz'
  | 'oral'
  | 'derive'
  | 'compare';

export interface ApiStudyRequest {
  action: StudyAction;
  query: string;
  rag_only?: boolean;
  /** Persisted study session (issue #136) this turn belongs to, if any. */
  session_id?: string;
}

export interface ApiCitationOut {
  snippet: string;
  score: number;
  label: string;
  page: number;
  slide: number;
  section: string;
  doc_id: string;
  chunk_id: string;
  chunk_type: string;
}

export interface ApiStudyResponse {
  answer: string;
  citations: ApiCitationOut[];
  retrieval_used: boolean;
  action: string;
  /** Id of the persisted turn, when session_id was provided and owned by the caller. */
  turn_id?: string | null;
}

// ── Study sessions (issue #136) ─────────────────────────────────────────────

export interface ApiTurnCitationOut {
  doc_id: string;
  doc_name: string;
  section?: string | null;
  page?: number | null;
  slide?: number | null;
  chunk_id?: string | null;
  chunk_type?: string | null;
  snippet: string;
}

export interface ApiStudyTurnOut {
  id: string;
  action: string;
  query: string;
  answer: string;
  citations: ApiTurnCitationOut[];
  duration_ms?: number | null;
  model_tier?: string | null;
  created_at: string;
}

export interface ApiStudySessionOut {
  id: string;
  course_id: string;
  title?: string | null;
  started_at: string;
  last_active_at: string;
  turn_count: number;
}

export interface ApiStudySessionDetailOut extends ApiStudySessionOut {
  turns: ApiStudyTurnOut[];
}

export interface DocumentListRow {
  id: string;
  courseId: string;
  filename: string;
  fileType: string;
  size: number;
  status: DocumentStatus;
  processingStage: ProcessingStage;
  isTerminal: boolean;
  errorMessage: string | null;
  indexingStatus: string | null;
  documentType: MaterialType;
  createdAt: string;
  updatedAt: string;
}

export interface DocumentDetailView {
  id: string;
  courseId: string;
  filename: string;
  fileType: string;
  size: number;
  status: DocumentStatus;
  processingStage: ProcessingStage;
  errorMessage: string | null;
  documentType: MaterialType;
  parserUsed: string | null;
  pageCount: number | null;
  chunkCount: number | null;
  indexingStatus: string | null;
  normalizedMetadata: Record<string, unknown> | null;
  createdAt: string;
  updatedAt: string;
}

export interface DocumentPreviewView {
  id: string;
  filename: string;
  extractedTextPreview: string | null;
  pageCount: number | null;
  chunkCount: number | null;
  sections: string[] | null;
  sampleChunks: ApiPreviewChunk[] | null;
}
export interface CursorPage<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
}
