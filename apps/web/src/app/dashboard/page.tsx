'use client';

import { useEffect, useState } from 'react';
import { signOut, useSession } from 'next-auth/react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { getCourses, MVP_COURSES_LIMIT, type Course } from '@/lib/services/courses';

export default function DashboardPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [courses, setCourses] = useState<Course[]>([]);
  const [coursesLoading, setCoursesLoading] = useState(true);

  useEffect(() => {
    if (status !== 'authenticated') return;

    async function fetchCourses() {
      try {
        const data = await getCourses(0, MVP_COURSES_LIMIT, session?.user?.accessToken);
        setCourses(data);
      } catch {
        // Non-critical — dashboard still usable without course count
      } finally {
        setCoursesLoading(false);
      }
    }

    fetchCourses();
  }, [status, session]);

  if (status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-orange-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  if (status === 'unauthenticated') {
    router.push('/login');
    return null;
  }

  const handleSignOut = async () => {
    await signOut({ callbackUrl: '/login' });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <h1 className="text-2xl font-bold text-gray-900">BitPolito Academy</h1>
          <div className="flex items-center space-x-4">
            <span className="text-sm text-gray-600">{session?.user?.email}</span>
            <button
              onClick={handleSignOut}
              className="px-4 py-2 text-sm font-medium text-white bg-orange-600 rounded-md hover:bg-orange-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-orange-500"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Welcome, {session?.user?.displayName || session?.user?.email}!
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-6">
            {/* User Info Card */}
            <div className="bg-gray-50 rounded-lg p-4">
              <h3 className="text-lg font-medium text-gray-900 mb-2">Your Profile</h3>
              <dl className="space-y-2">
                <div>
                  <dt className="text-sm text-gray-500">Email</dt>
                  <dd className="text-sm font-medium text-gray-900">{session?.user?.email}</dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Display Name</dt>
                  <dd className="text-sm font-medium text-gray-900">
                    {session?.user?.displayName || 'Not set'}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Role</dt>
                  <dd className="text-sm font-medium text-gray-900 capitalize">
                    {session?.user?.role || 'Student'}
                  </dd>
                </div>
              </dl>
            </div>

            {/* Quick Stats Card */}
            <div className="bg-gray-50 rounded-lg p-4">
              <h3 className="text-lg font-medium text-gray-900 mb-2">Your Progress</h3>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">Available Courses</span>
                  <span className="text-lg font-semibold text-orange-600">
                    {coursesLoading ? (
                      <span className="inline-block h-5 w-6 bg-gray-200 rounded animate-pulse" />
                    ) : (
                      courses.length
                    )}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">Courses Completed</span>
                  <span className="text-lg font-semibold text-green-600">–</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">Certificates Earned</span>
                  <span className="text-lg font-semibold text-blue-600">–</span>
                </div>
              </div>
            </div>

            {/* Quick Actions Card */}
            <div className="bg-gray-50 rounded-lg p-4">
              <h3 className="text-lg font-medium text-gray-900 mb-2">Quick Actions</h3>
              <div className="space-y-2">
                <Link
                  href="/courses"
                  className="block w-full px-4 py-2 text-center text-sm font-medium text-white bg-orange-600 rounded-md hover:bg-orange-700"
                >
                  Browse Courses
                </Link>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
