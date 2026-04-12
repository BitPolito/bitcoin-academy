import type {
  ApiDocumentListItem,
  ApiDocumentDetail,
  ApiDocumentPreview,
  DocumentListRow,
  DocumentDetailView,
  DocumentPreviewView,
  DocumentStatus,
  ProcessingStage,
} from './types';

function mimeToLabel(mime: string | null, filename: string): string {
  if (mime) {
    const sub = mime.split('/')[1];
    if (sub === 'pdf') return 'PDF';
    if (sub === 'vnd.openxmlformats-officedocument.presentationml.presentation') return 'PPTX';
    if (sub === 'vnd.openxmlformats-officedocument.wordprocessingml.document') return 'DOCX';
    if (sub === 'plain') return 'TXT';
    if (sub) return sub.toUpperCase();
  }
  const ext = filename.split('.').pop()?.toUpperCase();
  return ext || 'FILE';
}

const TERMINAL_STATUSES: ReadonlySet<DocumentStatus> = new Set(['ready', 'error']);

export function toDocumentListRow(item: ApiDocumentListItem): DocumentListRow {
  return {
    id: item.id,
    courseId: item.course_id,
    filename: item.filename,
    fileType: mimeToLabel(item.mime_type, item.filename),
    size: item.size,
    status: item.status,
    processingStage: item.processing_stage,
    isTerminal: TERMINAL_STATUSES.has(item.status),
    errorMessage: item.error_message,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
  };
}

export function toDocumentDetailView(item: ApiDocumentDetail): DocumentDetailView {
  let normalizedMetadata: Record<string, unknown> | null = null;
  if (item.metadata_json) {
    try {
      normalizedMetadata = JSON.parse(item.metadata_json);
    } catch {
      normalizedMetadata = null;
    }
  }

  return {
    id: item.id,
    courseId: item.course_id,
    filename: item.filename,
    fileType: mimeToLabel(item.mime_type, item.filename),
    size: item.size,
    status: item.status,
    processingStage: item.processing_stage,
    errorMessage: item.error_message,
    parserUsed: item.parser_used,
    pageCount: item.page_count,
    chunkCount: item.chunk_count,
    indexingStatus: item.indexing_status,
    normalizedMetadata,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
  };
}

export function toDocumentPreviewView(item: ApiDocumentPreview): DocumentPreviewView {
  return {
    id: item.id,
    filename: item.filename,
    extractedTextPreview: item.extracted_text_preview,
    pageCount: item.page_count,
    sections: item.sections,
    sampleChunks: item.sample_chunks,
  };
}
