'use client';

interface SourcePaneProps {
  courseTitle?: string;
}

export function SourcePane({ courseTitle }: SourcePaneProps) {
  return (
    <div className="h-full flex flex-col">
      <div className="flex-shrink-0 px-6 py-4 border-b border-gray-200 bg-white">
        <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">
          Source Material
        </h2>
        {courseTitle && (
          <p className="mt-0.5 text-xs text-gray-500">{courseTitle}</p>
        )}
      </div>

      <div className="flex-1 flex items-center justify-center p-8 bg-gray-50">
        <div className="text-center max-w-sm">
          <svg
            className="mx-auto h-12 w-12 text-gray-300"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
            />
          </svg>
          <h3 className="mt-4 text-sm font-medium text-gray-900">
            No document selected
          </h3>
          <p className="mt-1 text-sm text-gray-500">
            Select a document from the course workspace to view its contents here.
            Citations and highlights will be synced with the explanation panel.
          </p>
        </div>
      </div>
    </div>
  );
}
