import { fetchDocumentPdf } from '@/lib/api/documents';

const mockFetch = jest.fn();
const originalFetch = global.fetch;
beforeEach(() => { mockFetch.mockReset(); global.fetch = mockFetch; });
afterAll(() => { global.fetch = originalFetch; });

it('fetches PDF bytes with the bearer token, cancellation and no cache', async () => {
  const pdf = new Blob(['%PDF-1.7'], { type: 'application/pdf' });
  mockFetch.mockResolvedValue({ ok: true, blob: async () => pdf });
  const signal = new AbortController().signal;
  expect(await fetchDocumentPdf('doc/id', 'token', signal)).toBe(pdf);
  expect(mockFetch).toHaveBeenCalledWith(expect.stringMatching(/\/documents\/doc%2Fid\/file$/), {
    headers: { Authorization: 'Bearer token' }, signal, cache: 'no-store',
  });
});

it('preserves recovery guidance from the backend error envelope', async () => {
  mockFetch.mockResolvedValue({ ok: false, status: 404,
    json: async () => ({ error: { message: 'Original unavailable. Re-upload the document.' } }),
  });
  await expect(fetchDocumentPdf('doc', 'token')).rejects.toMatchObject({
    status: 404, message: 'Original unavailable. Re-upload the document.',
  });
});

it('handles a non-JSON failed response', async () => {
  mockFetch.mockResolvedValue({ ok: false, status: 503,
    json: async () => { throw new Error('not JSON'); },
  });
  await expect(fetchDocumentPdf('doc', 'token')).rejects.toMatchObject({
    status: 503, message: 'Could not load PDF (503).',
  });
});

it('rejects non-PDF content instead of showing an invalid preview', async () => {
  mockFetch.mockResolvedValue({ ok: true, blob: async () => new Blob(['login'], { type: 'text/html' }) });
  await expect(fetchDocumentPdf('doc', 'token')).rejects.toThrow('The source is not a PDF.');
});
