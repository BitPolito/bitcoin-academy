/**
 * Frontend service layer — the boundary between the UI and the backend.
 *
 * These modules had no coverage at all, and they are where a backend contract
 * change breaks the interface silently: a renamed field turns into `undefined`
 * on screen rather than an error anyone notices.
 *
 * The snake_case → camelCase mapping in the progress service is the clearest
 * example — nothing else in the app would reveal a mismatch.
 */
import {
  createCourse,
  deleteCourse,
  getCourse,
  getCourseLessons,
  getCourses,
  getLesson,
  updateCourse,
} from '@/lib/services/courses';
import {
  getCourseProgress,
  getUserBadges,
  markLessonComplete,
} from '@/lib/services/progress';
import {
  deleteDocument,
  getDocumentStatus,
  getDocuments,
  uploadDocument,
} from '@/lib/services/documents';

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
  return { url: url as string, init: init as RequestInit & { headers: Record<string, string> } };
}

beforeEach(() => {
  mockFetch.mockReset();
});

// ---------------------------------------------------------------------------
// Courses
// ---------------------------------------------------------------------------

describe('courses service', () => {
  it('requests the course list with pagination parameters', async () => {
    mockFetch.mockResolvedValue(jsonResponse([]));

    await getCourses(10, 25);

    expect(lastCall().url).toContain('/courses?skip=10&limit=25');
  });

  it('defaults to the first page when no parameters are given', async () => {
    mockFetch.mockResolvedValue(jsonResponse([]));

    await getCourses();

    expect(lastCall().url).toContain('skip=0');
    expect(lastCall().url).toContain('limit=100');
  });

  it('returns the course list unchanged', async () => {
    const courses = [{ id: 1, title: 'Bitcoin' }];
    mockFetch.mockResolvedValue(jsonResponse(courses));

    await expect(getCourses()).resolves.toEqual(courses);
  });

  it('forwards the access token when listing courses', async () => {
    mockFetch.mockResolvedValue(jsonResponse([]));

    await getCourses(0, 100, 'token-1');

    expect(lastCall().init.headers.Authorization).toBe('Bearer token-1');
  });

  it('fetches a single course by id', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ id: 1, title: 'Bitcoin' }));

    await getCourse('course-1');

    expect(lastCall().url).toContain('/courses/course-1');
  });

  it('fetches the lessons of a course', async () => {
    mockFetch.mockResolvedValue(jsonResponse([]));

    await getCourseLessons('course-1');

    expect(lastCall().url).toContain('/courses/course-1/lessons');
  });

  it('fetches a single lesson by id', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ id: 2, title: 'Mining' }));

    await getLesson('lesson-2');

    expect(lastCall().url).toContain('/lessons/lesson-2');
  });

  it('creates a course with title and description', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ id: 1, title: 'New' }));

    await createCourse('New', 'A description');

    const { init } = lastCall();
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({
      title: 'New',
      description: 'A description',
    });
  });

  it('updates a course with PATCH', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ id: 1, title: 'Renamed' }));

    await updateCourse('course-1', 'Renamed', 'Updated', 'token-1');

    const { url, init } = lastCall();
    expect(url).toContain('/courses/course-1');
    expect(init.method).toBe('PATCH');
    expect(init.headers.Authorization).toBe('Bearer token-1');
  });

  it('deletes a course and resolves without a value', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ message: 'Course deleted' }));

    await expect(deleteCourse('course-1', 'token-1')).resolves.toBeUndefined();
    expect(lastCall().init.method).toBe('DELETE');
  });
});

// ---------------------------------------------------------------------------
// Progress — the snake_case boundary
// ---------------------------------------------------------------------------

describe('progress service', () => {
  const rawProgress = {
    course_id: 'course-1',
    percent: 40,
    status: 'in_progress',
    lesson_count: 5,
    completed_count: 2,
    updated_at: '2026-01-01T00:00:00',
    completed_lesson_ids: ['l1', 'l2'],
  };

  it('maps every snake_case field to its camelCase counterpart', async () => {
    mockFetch.mockResolvedValue(jsonResponse(rawProgress));

    await expect(getCourseProgress('course-1')).resolves.toEqual({
      courseId: 'course-1',
      percent: 40,
      status: 'in_progress',
      lessonCount: 5,
      completedCount: 2,
      updatedAt: '2026-01-01T00:00:00',
      completedLessonIds: ['l1', 'l2'],
    });
  });

  it('defaults completedLessonIds to an empty array when the field is absent', async () => {
    // A missing array would otherwise become undefined and break `.map` in the UI.
    const { completed_lesson_ids, ...withoutIds } = rawProgress;
    mockFetch.mockResolvedValue(jsonResponse(withoutIds));

    const progress = await getCourseProgress('course-1');

    expect(progress.completedLessonIds).toEqual([]);
  });

  it('posts the completion payload in the shape the backend expects', async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({
        lesson_progress: { lesson_id: 'l1', status: 'completed', last_score: null },
        course_progress: rawProgress,
        new_badges: [],
      })
    );

    await markLessonComplete('l1', 'course-1');

    const { init } = lastCall();
    expect(JSON.parse(init.body as string)).toEqual({
      lesson_id: 'l1',
      course_id: 'course-1',
      status: 'completed',
    });
  });

  it('maps the completion result including newly earned badges', async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({
        lesson_progress: { lesson_id: 'l1', status: 'completed', last_score: 90 },
        course_progress: rawProgress,
        new_badges: [
          { id: 'b1', slug: 'first_lesson', name: 'First', description: 'd', icon: '📖' },
        ],
      })
    );

    const result = await markLessonComplete('l1', 'course-1');

    expect(result.lessonProgress).toEqual({
      lessonId: 'l1',
      status: 'completed',
      lastScore: 90,
    });
    expect(result.courseProgress.completedCount).toBe(2);
    expect(result.newBadges).toEqual([
      { id: 'b1', slug: 'first_lesson', name: 'First', description: 'd', icon: '📖' },
    ]);
  });

  it('tolerates a response with no new_badges field', async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({
        lesson_progress: { lesson_id: 'l1', status: 'completed', last_score: null },
        course_progress: rawProgress,
      })
    );

    await expect(markLessonComplete('l1', 'course-1')).resolves.toMatchObject({
      newBadges: [],
    });
  });

  it('requests the badges of the authenticated user', async () => {
    mockFetch.mockResolvedValue(jsonResponse([]));

    await getUserBadges('token-1');

    const { url, init } = lastCall();
    expect(url).toContain('/badges/user');
    expect(init.headers.Authorization).toBe('Bearer token-1');
  });
});

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

describe('documents service', () => {
  it('lists the documents of a course', async () => {
    mockFetch.mockResolvedValue(jsonResponse([]));

    await getDocuments('course-1');

    expect(lastCall().url).toContain('/courses/course-1/documents');
  });

  it('uploads a file as multipart form data, not JSON', async () => {
    // Serialising the upload as JSON would corrupt it; the browser must set the
    // multipart boundary itself.
    mockFetch.mockResolvedValue(jsonResponse({ id: 'doc-1' }, 201));
    const file = new File(['content'], 'lecture.pdf', { type: 'application/pdf' });

    await uploadDocument('course-1', file);

    const { init } = lastCall();
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined();
  });

  it('fetches the processing status of a document', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ status: 'processing' }));

    await getDocumentStatus('doc-1');

    expect(lastCall().url).toContain('/documents/doc-1/status');
  });

  it('deletes a document', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ message: 'deleted' }));

    await deleteDocument('doc-1');

    const { url, init } = lastCall();
    expect(url).toContain('/documents/doc-1');
    expect(init.method).toBe('DELETE');
  });
});
