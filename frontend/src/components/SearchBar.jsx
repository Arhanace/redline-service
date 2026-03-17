import { useState } from 'react';
import { api } from '../api/client';

export default function SearchBar({ onSelectDocument }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await api.searchDocuments(query.trim());
      setResults(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const closeResults = () => {
    setResults(null);
    setQuery('');
  };

  return (
    <div className="border-b border-gray-200 dark:border-gray-700 relative">
      <form onSubmit={handleSearch} className="p-3">
        <div className="flex gap-1">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search documents..."
            className="flex-1 text-sm border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 bg-white dark:bg-gray-800 dark:text-white"
          />
          <button
            type="submit"
            disabled={loading}
            className="text-sm bg-gray-600 hover:bg-gray-700 text-white rounded px-3 py-1.5 disabled:opacity-50"
          >
            {loading ? '...' : 'Search'}
          </button>
        </div>
      </form>
      {results && (
        <div className="absolute left-0 right-0 top-full z-20 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg rounded-b-lg max-h-80 flex flex-col">
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-gray-100 dark:border-gray-700 shrink-0">
            <span className="text-xs text-gray-400">{results.total} result{results.total !== 1 ? 's' : ''}</span>
            <button
              onClick={closeResults}
              className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 px-1"
            >
              Close
            </button>
          </div>
          <div className="overflow-y-auto flex-1 p-2">
            {results.results.map((r) => (
              <button
                key={r.document_id}
                onClick={() => {
                  onSelectDocument(r.document_id);
                  closeResults();
                }}
                className="w-full text-left p-2 rounded hover:bg-gray-50 dark:hover:bg-gray-700 mb-1 border border-gray-100 dark:border-gray-700"
              >
                <div className="text-sm font-medium dark:text-white">{r.title}</div>
                <div
                  className="text-xs text-gray-500 mt-1 line-clamp-4"
                  dangerouslySetInnerHTML={{ __html: r.snippets.join(' ... ') }}
                />
              </button>
            ))}
            {results.results.length === 0 && (
              <div className="text-xs text-gray-400 p-2">No matches found</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
