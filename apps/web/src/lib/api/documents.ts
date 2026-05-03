import { apiFetch, ApiError } from '@/lib/api';

const _API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NEXT_PUBLIC_API_URL
    ? `${process.env.NEXT_PUBLIC_API_URL}/api`
    : 'http://localhost:8000/api');
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
  documentType = 'lecture',
): Promise<ApiDocumentListItem> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('document_type', documentType);
  return apiFetch<ApiDocumentListItem>(`/courses/${courseId}/documents`, {
    method: 'POST',
    body: formData,
    accessToken,
  });
}

export async function retryDocument(
  documentId: string,
  accessToken?: string,
): Promise<ApiDocumentStatusResponse> {
  return apiFetch<ApiDocumentStatusResponse>(`/documents/${documentId}/retry`, {
    method: 'POST',
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

export function uploadDocumentWithProgress(
  courseId: string,
  file: File,
  accessToken: string | undefined,
  documentType: string,
  onProgress: (pct: number) => void,
): Promise<ApiDocumentListItem> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', documentType);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${_API_BASE}/courses/${courseId}/documents`);
    if (accessToken) xhr.setRequestHeader('Authorization', `Bearer ${accessToken}`);

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as ApiDocumentListItem);
        } catch {
          reject(new Error('Invalid server response'));
        }
      } else {
        let message = `Upload failed (${xhr.status})`;
        try {
          const body = JSON.parse(xhr.responseText) as { detail?: string };
          if (body.detail) message = body.detail;
        } catch {
          /* use default message */
        }
        reject(new Error(message));
      }
    });

    xhr.addEventListener('error', () => reject(new Error('Network error during upload')));
    xhr.addEventListener('abort', () => reject(new Error('Upload aborted')));

    xhr.send(formData);
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
