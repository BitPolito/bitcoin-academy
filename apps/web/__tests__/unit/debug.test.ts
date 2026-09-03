import {
  getDocumentChunks,
  getEvidencePack,
  getParsedOutput,
  getPipelineHealth,
  testRetrieval,
} from '@/lib/services/debug';

const mockFetch = jest.fn();
global.fetch = mockFetch as unknown as typeof fetch;

beforeEach(() => mockFetch.mockReset());

function mockJson(payload: unknown, status = 200) {
  mockFetch.mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response);
}

function lastCall(): [string, RequestInit] {
  return mockFetch.mock.calls[mockFetch.mock.calls.length - 1] as [string, RequestInit];
}

describe('debug service', () => {
  it('getPipelineHealth fetches the health endpoint with the token', async () => {
    const health = { bm25_indexes: ['c1'], uploads_dir_size_mb: 1.5, python_version: '3.12' };
    mockJson(health);

    await expect(getPipelineHealth('tok')).resolves.toEqual(health);

    const [url, init] = lastCall();
    expect(url).toContain('/debug/pipeline/health');
    expect(init.headers).toEqual(expect.objectContaining({ Authorization: 'Bearer tok' }));
  });

  it('getDocumentChunks and getParsedOutput target the right document paths', async () => {
    mockJson([{ id: 'chunk-1' }]);
    await getDocumentChunks('doc-1', 'tok');
    expect(lastCall()[0]).toContain('/debug/documents/doc-1/chunks');

    mockJson({ text: 'parsed' });
    await getParsedOutput('doc-1', 'tok');
    expect(lastCall()[0]).toContain('/debug/documents/doc-1/parsed');
  });

  it('testRetrieval POSTs with the default top_k when none is given', async () => {
    mockJson({ query: 'q', course_id: 'c1', total: 0, chunks: [] });

    await testRetrieval('c1', 'what is a utxo', undefined, 'tok');

    const [url, init] = lastCall();
    expect(init.method).toBe('POST');
    expect(url).toContain('/debug/courses/c1/retrieval?');
    expect(url).toContain('query=what+is+a+utxo');
    expect(url).toContain('top_k=5');
  });

  it('testRetrieval forwards an explicit top_k', async () => {
    mockJson({ query: 'q', course_id: 'c1', total: 0, chunks: [] });
    await testRetrieval('c1', 'q', 12, 'tok');
    expect(lastCall()[0]).toContain('top_k=12');
  });

  it('getEvidencePack uses the default action and encodes the query', async () => {
    mockJson({ chunks: [] });

    await getEvidencePack('c1', 'halving schedule', undefined, 'tok');
    let url = lastCall()[0];
    expect(url).toContain('/debug/courses/c1/evidence?');
    expect(url).toContain('action=explain');
    expect(url).toContain('query=halving+schedule');

    mockJson({ chunks: [] });
    await getEvidencePack('c1', 'q', 'derive', 'tok');
    url = lastCall()[0];
    expect(url).toContain('action=derive');
  });

  it('propagates API errors', async () => {
    mockJson({ detail: 'debug mode is off' }, 404);
    await expect(getPipelineHealth('tok')).rejects.toThrow('debug mode is off');
  });
});
