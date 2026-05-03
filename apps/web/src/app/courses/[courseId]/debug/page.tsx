'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import {
  getPipelineHealth,
  testRetrieval,
  getEvidencePack,
  type PipelineHealth,
} from '@/lib/services/debug';
import type { EvidencePack } from '@/lib/api/types';

export default function DebugPage() {
  const params = useParams();
  const router = useRouter();
  const courseId = params.courseId as string;
  const { data: session } = useSession();
  const accessToken = session?.user?.accessToken;

  const [health, setHealth] = useState<PipelineHealth | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  const [query, setQuery] = useState('');
  const [action, setAction] = useState('explain');
  const [retrievalResult, setRetrievalResult] = useState<Record<string, unknown> | null>(null);
  const [evidencePack, setEvidencePack] = useState<EvidencePack | null>(null);
  const [querying, setQuerying] = useState(false);

  const loadHealth = useCallback(async () => {
    try {
      const h = await getPipelineHealth(accessToken);
      setHealth(h);
    } catch (err) {
      setHealthError(err instanceof Error ? err.message : 'Failed to load health');
    }
  }, [accessToken]);

  useEffect(() => {
    loadHealth();
  }, [loadHealth]);

  async function handleTestRetrieval() {
    if (!query.trim()) return;
    setQuerying(true);
    try {
      const result = await testRetrieval(courseId, query, 5, accessToken);
      setRetrievalResult(result as unknown as Record<string, unknown>);
    } catch (err) {
      setRetrievalResult({ error: err instanceof Error ? err.message : 'Failed' });
    } finally {
      setQuerying(false);
    }
  }

  async function handleGetEvidence() {
    if (!query.trim()) return;
    setQuerying(true);
    try {
      const pack = await getEvidencePack(courseId, query, action, accessToken);
      setEvidencePack(pack);
    } catch (err) {
      setEvidencePack(null);
    } finally {
      setQuerying(false);
    }
  }

  return (
    <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div className="flex items-center gap-3">
        <button
          onClick={() => router.push(`/courses/${courseId}`)}
          className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
          </svg>
          Back
        </button>
        <h1 className="text-xl font-bold text-gray-900">Debug Inspector</h1>
        <span className="px-2 py-0.5 text-xs bg-yellow-100 text-yellow-800 rounded font-medium">DEV ONLY</span>
      </div>

      {/* Pipeline health */}
      <section className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900">Pipeline Health</h2>
          <button onClick={loadHealth} className="text-xs text-gray-500 hover:text-gray-700 underline">Refresh</button>
        </div>
        <div className="p-6">
          {healthError && <p className="text-sm text-red-600">{healthError}</p>}
          {health && (
            <div className="space-y-3 text-sm">
              <div className="flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${health.chroma_status === 'ok' ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="font-medium">ChromaDB:</span>
                <span className="text-gray-600">{health.chroma_status} · {health.chroma_db_path}</span>
              </div>
              <div>
                <span className="font-medium">Collections:</span>
                <div className="mt-1 flex flex-wrap gap-2">
                  {Object.entries(health.collection_sizes).map(([name, count]) => (
                    <span key={name} className="px-2 py-0.5 bg-gray-100 rounded text-xs">
                      {name}: {count} chunks
                    </span>
                  ))}
                  {Object.keys(health.collection_sizes).length === 0 && (
                    <span className="text-gray-400 text-xs">No collections</span>
                  )}
                </div>
              </div>
              <div className="flex gap-4 text-xs text-gray-500">
                <span>Uploads: {health.uploads_dir_size_mb} MB</span>
                <span>Python: {health.python_version.split(' ')[0]}</span>
              </div>
            </div>
          )}
          {!health && !healthError && <p className="text-sm text-gray-400 animate-pulse">Loading…</p>}
        </div>
      </section>

      {/* Retrieval test */}
      <section className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-900">Retrieval Test</h2>
        </div>
        <div className="p-6 space-y-4">
          <div className="flex gap-3">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter a query…"
              className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
            />
            <select
              value={action}
              onChange={(e) => setAction(e.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none"
            >
              {['explain', 'summarize', 'retrieve', 'open_questions', 'quiz', 'oral'].map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleTestRetrieval}
              disabled={querying || !query.trim()}
              className="px-4 py-2 text-sm font-medium text-white bg-gray-700 rounded-md hover:bg-gray-800 disabled:opacity-40"
            >
              Raw Retrieval
            </button>
            <button
              onClick={handleGetEvidence}
              disabled={querying || !query.trim()}
              className="px-4 py-2 text-sm font-medium text-white bg-orange-600 rounded-md hover:bg-orange-700 disabled:opacity-40"
            >
              Evidence Pack
            </button>
          </div>

          {retrievalResult && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-2">Raw candidates ({(retrievalResult as any).total ?? 0}):</p>
              <pre className="bg-gray-50 rounded-md p-4 text-xs text-gray-700 overflow-auto max-h-80">
                {JSON.stringify(retrievalResult, null, 2)}
              </pre>
            </div>
          )}

          {evidencePack && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-2">
                Evidence pack · {evidencePack.chunks.length} chunks (from {evidencePack.total_candidates} candidates):
              </p>
              <div className="space-y-2">
                {evidencePack.chunks.map((chunk, i) => (
                  <div key={chunk.chunk_id} className="rounded-md border border-gray-200 p-3 text-xs">
                    <div className="flex justify-between mb-1">
                      <span className="font-medium text-gray-700">[{i + 1}] {chunk.anchor.doc_name}</span>
                      <span className="text-orange-600 font-medium">{Math.round(chunk.score * 100)}%</span>
                    </div>
                    {chunk.anchor.section && <p className="text-gray-500 mb-1">{chunk.anchor.section}</p>}
                    <p className="text-gray-700">{chunk.text.slice(0, 300)}{chunk.text.length > 300 ? '…' : ''}</p>
                    <p className="mt-1 text-gray-400">{chunk.chunk_id} · {chunk.anchor.chunk_type}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
