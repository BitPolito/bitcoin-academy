/**
 * Integration tests for sendChatMessageStream — verifies SSE parsing logic
 * end-to-end with a mocked fetch, covering token delivery, citation extraction,
 * and error handling without hitting the network.
 */
import { TextDecoder } from 'util';
import { sendChatMessageStream } from '../../src/lib/services/chat';

// jsdom does not expose TextDecoder globally; polyfill from Node's util module.
Object.assign(global, { TextDecoder });

function makeStreamResponse(lines: string[]): Response {
  const body = lines.join('\n') + '\n';
  const chunks = [Buffer.from(body)];
  let idx = 0;

  const mockReader = {
    read: jest.fn().mockImplementation(() => {
      if (idx < chunks.length) {
        return Promise.resolve({ done: false, value: chunks[idx++] });
      }
      return Promise.resolve({ done: true, value: undefined });
    }),
    releaseLock: jest.fn(),
  };

  const mockResponse = {
    ok: true,
    status: 200,
    body: { getReader: () => mockReader },
  } as unknown as Response;

  return mockResponse;
}

const mockFetch = jest.fn();

beforeAll(() => {
  global.fetch = mockFetch;
});

afterAll(() => {
  // @ts-expect-error restoring
  delete global.fetch;
});

describe('sendChatMessageStream', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('delivers tokens in order via onToken callback', async () => {
    mockFetch.mockResolvedValue(makeStreamResponse([
      'data: "Hello"',
      'data: " world"',
      'data: [DONE]',
    ]));

    const tokens: string[] = [];
    await sendChatMessageStream('c1', 'hi', (t) => tokens.push(t), jest.fn(), 'tok');

    expect(tokens).toEqual(['Hello', ' world']);
  });

  it('delivers citations via onCitations when [CITATIONS] line appears', async () => {
    const citations = [{ snippet: 'UTXO basics', score: 0.9 }];
    mockFetch.mockResolvedValue(makeStreamResponse([
      'data: "answer"',
      `data: [CITATIONS]${JSON.stringify(citations)}`,
      'data: [DONE]',
    ]));

    const received: unknown[] = [];
    await sendChatMessageStream('c1', 'q', jest.fn(), (c) => received.push(c), 'tok');

    expect(received).toHaveLength(1);
    expect((received[0] as typeof citations)[0].snippet).toBe('UTXO basics');
  });

  it('ignores lines that do not start with "data: "', async () => {
    mockFetch.mockResolvedValue(makeStreamResponse([
      'event: start',
      ': keep-alive',
      'data: "token1"',
      'data: [DONE]',
    ]));

    const tokens: string[] = [];
    await sendChatMessageStream('c1', 'q', (t) => tokens.push(t), jest.fn(), 'tok');

    expect(tokens).toEqual(['token1']);
  });

  it('stops processing after [DONE] even if more lines follow', async () => {
    mockFetch.mockResolvedValue(makeStreamResponse([
      'data: "first"',
      'data: [DONE]',
      'data: "should not arrive"',
    ]));

    const tokens: string[] = [];
    await sendChatMessageStream('c1', 'q', (t) => tokens.push(t), jest.fn());

    expect(tokens).toEqual(['first']);
  });

  it('throws when the server returns a non-2xx status', async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 429, body: null } as unknown as Response);

    await expect(
      sendChatMessageStream('c1', 'q', jest.fn(), jest.fn())
    ).rejects.toThrow('429');
  });

  it('passes courseId, message, history, and auth header to fetch', async () => {
    mockFetch.mockResolvedValue(makeStreamResponse(['data: [DONE]']));

    await sendChatMessageStream(
      'btc-101',
      'What is mining?',
      jest.fn(),
      jest.fn(),
      'my-token',
      [{ role: 'user', content: 'prev question' }],
    );

    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('btc-101');
    expect((init.headers as Record<string, string>)['Authorization']).toBe('Bearer my-token');
    const body = JSON.parse(init.body as string);
    expect(body.message).toBe('What is mining?');
    expect(body.history).toHaveLength(1);
  });
});
