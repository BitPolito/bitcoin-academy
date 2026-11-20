'use client';

import { useCallback } from 'react';
import { useParams } from 'next/navigation';
import { QuizPage } from '@/components/assessment/QuizPage';
import { getChapterTest } from '@/lib/services/chapterTests';

export default function ChapterTestPage() {
  const { courseId, chapterId } = useParams<{ courseId: string; chapterId: string }>();
  const loadQuiz = useCallback((token: string) => getChapterTest(chapterId, token), [chapterId]);
  return <QuizPage courseId={courseId} kind="Chapter Test" loadQuiz={loadQuiz} />;
}
