/**
 * SSE streaming client for study actions.
 *
 * This is the path a student actually watches: tokens arriving one by one,
 * followed by citations delivered through an in-band sentinel. Every failure
 * mode here is silent from the UI's perspective — a mis-split chunk drops a
 * token, a malformed sentinel loses the citations, and a missing [DONE] leaves
 * the stream hanging.
 *
 * The reader is faked rather than mocked at the fetch level alone, so the
 * chunk-boundary handling is genuinely exercised.
 */
import { sendStudyActionStream } from '@/lib/services/study';

const CITATIONS_SENTINEL = '\x00CITATIONS\x00';

const mockFetch = jest.fn();
global.fetch = mockFetch as unknown as typeof fetch;

/** Build a Response whose body streams the given chunks verbatim. */
function streamingResponse(chunks: string[], status = 200): Response {
  const encoder = new TextEncoder();
  let i = 0;
  return {
    ok: status >= 200 && status < 300,
    status,
    body: {
      getReader: () => ({
        read: async () =>
          i < chunks.length
            ? { done: false, value: encoder.encode(chunks[i++]) }
            : { done: true, value: undefined },
      }),
    },
  } as unknown as Response;
}

function sse(payload: string): string {
  return `data: ${JSON.stringify(payload)}\n`;
}

beforeEach(() => {
  mockFetch.mockReset();
});

async function collect(chunks: string[]) {
  const tokens: string[] = [];
  const citations: unknown[] = [];
  mockFetch.mockResolvedValue(streamingResponse(chunks));

  await sendStudyActionStream(
    'course-1',
    'explain',
    'What is a UTXO?',
    (t) => tokens.push(t),
    (c) => citations.push(...c)
  );

  return { tokens, citations };
}

describe('sendStudyActionStream', () => {
  it('delivers each token in order', async () => {
    const { tokens } = await collect([sse('Bitcoin '), sse('uses '), sse('PoW.'), 'data: [DONE]\n']);

    expect(tokens).toEqual(['Bitcoin ', 'uses ', 'PoW.']);
  });

  it('reassembles a token split across two network chunks', async () => {
    // The reader emits arbitrary byte boundaries; a line split mid-way must not
    // be dropped or duplicated.
    const line = sse('complete token');
    const { tokens } = await collect([
      line.slice(0, 8),
      line.slice(8),
      'data: [DONE]\n',
    ]);

    expect(tokens).toEqual(['complete token']);
  });

  it('handles several SSE lines arriving in a single chunk', async () => {
    const { tokens } = await collect([sse('a') + sse('b') + sse('c'), 'data: [DONE]\n']);

    expect(tokens).toEqual(['a', 'b', 'c']);
  });

  it('stops at the [DONE] marker and ignores anything after it', async () => {
    const { tokens } = await collect([sse('kept'), 'data: [DONE]\n', sse('after done')]);

    expect(tokens).toEqual(['kept']);
  });

  it('parses citations from the sentinel and keeps them out of the token stream', async () => {
    const citationPayload = [{ snippet: 'PoW secures the chain', page: 3, doc_id: 'd1' }];
    const { tokens, citations } = await collect([
      sse('answer text'),
      sse(CITATIONS_SENTINEL + JSON.stringify(citationPayload)),
      'data: [DONE]\n',
    ]);

    expect(tokens).toEqual(['answer text']);
    expect(citations).toEqual(citationPayload);
  });

  it('ignores a malformed citations payload rather than failing the stream', async () => {
    const { tokens, citations } = await collect([
      sse('answer text'),
      sse(CITATIONS_SENTINEL + '{not valid json'),
      sse('more text'),
      'data: [DONE]\n',
    ]);

    expect(citations).toEqual([]);
    expect(tokens).toEqual(['answer text', 'more text']);
  });

  it('falls back to the raw payload when a token is not valid JSON', async () => {
    const { tokens } = await collect(['data: plain text token\n', 'data: [DONE]\n']);

    expect(tokens).toEqual(['plain text token']);
  });

  it('ignores lines that are not SSE data frames', async () => {
    const { tokens } = await collect([
      ': keep-alive comment\n',
      'event: ping\n',
      sse('real token'),
      'data: [DONE]\n',
    ]);

    expect(tokens).toEqual(['real token']);
  });

  it('completes when the stream ends without an explicit [DONE]', async () => {
    const { tokens } = await collect([sse('token')]);

    expect(tokens).toEqual(['token']);
  });

  it('posts the action, query and course to the stream endpoint', async () => {
    mockFetch.mockResolvedValue(streamingResponse(['data: [DONE]\n']));

    await sendStudyActionStream('course-9', 'quiz', 'Quiz me', () => {}, () => {}, 'token-1');

    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain('/courses/course-9/study/stream');
    expect(init.headers.Authorization).toBe('Bearer token-1');
    expect(JSON.parse(init.body)).toMatchObject({ action: 'quiz', query: 'Quiz me' });
  });

  it('sends rag_only only when retrieval-only mode is requested', async () => {
    mockFetch.mockResolvedValue(streamingResponse(['data: [DONE]\n']));
    await sendStudyActionStream('c1', 'explain', 'q', () => {}, () => {}, undefined, true);
    expect(JSON.parse(mockFetch.mock.calls[0][1].body).rag_only).toBe(true);

    mockFetch.mockResolvedValue(streamingResponse(['data: [DONE]\n']));
    await sendStudyActionStream('c1', 'explain', 'q', () => {}, () => {});
    expect(JSON.parse(mockFetch.mock.calls[1][1].body)).not.toHaveProperty('rag_only');
  });

  it('reports rate limiting in a message the user can act on', async () => {
    mockFetch.mockResolvedValue(streamingResponse([], 429));

    await expect(
      sendStudyActionStream('c1', 'explain', 'q', () => {}, () => {})
    ).rejects.toThrow(/Troppe richieste/);
  });

  it('reports the status code for other failures', async () => {
    mockFetch.mockResolvedValue(streamingResponse([], 500));

    await expect(
      sendStudyActionStream('c1', 'explain', 'q', () => {}, () => {})
    ).rejects.toThrow('Stream request failed (500)');
  });

  it('fails clearly when the response carries no body', async () => {
    mockFetch.mockResolvedValue({ ok: true, status: 200, body: null } as Response);

    await expect(
      sendStudyActionStream('c1', 'explain', 'q', () => {}, () => {})
    ).rejects.toThrow('Stream response body is null');
  });
});
