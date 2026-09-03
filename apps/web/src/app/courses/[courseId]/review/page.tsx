'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { SplitPane } from '@/components/study/SplitPane';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { useToast } from '@/components/ui/Toast';
import { getCourse, type Course } from '@/lib/services/courses';
import { generateChapterTest } from '@/lib/services/chapterTests';
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
  type ChapterDraft,
  type LessonContent,
  type LessonDraft,
  type OutlineResponse,
} from '@/lib/services/courseBuilder';

const POLL_INTERVAL_MS = 3_000;
const POLL_TIMEOUT_MS = 20 * 60 * 1_000;

const STATUS_DOT: Record<string, string> = {
  published: '#1a7f3a',
  needs_review: '#a55a00',
  draft: '#7a7f9a',
};

const STATUS_LABEL: Record<string, string> = {
  published: 'Published',
  needs_review: 'Needs review',
  draft: 'Draft',
};

function StatusChip({ status }: { status?: string }) {
  const s = status || 'draft';
  const dot = STATUS_DOT[s] || '#7a7f9a';
  return (
    <span className="chip" style={{ color: dot, borderColor: dot, border: '1px solid' }}>
      <span
        className="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0"
        style={{ background: dot }}
      />
      {STATUS_LABEL[s] || s}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Run polling — reused for outline generation and content generation
// ---------------------------------------------------------------------------

function usePollRun(accessToken: string | undefined, onDone: () => void) {
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<{ status: string; stage?: string; error_message?: string } | null>(
    null
  );
  const startRef = useRef<number | null>(null);

  const start = useCallback((id: string) => {
    setRunId(id);
    setRun({ status: 'queued' });
    startRef.current = Date.now();
  }, []);

  useEffect(() => {
    if (!runId) return;
    if (run?.status === 'done' || run?.status === 'error') return;

    const id = setInterval(async () => {
      if (Date.now() - (startRef.current ?? Date.now()) >= POLL_TIMEOUT_MS) {
        clearInterval(id);
        return;
      }
      try {
        const updated = await getGenerationRun(runId, accessToken);
        setRun(updated);
        if (updated.status === 'done') {
          clearInterval(id);
          onDone();
        } else if (updated.status === 'error') {
          clearInterval(id);
        }
      } catch {
        /* transient — keep polling */
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, run?.status, accessToken]);

  return { runId, run, start };
}

export default function CourseReviewPage() {
  const params = useParams();
  const router = useRouter();
  const courseId = params.courseId as string;
  const { data: session } = useSession();
  const accessToken = session?.user?.accessToken;
  const { showToast } = useToast();

  const [course, setCourse] = useState<Course | null>(null);
  const [outline, setOutline] = useState<OutlineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedLessonId, setSelectedLessonId] = useState<string | null>(null);
  const [lesson, setLesson] = useState<LessonContent | null>(null);
  const [lessonLoading, setLessonLoading] = useState(false);
  const [editedContent, setEditedContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);

  const refreshOutline = useCallback(async () => {
    try {
      const data = await getOutline(courseId, accessToken);
      setOutline(data);
    } catch {
      showToast('Could not load outline.', 'err');
    }
  }, [courseId, accessToken, showToast]);

  const outlinePoll = usePollRun(accessToken, () => {
    showToast('Outline generated.', 'ok');
    refreshOutline();
  });
  const contentPoll = usePollRun(accessToken, () => {
    showToast('Content generation finished.', 'ok');
    refreshOutline();
    if (selectedLessonId) loadLesson(selectedLessonId);
  });

  useEffect(() => {
    async function load() {
      try {
        const [c, o] = await Promise.all([
          getCourse(courseId, accessToken),
          getOutline(courseId, accessToken),
        ]);
        setCourse(c);
        setOutline(o);
      } catch {
        showToast('Could not load course.', 'err');
      } finally {
        setLoading(false);
      }
    }
    if (courseId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, accessToken]);

  async function loadLesson(lessonId: string) {
    setSelectedLessonId(lessonId);
    setLessonLoading(true);
    try {
      const data = await getLessonContent(lessonId, accessToken);
      setLesson(data);
      setEditedContent(data.content);
    } catch {
      showToast('Could not load lesson.', 'err');
    } finally {
      setLessonLoading(false);
    }
  }

  async function handleGenerateOutline() {
    const hasHumanEdits = outline?.chapters.some(
      (chapter) =>
        chapter.is_human_modified || chapter.lessons.some((item) => item.is_human_modified)
    );
    if (hasHumanEdits && !window.confirm('Regenerate the full outline and replace manual edits?'))
      return;
    try {
      const { run_id } = await generateOutline(courseId, accessToken, !!hasHumanEdits);
      outlinePoll.start(run_id);
      showToast('Outline generation started…', 'ok');
    } catch {
      showToast('Could not start outline generation.', 'err');
    }
  }

  async function handleGenerateContent() {
    try {
      const { run_id } = await generateContent(courseId, undefined, accessToken);
      contentPoll.start(run_id);
      showToast('Content generation started…', 'ok');
    } catch {
      showToast('Could not start content generation. Generate an outline first.', 'err');
    }
  }

  async function handleRegenerateLesson() {
    if (!selectedLessonId) return;
    const selected = outline?.chapters
      .flatMap((chapter) => chapter.lessons)
      .find((item) => item.id === selectedLessonId);
    if (selected?.is_human_modified && !window.confirm('Replace the manual edits to this lesson?'))
      return;
    try {
      const { run_id } = await generateContent(
        courseId,
        [selectedLessonId],
        accessToken,
        !!selected?.is_human_modified
      );
      contentPoll.start(run_id);
      showToast('Regenerating lesson…', 'ok');
    } catch {
      showToast('Could not start regeneration.', 'err');
    }
  }

  async function handleSave() {
    if (!selectedLessonId || !lesson) return;
    setSaving(true);
    try {
      const updated = await patchLesson(selectedLessonId, { content: editedContent }, accessToken);
      setLesson(updated);
      setEditedContent(updated.content);
      showToast('Saved.', 'ok');
      refreshOutline();
    } catch {
      showToast('Could not save changes.', 'err');
    } finally {
      setSaving(false);
    }
  }

  async function handleApprove() {
    if (!selectedLessonId) return;
    try {
      await approveLesson(selectedLessonId, accessToken);
      showToast('Lesson approved.', 'ok');
      if (selectedLessonId) loadLesson(selectedLessonId);
      refreshOutline();
    } catch {
      showToast('Could not approve lesson.', 'err');
    }
  }

  async function handlePublishCourse() {
    setPublishing(true);
    try {
      const result = await publishCourse(courseId, accessToken);
      showToast(
        `Published ${result.published_chapters} chapter(s), ${result.published_lessons} lesson(s). ${result.skipped_chapters} pending review.`,
        result.skipped_chapters > 0 ? 'warn' : 'ok'
      );
      refreshOutline();
    } catch {
      showToast('Could not publish course.', 'err');
    } finally {
      setPublishing(false);
    }
  }

  if (loading) {
    return (
      <main className="page-fade max-w-8xl mx-auto px-6 py-6">
        <div className="animate-pulse space-y-5">
          <div className="b-hard rounded-lg h-16 bg-blue-dark/5" />
          <div className="h-96 b-hard rounded-lg bg-blue-dark/5" />
        </div>
      </main>
    );
  }

  if (!course) {
    return (
      <main className="max-w-8xl mx-auto px-6 py-6">
        <div
          className="b-hard rounded-lg p-6 text-center"
          style={{ borderColor: '#b3261e', color: '#b3261e' }}
        >
          <p className="text-sm">Course not found</p>
        </div>
      </main>
    );
  }

  const hasChapters = (outline?.chapters.length ?? 0) > 0;
  const isOutlineRunning = outlinePoll.run && !['done', 'error'].includes(outlinePoll.run.status);
  const isContentRunning = contentPoll.run && !['done', 'error'].includes(contentPoll.run.status);

  return (
    <main className="page-fade max-w-8xl mx-auto px-6 py-6 h-[calc(100vh-5rem)] flex flex-col">
      {/* Header */}
      <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 px-6 py-4 mb-4 flex items-center gap-4 flex-shrink-0">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 font-mono text-[11px] tracking-[0.12em] uppercase opacity-70 mb-1">
            <span>Academy</span>
            <span className="opacity-40">/</span>
            <span>{course.title}</span>
            <span className="opacity-40">/</span>
            <span className="font-semibold opacity-100">Review</span>
          </div>
          <h1 className="text-xl font-medium leading-tight truncate">
            {course.title} — Course Review
          </h1>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            className="btn-ghost"
            onClick={handleGenerateOutline}
            disabled={!!isOutlineRunning}
          >
            {isOutlineRunning
              ? `Generating outline… (${outlinePoll.run?.stage || 'init'})`
              : hasChapters
                ? '↺ Regenerate outline'
                : 'Generate outline'}
          </button>
          <button
            className="btn-ghost"
            onClick={handleGenerateContent}
            disabled={!hasChapters || !!isContentRunning}
          >
            {isContentRunning
              ? `Generating content… (${contentPoll.run?.stage || 'init'})`
              : 'Generate content'}
          </button>
          <button
            className="btn-primary"
            onClick={handlePublishCourse}
            disabled={!hasChapters || publishing}
          >
            {publishing ? 'Publishing…' : 'Publish course'}
          </button>
          <button className="btn-ghost" onClick={() => router.push(`/courses/${courseId}`)}>
            ← Back
          </button>
        </div>
      </div>

      {outlinePoll.run?.status === 'error' && (
        <div
          className="mb-4 b-thin rounded-lg px-4 py-3 font-mono text-[11px] flex-shrink-0"
          style={{ borderColor: '#b3261e', color: '#b3261e' }}
        >
          Outline generation failed: {outlinePoll.run.error_message}
        </div>
      )}
      {contentPoll.run?.status === 'error' && (
        <div
          className="mb-4 b-thin rounded-lg px-4 py-3 font-mono text-[11px] flex-shrink-0"
          style={{ borderColor: '#b3261e', color: '#b3261e' }}
        >
          Content generation failed: {contentPoll.run.error_message}
        </div>
      )}
      {outline?.is_stale && (
        <div
          className="mb-4 b-thin rounded-lg px-4 py-3 text-sm flex-shrink-0"
          style={{ borderColor: '#a55a00', color: '#a55a00' }}
        >
          <strong>Outline needs review.</strong> {outline.stale_reason}
        </div>
      )}
      {outline?.generation_run && (
        <div className="mb-3 font-mono text-[10px] opacity-60 flex-shrink-0">
          Last generation: {outline.generation_run.created_at} · prompt{' '}
          {outline.generation_run.prompt_version || 'unknown'} · {outline.generation_run.status}
        </div>
      )}

      {/* Split view */}
      <div className="flex-1 min-h-0 b-hard rounded-lg bg-white dark:bg-blue-dark/30 overflow-hidden">
        <ErrorBoundary>
          <SplitPane
            defaultLeftPercent={32}
            left={
              <OutlineTree
                outline={outline}
                selectedLessonId={selectedLessonId}
                onSelectLesson={loadLesson}
                accessToken={accessToken}
                showToast={showToast}
                courseId={courseId}
                onOutlineChange={setOutline}
              />
            }
            right={
              <LessonPanel
                lesson={lesson}
                loading={lessonLoading}
                editedContent={editedContent}
                onContentChange={setEditedContent}
                onSave={handleSave}
                onApprove={handleApprove}
                onRegenerate={handleRegenerateLesson}
                saving={saving}
                regenerating={!!isContentRunning}
              />
            }
          />
        </ErrorBoundary>
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Outline tree (left pane)
// ---------------------------------------------------------------------------

function OutlineTree({
  outline,
  selectedLessonId,
  onSelectLesson,
  accessToken,
  showToast,
  courseId,
  onOutlineChange,
}: {
  outline: OutlineResponse | null;
  selectedLessonId: string | null;
  onSelectLesson: (id: string) => void;
  accessToken?: string;
  showToast: (message: string, type?: 'ok' | 'err' | 'warn') => void;
  courseId: string;
  onOutlineChange: (outline: OutlineResponse) => void;
}) {
  const router = useRouter();
  const [generatingTestFor, setGeneratingTestFor] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  async function apply(action: Parameters<typeof editOutline>[1]) {
    setEditing(true);
    try {
      onOutlineChange(await editOutline(courseId, action, accessToken));
      showToast('Outline saved.', 'ok');
    } catch {
      showToast('Could not update outline.', 'err');
    } finally {
      setEditing(false);
    }
  }

  function moveId(ids: string[], index: number, delta: number) {
    const next = [...ids];
    [next[index], next[index + delta]] = [next[index + delta], next[index]];
    return next;
  }

  async function handleGenerateTest(chapterId: string) {
    setGeneratingTestFor(chapterId);
    try {
      const test = await generateChapterTest(chapterId, accessToken);
      showToast(`Chapter test built: ${test.questions.length} question(s).`, 'ok');
    } catch {
      showToast('Could not build chapter test — publish lessons with quizzes first.', 'err');
    } finally {
      setGeneratingTestFor(null);
    }
  }

  if (!outline || outline.chapters.length === 0) {
    return (
      <div className="p-8 text-center">
        <div className="mx-auto w-10 h-10 b-thin rounded-md mb-4 stripes" />
        <p className="font-medium mb-1">No outline yet</p>
        <p className="font-mono text-[11px] opacity-60 leading-relaxed max-w-xs mx-auto">
          Click &quot;Generate outline&quot; to draft chapters and lessons from the indexed
          documents.
        </p>
      </div>
    );
  }

  return (
    <div className="p-2">
      <button
        className="btn-ghost w-full mb-2"
        disabled={editing}
        onClick={() => {
          const title = window.prompt('Chapter title');
          if (title?.trim()) apply({ action: 'create_chapter', title: title.trim() });
        }}
      >
        + Add chapter
      </button>
      {outline.chapters.map((chapter: ChapterDraft, chapterIndex: number) => (
        <div key={chapter.id} className="mb-1">
          <div className="flex items-center gap-2 px-3 py-2 font-mono text-[11px] tracking-[0.08em] uppercase opacity-80">
            <StatusChip status={chapter.status} />
            {chapter.is_human_modified && <span title="Manually edited">✎</span>}
            {chapter.is_stale && <span title={chapter.stale_reason}>⚠</span>}
            <span className="truncate flex-1">{chapter.title}</span>
            <button
              disabled={editing}
              title="Rename chapter"
              onClick={() => {
                const title = window.prompt('Chapter title', chapter.title);
                if (title?.trim())
                  apply({ action: 'rename_chapter', chapter_id: chapter.id, title: title.trim() });
              }}
            >
              ✎
            </button>
            <button
              disabled={editing || chapterIndex === 0}
              title="Move chapter up"
              onClick={() =>
                apply({
                  action: 'reorder_chapters',
                  ordered_ids: moveId(
                    outline.chapters.map((c) => c.id),
                    chapterIndex,
                    -1
                  ),
                })
              }
            >
              ↑
            </button>
            <button
              disabled={editing || chapterIndex === outline.chapters.length - 1}
              title="Move chapter down"
              onClick={() =>
                apply({
                  action: 'reorder_chapters',
                  ordered_ids: moveId(
                    outline.chapters.map((c) => c.id),
                    chapterIndex,
                    1
                  ),
                })
              }
            >
              ↓
            </button>
            <button
              disabled={editing || chapterIndex === 0}
              title="Merge into previous chapter"
              onClick={() => {
                if (window.confirm(`Merge “${chapter.title}” into the previous chapter?`))
                  apply({
                    action: 'merge_chapters',
                    chapter_id: chapter.id,
                    target_chapter_id: outline.chapters[chapterIndex - 1].id,
                  });
              }}
            >
              Merge
            </button>
            <button
              disabled={editing}
              title="Delete chapter"
              onClick={() => {
                if (
                  window.confirm(
                    `Delete “${chapter.title}” and all its lessons and generated content? This cannot be undone.`
                  )
                )
                  apply({
                    action: 'delete_chapter',
                    chapter_id: chapter.id,
                    delete_lessons: true,
                  });
              }}
            >
              ×
            </button>
            {chapter.status === 'published' && (
              <>
                <button
                  onClick={() => handleGenerateTest(chapter.id)}
                  disabled={generatingTestFor === chapter.id}
                  className="font-mono text-[10px] tracking-[0.1em] normal-case opacity-60 hover:opacity-100 flex-shrink-0"
                  title="Build a chapter test from this chapter's lesson quizzes"
                >
                  {generatingTestFor === chapter.id ? '…' : '⚙ Test'}
                </button>
                <button
                  onClick={() => router.push(`/courses/${courseId}/chapters/${chapter.id}/test`)}
                  className="font-mono text-[10px] normal-case opacity-60 hover:opacity-100 flex-shrink-0"
                  title="Open the chapter test"
                >
                  →
                </button>
              </>
            )}
          </div>
          <div className="pl-3">
            {chapter.lessons.map((lsn: LessonDraft, lessonIndex: number) => (
              <div
                key={lsn.id}
                className={`w-full text-left flex items-center gap-1 px-3 py-2 rounded-md text-[13px] transition-colors ${
                  selectedLessonId === lsn.id
                    ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                    : 'hover:bg-blue-dark/5 dark:hover:bg-white/5'
                }`}
              >
                <span
                  className="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0"
                  style={{ background: STATUS_DOT[lsn.status || 'draft'] || '#7a7f9a' }}
                />
                {lsn.is_human_modified && <span title="Manually edited">✎</span>}
                {lsn.is_stale && <span title={lsn.stale_reason}>⚠</span>}
                <button
                  className="truncate flex-1 text-left"
                  onClick={() => onSelectLesson(lsn.id)}
                >
                  {lsn.title}
                </button>
                {lsn.is_stale && (
                  <button
                    disabled={editing}
                    title="Accept current lesson without regeneration"
                    onClick={() => apply({ action: 'accept_stale', lesson_id: lsn.id })}
                  >
                    Accept
                  </button>
                )}
                <button
                  disabled={editing}
                  title="Rename lesson"
                  onClick={() => {
                    const title = window.prompt('Lesson title', lsn.title);
                    if (title?.trim())
                      apply({ action: 'rename_lesson', lesson_id: lsn.id, title: title.trim() });
                  }}
                >
                  ✎
                </button>
                <button
                  disabled={editing || lessonIndex === 0}
                  title="Move lesson up"
                  onClick={() =>
                    apply({
                      action: 'reorder_lessons',
                      chapter_id: chapter.id,
                      ordered_ids: moveId(
                        chapter.lessons.map((l) => l.id),
                        lessonIndex,
                        -1
                      ),
                    })
                  }
                >
                  ↑
                </button>
                <button
                  disabled={editing || lessonIndex === chapter.lessons.length - 1}
                  title="Move lesson down"
                  onClick={() =>
                    apply({
                      action: 'reorder_lessons',
                      chapter_id: chapter.id,
                      ordered_ids: moveId(
                        chapter.lessons.map((l) => l.id),
                        lessonIndex,
                        1
                      ),
                    })
                  }
                >
                  ↓
                </button>
                <button
                  disabled={editing || outline.chapters.length < 2}
                  title="Move lesson to another chapter"
                  onClick={() => {
                    const target = window.prompt(
                      'Target chapter title',
                      outline.chapters.find((c) => c.id !== chapter.id)?.title
                    );
                    const targetChapter = outline.chapters.find(
                      (c) => c.id !== chapter.id && c.title === target
                    );
                    if (targetChapter)
                      apply({
                        action: 'move_lesson',
                        lesson_id: lsn.id,
                        target_chapter_id: targetChapter.id,
                      });
                  }}
                >
                  Move
                </button>
                <button
                  disabled={editing || lessonIndex === 0}
                  title="Split chapter before this lesson"
                  onClick={() => {
                    const title = window.prompt('New chapter title', `${chapter.title} (split)`);
                    if (title?.trim())
                      apply({
                        action: 'split_chapter',
                        chapter_id: chapter.id,
                        title: title.trim(),
                        lesson_ids: chapter.lessons.slice(lessonIndex).map((l) => l.id),
                      });
                  }}
                >
                  Split
                </button>
                <button
                  disabled={editing}
                  title="Delete lesson"
                  onClick={() => {
                    if (
                      window.confirm(
                        `Delete “${lsn.title}”, including its content and quiz? This cannot be undone.`
                      )
                    )
                      apply({ action: 'delete_lesson', lesson_id: lsn.id });
                  }}
                >
                  ×
                </button>
              </div>
            ))}
            <button
              className="w-full text-left px-3 py-2 font-mono text-[10px] opacity-60 hover:opacity-100"
              disabled={editing}
              onClick={() => {
                const title = window.prompt('Lesson title');
                if (title?.trim())
                  apply({ action: 'create_lesson', chapter_id: chapter.id, title: title.trim() });
              }}
            >
              + Add lesson
            </button>
          </div>
          {chapter.lessons.some((item) => item.sources.length > 0) && (
            <div className="px-6 pb-2 font-mono text-[9px] opacity-55">
              {chapter.lessons.flatMap((item) =>
                item.sources.map((source) => (
                  <a
                    key={`${item.id}-${source.chunk_id}`}
                    className="mr-2 underline"
                    href={`/courses/${courseId}/documents/${source.document_id}/preview?chunk=${source.chunk_id}`}
                  >
                    {item.title}: {source.chunk_id.slice(0, 8)}
                  </a>
                ))
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lesson panel (right pane)
// ---------------------------------------------------------------------------

function LessonPanel({
  lesson,
  loading,
  editedContent,
  onContentChange,
  onSave,
  onApprove,
  onRegenerate,
  saving,
  regenerating,
}: {
  lesson: LessonContent | null;
  loading: boolean;
  editedContent: string;
  onContentChange: (v: string) => void;
  onSave: () => void;
  onApprove: () => void;
  onRegenerate: () => void;
  saving: boolean;
  regenerating: boolean;
}) {
  if (loading) {
    return (
      <div className="p-6 space-y-3">
        <div className="animate-pulse h-6 w-1/2 bg-blue-dark/5 rounded" />
        <div className="animate-pulse h-40 bg-blue-dark/5 rounded" />
      </div>
    );
  }

  if (!lesson) {
    return (
      <div className="p-10 text-center font-mono text-[11px] opacity-50">
        Select a lesson from the outline to review it.
      </div>
    );
  }

  const isDirty = editedContent !== lesson.content;
  const canApprove = lesson.status !== 'published' && !!lesson.content.trim();

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-4 b-thin-b flex items-start gap-3 flex-shrink-0">
        <div className="flex-1 min-w-0">
          <h3 className="font-medium leading-tight truncate">{lesson.title}</h3>
          {lesson.description && (
            <p className="font-mono text-[11px] opacity-70 mt-1">{lesson.description}</p>
          )}
        </div>
        <StatusChip status={lesson.status} />
      </div>

      {lesson.review_issues.length > 0 && (
        <div
          className="mx-5 mt-4 b-thin rounded-md px-4 py-3 flex-shrink-0"
          style={{ borderColor: '#a55a00', color: '#a55a00' }}
        >
          <div className="font-mono text-[10px] tracking-[0.18em] uppercase mb-1.5">
            Groundedness issues
          </div>
          <ul className="text-[12px] leading-relaxed list-disc list-inside space-y-0.5">
            {lesson.review_issues.map((issue, i) => (
              <li key={i}>{issue}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="p-5 flex-1 min-h-0 flex flex-col">
        <div className="flex items-end justify-between b-thin-b pb-1.5 mb-3 flex-shrink-0">
          <span className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">
            Content
          </span>
          {lesson.source_refs.length > 0 && (
            <span className="font-mono text-[10px] opacity-50">
              {lesson.source_refs.length} source{lesson.source_refs.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <textarea
          value={editedContent}
          onChange={(e) => onContentChange(e.target.value)}
          className="flex-1 min-h-[240px] w-full resize-none rounded-md b-thin px-3 py-2 text-[13px] font-mono leading-relaxed bg-transparent outline-none focus:ring-1 focus:ring-blue-dark"
          placeholder="No content generated yet."
        />
      </div>

      <div className="px-5 py-4 b-thin-t flex items-center gap-2 flex-shrink-0">
        <button
          className="btn-primary"
          onClick={onSave}
          disabled={!isDirty || saving || regenerating}
          title={
            regenerating
              ? 'A regeneration is in progress — saving now would be overwritten when it finishes'
              : undefined
          }
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button className="btn-ghost" onClick={onApprove} disabled={!canApprove || regenerating}>
          Approve
        </button>
        <button className="btn-ghost" onClick={onRegenerate} disabled={regenerating}>
          {regenerating ? 'Regenerating…' : '↺ Regenerate'}
        </button>
        {lesson.quiz && (
          <span className="ml-auto font-mono text-[10px] opacity-60">
            Quiz: {lesson.quiz.questions.length} question
            {lesson.quiz.questions.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>
    </div>
  );
}
