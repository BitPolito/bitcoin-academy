import { apiFetch, ApiError } from '@/lib/api';

export type DocumentStatus = 'uploading' | 'processing' | 'ready' | 'error';

export interface CourseDocument {
  id: string;
  filename: string;
  size: number;
  status: DocumentStatus;
  error_message?: string;
  created_at: string;
}

export interface DocumentStatusResponse {
  id: string;
  status: DocumentStatus;
  progress?: number;
  error_message?: string;
}

export async function getDocuments(
  courseId: string,
  accessToken?: string
): Promise<CourseDocument[]> {
  return apiFetch<CourseDocument[]>(`/courses/${courseId}/documents`, {
    accessToken,
  });
}

export async function uploadDocument(
  courseId: string,
  file: File,
  accessToken?: string
): Promise<CourseDocument> {
  const formData = new FormData();
  formData.append('file', file);

  return apiFetch<CourseDocument>(`/courses/${courseId}/documents`, {
    method: 'POST',
    body: formData,
    accessToken,
  });
}

export async function getDocumentStatus(
  documentId: string,
  accessToken?: string
): Promise<DocumentStatusResponse> {
  return apiFetch<DocumentStatusResponse>(`/documents/${documentId}/status`, {
    accessToken,
  });
}

export async function deleteDocument(
  documentId: string,
  accessToken?: string
): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/documents/${documentId}`, {
    method: 'DELETE',
    accessToken,
  });
}

/**
 * Poll a document's status until it reaches a terminal state.
 * Returns the final status, or throws if polling times out.
 */
export async function pollDocumentStatus(
  documentId: string,
  accessToken?: string,
  intervalMs = 3000,
  maxAttempts = 60
): Promise<DocumentStatusResponse> {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const status = await getDocumentStatus(documentId, accessToken);
      if (status.status === 'ready' || status.status === 'error') {
        return status;
      }
    } catch (err) {
      if (err instanceof ApiError && err.status >= 500) {
        // Server error — keep polling
      } else {
        throw err;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error('Document processing timed out');
}
