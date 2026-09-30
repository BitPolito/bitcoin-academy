/**
 * Assessment, certificate and health service clients.
 *
 * Small modules, but each carries a shape assumption that only shows up at
 * runtime: the certificate list is unwrapped from a paginated envelope, the
 * health endpoint is called outside the `/api` prefix, and quiz answers are
 * posted as a map the backend has to recognise.
 */
import {
  generateChapterTest,
  getChapterTest,
  submitQuizAttempt,
} from '@/lib/services/chapterTests';
import { getMyCertificates, issueCertificate } from '@/lib/services/certificates';
import { fetchHealthStatus } from '@/lib/services/health';

const mockFetch = jest.fn();
global.fetch = mockFetch as unknown as typeof fetch;

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function lastCall() {
  const [url, init] = mockFetch.mock.calls[mockFetch.mock.calls.length - 1];
  return { url: url as string, init: (init ?? {}) as RequestInit & { headers: Record<string, string> } };
}

beforeEach(() => {
  mockFetch.mockReset();
});

// ---------------------------------------------------------------------------
// Chapter tests
// ---------------------------------------------------------------------------

describe('chapter test service', () => {
  it('generates a chapter test with POST', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ id: 'ct-1' }));

    await generateChapterTest('chapter-1', 'token-1');

    const { url, init } = lastCall();
    expect(url).toContain('/chapters/chapter-1/test/generate');
    expect(init.method).toBe('POST');
    expect(init.headers.Authorization).toBe('Bearer token-1');
  });

  it('reads a chapter test without a method override', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ id: 'ct-1', questions: [] }));

    await getChapterTest('chapter-1');

    const { url, init } = lastCall();
    expect(url).toContain('/chapters/chapter-1/test');
    expect(init.method).toBeUndefined();
  });

  it('posts answers keyed by question id', async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({
        attempt_id: 'a-1',
        score_pct: 75,
        passed: true,
        correct_count: 3,
        total_count: 4,
        corrections: [],
      })
    );

    await submitQuizAttempt('quiz-1', { q1: 'opt-a', q2: 'opt-c' });

    const { url, init } = lastCall();
    expect(url).toContain('/quizzes/quiz-1/attempts');
    expect(JSON.parse(init.body as string)).toEqual({
      answers: { q1: 'opt-a', q2: 'opt-c' },
    });
  });

  it('returns the attempt result including corrections', async () => {
    const result = {
      attempt_id: 'a-1',
      score_pct: 50,
      passed: false,
      correct_count: 1,
      total_count: 2,
      corrections: [
        {
          question_id: 'q1',
          correct_option_id: 'opt-a',
          selected_option_id: 'opt-b',
          is_correct: false,
        },
      ],
    };
    mockFetch.mockResolvedValue(jsonResponse(result));

    await expect(submitQuizAttempt('quiz-1', { q1: 'opt-b' })).resolves.toEqual(result);
  });

  it('submits an empty answer map without failing', async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({
        attempt_id: 'a-1',
        score_pct: 0,
        passed: false,
        correct_count: 0,
        total_count: 2,
        corrections: [],
      })
    );

    const result = await submitQuizAttempt('quiz-1', {});

    expect(result.score_pct).toBe(0);
    expect(JSON.parse(lastCall().init.body as string)).toEqual({ answers: {} });
  });
});

// ---------------------------------------------------------------------------
// Certificates
// ---------------------------------------------------------------------------

describe('certificates service', () => {
  it('issues a certificate for a course', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ id: 'cert-1', code: 'ABC' }));

    await issueCertificate('course-1', 'token-1');

    const { url, init } = lastCall();
    expect(url).toContain('/courses/course-1/certificates/issue');
    expect(init.method).toBe('POST');
  });

  it('unwraps the paginated envelope when listing certificates', async () => {
    // The endpoint returns {"items": [...]}, not a bare array — returning the
    // envelope would break every `.map` at the call site.
    const certs = [{ id: 'cert-1', code: 'ABC' }];
    mockFetch.mockResolvedValue(jsonResponse({ items: certs }));

    await expect(getMyCertificates('token-1')).resolves.toEqual(certs);
  });

  it('returns an empty list when the user holds no certificates', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ items: [] }));

    await expect(getMyCertificates()).resolves.toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

describe('health service', () => {
  it('calls /health outside the /api prefix', async () => {
    // The health endpoint is mounted at the service root, so reusing the API
    // base URL unchanged would produce /api/health and always 404.
    mockFetch.mockResolvedValue(
      jsonResponse({ status: 'healthy', database: 'connected', qvac: 'connected', cache: 'redis' })
    );

    await fetchHealthStatus();

    expect(lastCall().url).toMatch(/\/health$/);
    expect(lastCall().url).not.toContain('/api/health');
  });

  it('requests a fresh status rather than a cached one', async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({ status: 'healthy', database: 'connected', qvac: 'connected', cache: 'redis' })
    );

    await fetchHealthStatus();

    expect(lastCall().init).toMatchObject({ cache: 'no-store' });
  });

  it('returns the degraded status verbatim', async () => {
    const degraded = {
      status: 'degraded',
      database: 'disconnected',
      qvac: 'unreachable',
      cache: 'in-memory',
    };
    mockFetch.mockResolvedValue(jsonResponse(degraded));

    await expect(fetchHealthStatus()).resolves.toEqual(degraded);
  });

  it('throws with the status code when the health check itself fails', async () => {
    mockFetch.mockResolvedValue(jsonResponse({}, 503));

    await expect(fetchHealthStatus()).rejects.toThrow('Health check failed (503)');
  });
});
