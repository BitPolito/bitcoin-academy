import { apiFetch } from '@/lib/api';
import type { EvidencePack } from '@/lib/api/types';

export interface PipelineHealth {
  chroma_status: string;
  collection_sizes: Record<string, number>;
  uploads_dir_size_mb: number;
  python_version: string;
  chroma_db_path: string;
}

export async function getPipelineHealth(accessToken?: string): Promise<PipelineHealth> {
  return apiFetch<PipelineHealth>('/debug/pipeline/health', { accessToken });
}

export async function getDocumentChunks(
  docId: string,
  accessToken?: string,
): Promise<Array<Record<string, unknown>>> {
  return apiFetch<Array<Record<string, unknown>>>(`/debug/documents/${docId}/chunks`, { accessToken });
}

export async function getParsedOutput(
  docId: string,
  accessToken?: string,
): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/debug/documents/${docId}/parsed`, { accessToken });
}

export async function testRetrieval(
  courseId: string,
  query: string,
  topK = 5,
  accessToken?: string,
): Promise<{ query: string; course_id: string; total: number; chunks: Array<Record<string, unknown>> }> {
  const params = new URLSearchParams({ query, top_k: String(topK) });
  return apiFetch(`/debug/courses/${courseId}/retrieval?${params}`, {
    method: 'POST',
    accessToken,
  });
}

export async function getEvidencePack(
  courseId: string,
  query: string,
  action = 'explain',
  accessToken?: string,
): Promise<EvidencePack> {
  const params = new URLSearchParams({ query, action });
  return apiFetch<EvidencePack>(`/debug/courses/${courseId}/evidence?${params}`, { accessToken });
}
