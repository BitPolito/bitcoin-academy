import {
  approveLesson,
  editOutline,
  generateContent,
  generateOutline,
  getGenerationRun,
  getLessonContent,
  getOutline,
  patchLesson,
  publishCourse,
} from '@/lib/services/courseBuilder';

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

describe('course builder outline editing', () => {
  it('persists a typed outline action and forwards authorization', async () => {
    const outline = { course_id: 'course-1', chapters: [] };
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => outline,
    } as Response);

    await expect(
      editOutline(
        'course-1',
        { action: 'move_lesson', lesson_id: 'lesson-1', target_chapter_id: 'chapter-2' },
        'token-1'
      )
    ).resolves.toEqual(outline);

    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/courses/course-1/outline/actions');
    expect(init.method).toBe('POST');
    expect(init.headers).toEqual(expect.objectContaining({ Authorization: 'Bearer token-1' }));
    expect(JSON.parse(init.body as string)).toEqual({
      action: 'move_lesson',
      lesson_id: 'lesson-1',
      target_chapter_id: 'chapter-2',
    });
  });
});

describe('course builder API wrappers', () => {
  it('getOutline issues a GET and forwards the token', async () => {
    const outline = { course_id: 'c1', chapters: [] };
    mockJson(outline);

    await expect(getOutline('c1', 'tok')).resolves.toEqual(outline);

    const [url, init] = lastCall();
    expect(url).toContain('/courses/c1/outline');
    expect(init.method ?? 'GET').toBe('GET');
    expect(init.headers).toEqual(expect.objectContaining({ Authorization: 'Bearer tok' }));
  });

  it('generateOutline POSTs an empty body', async () => {
    mockJson({ run_id: 'r1', status: 'queued' });

    await expect(generateOutline('c1', 'tok')).resolves.toEqual({ run_id: 'r1', status: 'queued' });

    const [url, init] = lastCall();
    expect(url).toContain('/courses/c1/outline/generate');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({});
  });

  it('generateContent sends lesson_ids only when provided', async () => {
    mockJson({ run_id: 'r1', status: 'queued', draft_lessons: 2 });
    await generateContent('c1', ['l1', 'l2'], 'tok');
    expect(JSON.parse(lastCall()[1].body as string)).toEqual({ lesson_ids: ['l1', 'l2'] });

    mockJson({ run_id: 'r2', status: 'queued', draft_lessons: 0 });
    await generateContent('c1', undefined, 'tok');
    expect(JSON.parse(lastCall()[1].body as string)).toEqual({});
  });

  it('publishCourse POSTs to the publish endpoint', async () => {
    const result = { published_chapters: 1, published_lessons: 3, skipped_chapters: 0 };
    mockJson(result);

    await expect(publishCourse('c1', 'tok')).resolves.toEqual(result);

    const [url, init] = lastCall();
    expect(url).toContain('/courses/c1/publish');
    expect(init.method).toBe('POST');
  });

  it('getGenerationRun polls a run by id', async () => {
    mockJson({ id: 'run-9', course_id: 'c1', status: 'running', created_at: 'now' });

    await expect(getGenerationRun('run-9', 'tok')).resolves.toEqual(
      expect.objectContaining({ id: 'run-9', status: 'running' })
    );
    expect(lastCall()[0]).toContain('/generation-runs/run-9');
  });

  it('getLessonContent fetches a lesson', async () => {
    mockJson({ id: 'l1', title: 'Intro', content: '...', order_index: 0, source_refs: [], review_issues: [] });

    await expect(getLessonContent('l1', 'tok')).resolves.toEqual(
      expect.objectContaining({ id: 'l1', title: 'Intro' })
    );
    expect(lastCall()[0]).toContain('/lessons/l1/content');
  });

  it('patchLesson PATCHes the provided fields', async () => {
    mockJson({ id: 'l1', title: 'New', content: 'x', order_index: 0, source_refs: [], review_issues: [] });

    await patchLesson('l1', { title: 'New', content: 'x' }, 'tok');

    const [url, init] = lastCall();
    expect(url).toContain('/lessons/l1');
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body as string)).toEqual({ title: 'New', content: 'x' });
  });

  it('approveLesson POSTs to the approve endpoint', async () => {
    mockJson({ id: 'l1', status: 'published' });

    await expect(approveLesson('l1', 'tok')).resolves.toEqual({ id: 'l1', status: 'published' });

    const [url, init] = lastCall();
    expect(url).toContain('/lessons/l1/approve');
    expect(init.method).toBe('POST');
  });

  it('propagates API errors', async () => {
    mockJson({ detail: 'nope' }, 403);
    await expect(getOutline('c1', 'tok')).rejects.toThrow('nope');
  });
});
