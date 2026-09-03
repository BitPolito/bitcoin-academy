import { editOutline } from '@/lib/services/courseBuilder';

const mockFetch = jest.fn();
global.fetch = mockFetch as unknown as typeof fetch;

beforeEach(() => mockFetch.mockReset());

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
