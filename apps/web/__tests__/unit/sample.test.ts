import { toDocumentListRow, toDocumentDetailView, toDocumentPreviewView } from '../../src/lib/api/adapters';
import type { ApiDocumentListItem, ApiDocumentDetail, ApiDocumentPreview } from '../../src/lib/api/types';

const baseListItem: ApiDocumentListItem = {
  id: 'doc-1',
  course_id: 'course-1',
  filename: 'lecture01.pdf',
  mime_type: 'application/pdf',
  size: 204800,
  status: 'ready',
  processing_stage: 'done',
  error_message: null,
  document_type: 'lecture',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

describe('toDocumentListRow', () => {
  it('maps id and courseId correctly', () => {
    const row = toDocumentListRow(baseListItem);
    expect(row.id).toBe('doc-1');
    expect(row.courseId).toBe('course-1');
  });

  it('detects PDF from mime type', () => {
    const row = toDocumentListRow(baseListItem);
    expect(row.fileType).toBe('PDF');
  });

  it('detects PPTX from mime type', () => {
    const row = toDocumentListRow({
      ...baseListItem,
      mime_type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      filename: 'slides.pptx',
    });
    expect(row.fileType).toBe('PPTX');
  });

  it('detects DOCX from mime type', () => {
    const row = toDocumentListRow({
      ...baseListItem,
      mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      filename: 'notes.docx',
    });
    expect(row.fileType).toBe('DOCX');
  });

  it('falls back to file extension when mime_type is null', () => {
    const row = toDocumentListRow({ ...baseListItem, mime_type: null, filename: 'handout.txt' });
    expect(row.fileType).toBe('TXT');
  });

  it('marks ready status as terminal', () => {
    const row = toDocumentListRow({ ...baseListItem, status: 'ready' });
    expect(row.isTerminal).toBe(true);
  });

  it('marks error status as terminal', () => {
    const row = toDocumentListRow({ ...baseListItem, status: 'error' });
    expect(row.isTerminal).toBe(true);
  });

  it('marks processing status as non-terminal', () => {
    const row = toDocumentListRow({ ...baseListItem, status: 'processing' });
    expect(row.isTerminal).toBe(false);
  });

  it('preserves uploading status as non-terminal', () => {
    const row = toDocumentListRow({ ...baseListItem, status: 'uploading' });
    expect(row.isTerminal).toBe(false);
  });
});

describe('toDocumentDetailView', () => {
  const baseDetail: ApiDocumentDetail = {
    ...baseListItem,
    parser_used: 'pymupdf',
    page_count: 10,
    chunk_count: 42,
    indexing_status: 'indexed',
    metadata_json: '{"author":"Satoshi"}',
  };

  it('parses metadata_json into an object', () => {
    const view = toDocumentDetailView(baseDetail);
    expect(view.normalizedMetadata).toEqual({ author: 'Satoshi' });
  });

  it('returns null for malformed metadata_json', () => {
    const view = toDocumentDetailView({ ...baseDetail, metadata_json: '{bad json' });
    expect(view.normalizedMetadata).toBeNull();
  });

  it('returns null when metadata_json is null', () => {
    const view = toDocumentDetailView({ ...baseDetail, metadata_json: null });
    expect(view.normalizedMetadata).toBeNull();
  });

  it('preserves page_count and chunk_count', () => {
    const view = toDocumentDetailView(baseDetail);
    expect(view.pageCount).toBe(10);
    expect(view.chunkCount).toBe(42);
  });

  it('maps parser_used to parserUsed', () => {
    const view = toDocumentDetailView(baseDetail);
    expect(view.parserUsed).toBe('pymupdf');
  });
});

describe('toDocumentPreviewView', () => {
  const basePreview: ApiDocumentPreview = {
    id: 'doc-1',
    filename: 'lecture01.pdf',
    extracted_text_preview: 'Bitcoin is a peer-to-peer...',
    page_count: 5,
    chunk_count: 12,
    sections: ['Introduction', 'Mining'],
    sample_chunks: [
      { text: 'chunk A text', label: 'slide-1', section: 'Introduction' },
      { text: 'chunk B text', label: null, section: null },
    ],
  };

  it('maps all scalar fields correctly', () => {
    const view = toDocumentPreviewView(basePreview);
    expect(view.id).toBe('doc-1');
    expect(view.filename).toBe('lecture01.pdf');
    expect(view.extractedTextPreview).toBe('Bitcoin is a peer-to-peer...');
    expect(view.pageCount).toBe(5);
    expect(view.chunkCount).toBe(12);
  });

  it('passes sections array through unchanged', () => {
    const view = toDocumentPreviewView(basePreview);
    expect(view.sections).toEqual(['Introduction', 'Mining']);
  });

  it('passes sample_chunks through as sampleChunks', () => {
    const view = toDocumentPreviewView(basePreview);
    expect(view.sampleChunks).toHaveLength(2);
    expect(view.sampleChunks![0].text).toBe('chunk A text');
  });

  it('handles null sections and sample_chunks', () => {
    const view = toDocumentPreviewView({ ...basePreview, sections: null, sample_chunks: null });
    expect(view.sections).toBeNull();
    expect(view.sampleChunks).toBeNull();
  });
});
