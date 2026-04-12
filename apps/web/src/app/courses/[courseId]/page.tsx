'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { getCourse, getCourseLessons, type Course, type Lesson } from '@/lib/services/courses';
import { DocumentList } from '@/components/courses/DocumentList';
import { DocumentUpload } from '@/components/documents/DocumentUpload';

export default function CourseWorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const courseId = params.courseId as string;
  const { data: session } = useSession();
  const accessToken = (session?.user as any)?.accessToken;

  const [course, setCourse] = useState<Course | null>(null);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [docRefreshKey, setDocRefreshKey] = useState(0);

  const refreshDocuments = useCallback(() => {
    setDocRefreshKey((k) => k + 1);
  }, []);

  function handleViewPreview(documentId: string) {
    router.push(`/courses/${courseId}/documents/${documentId}/preview`);
  }

  useEffect(() => {
    async function load() {
      try {
        const [courseData, lessonsData] = await Promise.all([
          getCourse(courseId, accessToken),
          getCourseLessons(courseId, accessToken),
        ]);
        setCourse(courseData);
        setLessons(lessonsData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load course');
      } finally {
        setLoading(false);
      }
    }

    if (courseId) load();
  }, [courseId, accessToken]);

  if (loading) {
    return (
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-1/3 bg-gray-200 rounded" />
          <div className="h-4 w-2/3 bg-gray-100 rounded" />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 bg-white rounded-lg shadow p-6 space-y-4">
              <div className="h-5 w-1/4 bg-gray-200 rounded" />
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-12 bg-gray-50 rounded" />
              ))}
            </div>
            <div className="bg-white rounded-lg shadow p-6 space-y-4">
              <div className="h-5 w-1/3 bg-gray-200 rounded" />
              <div className="h-24 bg-gray-50 rounded" />
            </div>
          </div>
        </div>
      </main>
    );
  }

  if (error || !course) {
    return (
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center">
          <p className="text-sm text-red-700">{error || 'Course not found'}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-3 text-sm font-medium text-red-700 hover:text-red-800 underline"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{course.title}</h1>
        {course.description && (
          <p className="mt-1 text-gray-600">{course.description}</p>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Lessons panel */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-lg shadow">
            <div className="px-6 py-4 border-b border-gray-100">
              <h2 className="text-lg font-semibold text-gray-900">Lessons</h2>
            </div>
            <div className="p-6">
              {lessons.length === 0 ? (
                <div className="text-center py-8">
                  <svg className="mx-auto h-10 w-10 text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.26 10.147a60.438 60.438 0 00-.491 6.347A48.62 48.62 0 0112 20.904a48.62 48.62 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.636 50.636 0 00-2.658-.813A59.906 59.906 0 0112 3.493a59.903 59.903 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0112 13.489a50.702 50.702 0 017.74-3.342" />
                  </svg>
                  <p className="mt-2 text-sm text-gray-500">No lessons available yet</p>
                </div>
              ) : (
                <ul className="divide-y divide-gray-100">
                  {lessons.map((lesson, index) => (
                    <li key={lesson.id} className="flex items-center gap-4 py-3">
                      <span className="flex-shrink-0 flex items-center justify-center h-8 w-8 rounded-full bg-orange-50 text-orange-600 text-sm font-semibold">
                        {index + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900">{lesson.title}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>

        {/* Documents sidebar */}
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow">
            <div className="px-6 py-4 border-b border-gray-100">
              <h2 className="text-lg font-semibold text-gray-900">Documents</h2>
            </div>
            <div className="p-6">
              <DocumentUpload
                courseId={courseId}
                accessToken={accessToken}
                onUploadComplete={refreshDocuments}
              />
              <div className="mt-4">
                <DocumentList
                  courseId={courseId}
                  accessToken={accessToken}
                  refreshKey={docRefreshKey}
                  onViewPreview={handleViewPreview}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
