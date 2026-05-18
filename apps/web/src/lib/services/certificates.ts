import { apiFetch } from '@/lib/api';

export interface Certificate {
  id: string;
  course_id: string;
  course_name: string;
  issued_at: string;
  code: string;
  verify_url: string;
  grade_pct: number | null;
}

export async function issueCertificate(
  courseId: string,
  accessToken?: string
): Promise<Certificate> {
  return apiFetch<Certificate>(`/courses/${courseId}/certificates/issue`, {
    method: 'POST',
    accessToken,
  });
}

export async function getMyCertificates(accessToken?: string): Promise<Certificate[]> {
  const data = await apiFetch<{ items: Certificate[] }>('/users/me/certificates', { accessToken });
  return data.items;
}
