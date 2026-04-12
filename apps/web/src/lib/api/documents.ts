import { apiFetch, ApiError } from '@/lib/api';
import type {
  ApiDocumentListItem,
  ApiDocumentDetail,
  ApiDocumentPreview,
  ApiDocumentStatusResponse,
  DocumentListRow,
  DocumentDetailView,
  DocumentPreviewView,
} from './types';
import { toDocumentListRow, toDocumentDetailView, toDocumentPreviewView } from './adapters';

// ── Raw API calls (wire types) ──────────────────────────────────────────

export async function fetchDocumentsList(
  courseId: string,
  accessToken?: string,
): Promise<ApiDocumentListItem[]> {
  return apiFetch<ApiDocumentListItem[]>(`/courses/${courseId}/documents`, {
    accessToken,
  });
}

export async function fetchDocumentStatus(
  documentId: string,
  accessToken?: string,
): Promise<ApiDocumentStatusResponse> {
  return apiFetch<ApiDocumentStatusResponse>(`/documents/${documentId}/status`, {
    accessToken,
  });
}

export async function fetchDocumentDetail(
  documentId: string,
  accessToken?: string,
): Promise<ApiDocumentDetail> {
  return apiFetch<ApiDocumentDetail>(`/documents/${documentId}`, {
    accessToken,
  });
}

export async function fetchDocumentPreview(
  documentId: string,
  accessToken?: string,
): Promise<ApiDocumentPreview> {
  return apiFetch<ApiDocumentPreview>(`/documents/${documentId}/preview`, {
    accessToken,
  });
}

export async function uploadDocument(
  courseId: string,
  file: File,
  accessToken?: string,
): Promise<ApiDocumentListItem> {
  const formData = new FormData();
  formData.append('file', file);
  return apiFetch<ApiDocumentListItem>(`/courses/${courseId}/documents`, {
    method: 'POST',
    body: formData,
    accessToken,
  });
}

export async function deleteDocument(
  documentId: string,
  accessToken?: string,
): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/documents/${documentId}`, {
    method: 'DELETE',
    accessToken,
  });
}

// ── Adapted calls (UI types) ───────────────────────────────────────────

export async function getDocumentListRows(
  courseId: string,
  accessToken?: string,
): Promise<DocumentListRow[]> {
  const items = await fetchDocumentsList(courseId, accessToken);
  return items.map(toDocumentListRow);
}

export async function getDocumentDetailView(
  documentId: string,
  accessToken?: string,
): Promise<DocumentDetailView> {
  const item = await fetchDocumentDetail(documentId, accessToken);
  return toDocumentDetailView(item);
}

export async function getDocumentPreviewView(
  documentId: string,
  accessToken?: string,
): Promise<DocumentPreviewView> {
  const item = await fetchDocumentPreview(documentId, accessToken);
  return toDocumentPreviewView(item);
}

// ── Polling helper ──────────────────────────────────────────────────────

export async function pollDocumentUntilTerminal(
  documentId: string,
  accessToken?: string,
  intervalMs = 3000,
  maxAttempts = 60,
): Promise<ApiDocumentStatusResponse> {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const status = await fetchDocumentStatus(documentId, accessToken);
      if (status.status === 'ready' || status.status === 'error') {
        return status;
      }
    } catch (err) {
      if (err instanceof ApiError && err.status >= 500) {
        // transient — keep polling
      } else {
        throw err;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error('Document processing timed out');
}
