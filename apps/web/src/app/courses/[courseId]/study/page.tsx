'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { getCourse, type Course } from '@/lib/services/courses';
import { SplitPane } from '@/components/study/SplitPane';
import { SourcePane } from '@/components/study/SourcePane';
import { OutputPane } from '@/components/study/OutputPane';

export default function StudyPage() {
  const params = useParams();
  const courseId = params.courseId as string;
  const { data: session } = useSession();
  const accessToken = (session?.user as any)?.accessToken;

  const [course, setCourse] = useState<Course | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await getCourse(courseId, accessToken);
        setCourse(data);
      } catch {
        // Course info is optional for the layout
      } finally {
        setLoading(false);
      }
    }
    if (courseId) load();
  }, [courseId, accessToken]);

  if (loading) {
    return (
      <div className="h-[calc(100vh-7rem)] flex items-center justify-center">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-orange-600" />
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-7rem)]">
      <SplitPane
        left={<SourcePane courseTitle={course?.title} />}
        right={<OutputPane />}
        defaultLeftPercent={50}
      />
    </div>
  );
}
