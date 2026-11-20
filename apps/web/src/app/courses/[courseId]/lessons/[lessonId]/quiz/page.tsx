'use client';

import { useCallback } from 'react';
import { useParams } from 'next/navigation';
import { QuizPage } from '@/components/assessment/QuizPage';
import { getLessonContent } from '@/lib/services/courseBuilder';

export default function LessonQuizPage() {
  const { courseId, lessonId } = useParams<{ courseId: string; lessonId: string }>();
  const loadQuiz = useCallback(
    async (token: string) => {
      const lesson = await getLessonContent(lessonId, token);
      if (!lesson.quiz || !lesson.quiz.questions.length) throw new Error('No saved lesson quiz');
      return lesson.quiz;
    },
    [lessonId]
  );
  return <QuizPage courseId={courseId} kind="Lesson Quiz" loadQuiz={loadQuiz} />;
}
