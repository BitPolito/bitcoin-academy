'use client';

import { useEffect, useState } from 'react';
import { fetchDocumentPdf } from '@/lib/api/documents';

interface Props {
  documentId: string;
  page: number;
  accessToken?: string;
}

interface Resource {
  documentId: string;
  accessToken: string;
  url?: string;
  error?: string;
}

export function PdfPreview({ documentId, page, accessToken }: Props) {
  const [resource, setResource] = useState<Resource | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setResource(null);
    if (!accessToken) return;
    const controller = new AbortController();
    let active = true;
    let objectUrl: string | undefined;

    fetchDocumentPdf(documentId, accessToken, controller.signal)
      .then((pdf) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(pdf);
        setResource({ documentId, accessToken, url: objectUrl });
      })
      .catch((error: unknown) => {
        if (!active) return;
        setResource({
          documentId, accessToken,
          error: error instanceof Error ? error.message : 'Could not load PDF.',
        });
      });

    return () => {
      active = false;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [documentId, accessToken, attempt]);

  if (!accessToken) return <p role="alert" className="p-6">Sign in to view the original PDF.</p>;
  // Do not show a previous document or session while the new request loads.
  const current = resource?.documentId === documentId && resource.accessToken === accessToken
    ? resource : null;
  if (!current) return <p role="status" className="p-6">Loading PDF…</p>;
  if (current.error) {
    return (
      <div role="alert" className="p-6">
        <p>{current.error}</p>
        <button onClick={() => setAttempt((n) => n + 1)} className="btn-ghost mt-3">Retry</button>
      </div>
    );
  }

  const targetPage = Number.isFinite(page) ? Math.max(1, Math.trunc(page)) : 1;
  const src = `${current.url}#page=${targetPage}`;
  return <iframe key={src} src={src} title="PDF viewer" className="w-full h-full border-0" />;
}
