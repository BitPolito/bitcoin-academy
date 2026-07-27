/**
 * API client — the boundary every frontend request crosses.
 *
 * This layer had no coverage. It is where authentication headers are attached,
 * where FormData must not be JSON-stringified, and where backend errors are
 * turned into something the UI can render. All three fail silently if wrong:
 * a missing Authorization header looks like a logged-out user, a stringified
 * FormData looks like a corrupt upload, and a swallowed error message shows the
 * user "Request failed" instead of what actually went wrong.
 */
import { ApiError, apiFetch } from '@/lib/api';
import { sendStudyAction } from '@/lib/services/study';

const mockFetch = jest.fn();
global.fetch = mockFetch as unknown as typeof fetch;

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

beforeEach(() => {
  mockFetch.mockReset();
});

describe('apiFetch', () => {
  it('returns the parsed JSON body on success', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ id: 'course-1' }));

    const result = await apiFetch<{ id: string }>('/courses/course-1');

    expect(result).toEqual({ id: 'course-1' });
  });

  it('prefixes the endpoint with the API base URL', async () => {
    mockFetch.mockResolvedValue(jsonResponse({}));

    await apiFetch('/courses');

    const [url] = mockFetch.mock.calls[0];
    expect(url).toMatch(/\/api\/courses$/);
  });

  it('attaches the bearer token when an access token is supplied', async () => {
    mockFetch.mockResolvedValue(jsonResponse({}));

    await apiFetch('/courses', { accessToken: 'token-abc' });

    const [, init] = mockFetch.mock.calls[0];
    expect(init.headers.Authorization).toBe('Bearer token-abc');
  });

  it('omits the Authorization header when no token is supplied', async () => {
    mockFetch.mockResolvedValue(jsonResponse({}));

    await apiFetch('/courses');

    const [, init] = mockFetch.mock.calls[0];
    expect(init.headers.Authorization).toBeUndefined();
  });

  it('serialises a JSON body and sets the content type', async () => {
    mockFetch.mockResolvedValue(jsonResponse({}));

    await apiFetch('/courses', { method: 'POST', body: { title: 'Bitcoin' } });

    const [, init] = mockFetch.mock.calls[0];
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(init.body).toBe(JSON.stringify({ title: 'Bitcoin' }));
  });

  it('passes FormData through untouched and lets the browser set the boundary', async () => {
    // Setting Content-Type manually on a multipart request omits the boundary
    // and the upload fails server-side with an unhelpful parse error.
    mockFetch.mockResolvedValue(jsonResponse({}));
    const form = new FormData();
    form.append('file', new Blob(['x']), 'lecture.pdf');

    await apiFetch('/courses/c1/documents', { method: 'POST', body: form });

    const [, init] = mockFetch.mock.calls[0];
    expect(init.body).toBe(form);
    expect(init.headers['Content-Type']).toBeUndefined();
  });

  it('sends no body when none is provided', async () => {
    mockFetch.mockResolvedValue(jsonResponse({}));

    await apiFetch('/courses');

    const [, init] = mockFetch.mock.calls[0];
    expect(init.body).toBeUndefined();
  });

  it('preserves caller-supplied headers', async () => {
    mockFetch.mockResolvedValue(jsonResponse({}));

    await apiFetch('/courses', { headers: { 'X-Request-ID': 'req-1' } });

    const [, init] = mockFetch.mock.calls[0];
    expect(init.headers['X-Request-ID']).toBe('req-1');
  });

  it('throws an ApiError carrying the HTTP status', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ detail: 'Course not found' }, 404));

    await expect(apiFetch('/courses/missing')).rejects.toThrow(ApiError);
    await expect(apiFetch('/courses/missing')).rejects.toMatchObject({ status: 404 });
  });

  it('surfaces the backend detail message', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ detail: 'Course not found' }, 404));

    await expect(apiFetch('/courses/missing')).rejects.toThrow('Course not found');
  });

  it('falls back to the message field when detail is absent', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ message: 'Validation failed' }, 422));

    await expect(apiFetch('/courses')).rejects.toThrow('Validation failed');
  });

  it('falls back to a generic message when the error body is unparseable', async () => {
    // A 502 from a proxy returns HTML, not JSON — this must not throw a
    // SyntaxError that masks the real status.
    mockFetch.mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => {
        throw new SyntaxError('Unexpected token < in JSON');
      },
    } as unknown as Response);

    await expect(apiFetch('/courses')).rejects.toThrow('Request failed (502)');
  });

  it('exposes the full error body for callers that need it', async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({ detail: 'Invalid', fields: ['title'] }, 422)
    );

    await expect(apiFetch('/courses')).rejects.toMatchObject({
      details: { detail: 'Invalid', fields: ['title'] },
    });
  });
});

describe('ApiError', () => {
  it('is identifiable by name for error boundaries', () => {
    expect(new ApiError(500, 'boom').name).toBe('ApiError');
  });

  it('is an instance of Error', () => {
    expect(new ApiError(500, 'boom')).toBeInstanceOf(Error);
  });
});

describe('sendStudyAction', () => {
  it('posts the action and query to the course study endpoint', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ answer: 'a', citations: [] }));

    await sendStudyAction('course-1', 'explain', 'What is a UTXO?');

    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain('/courses/course-1/study');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toMatchObject({
      action: 'explain',
      query: 'What is a UTXO?',
    });
  });

  it('omits rag_only unless explicitly requested', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ answer: 'a', citations: [] }));

    await sendStudyAction('course-1', 'explain', 'question text');

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body).not.toHaveProperty('rag_only');
  });

  it('sends rag_only when retrieval-only mode is requested', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ answer: 'a', citations: [] }));

    await sendStudyAction('course-1', 'explain', 'question text', undefined, true);

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.rag_only).toBe(true);
  });

  it('forwards the access token', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ answer: 'a', citations: [] }));

    await sendStudyAction('course-1', 'quiz', 'question text', 'token-xyz');

    const [, init] = mockFetch.mock.calls[0];
    expect(init.headers.Authorization).toBe('Bearer token-xyz');
  });

  it('propagates API errors to the caller', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ detail: 'Course not found' }, 404));

    await expect(
      sendStudyAction('missing-course', 'explain', 'question text')
    ).rejects.toThrow(ApiError);
  });
});
