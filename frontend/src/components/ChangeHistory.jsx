import { useState, useEffect, useRef } from 'react';
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued';
import { api } from '../api/client';

function DiffModal({ diffData, entry, onClose }) {
  const summarize = (changes) => {
    return changes.map((c) => {
      const target = c.target?.text || '';
      const replacement = c.replacement || '';
      const tShort = target.length > 40 ? target.slice(0, 40) + '...' : target;
      const rShort = replacement.length > 40 ? replacement.slice(0, 40) + '...' : replacement;
      if (!replacement) return `Removed "${tShort}"`;
      if (!target) return `Inserted "${rShort}"`;
      return `"${tShort}" → "${rShort}"`;
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-white dark:bg-gray-900 rounded-lg shadow-2xl w-[92vw] max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700 shrink-0">
          <div>
            <h3 className="text-sm font-semibold dark:text-white">
              Change from {new Date(entry.created_at).toLocaleString()}
            </h3>
            <div className="text-xs text-gray-400 mt-0.5 font-mono">
              {summarize(entry.changes).join(' | ')}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-lg px-2"
          >
            &times;
          </button>
        </div>

        {/* Diff content */}
        <div className="flex-1 overflow-auto" style={{ minWidth: 0 }}>
          <ReactDiffViewer
            oldValue={diffData.before}
            newValue={diffData.after}
            splitView={false}
            hideLineNumbers
            compareMethod={DiffMethod.CHARS}
            styles={{
              diffContainer: { width: '100%', tableLayout: 'fixed' },
              contentText: { fontSize: '13px', lineHeight: '1.6', whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
              content: { width: '100%' },
              gutter: { width: '30px', minWidth: '30px', maxWidth: '30px' },
              marker: { width: '20px', minWidth: '20px', maxWidth: '20px' },
              wordDiff: { padding: '1px 0' },
            }}
          />
        </div>
      </div>
    </div>
  );
}

export default function ChangeHistory({ documentId, refreshKey }) {
  const [history, setHistory] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [modalEntry, setModalEntry] = useState(null);
  const [diffData, setDiffData] = useState(null);
  const [loadingDiff, setLoadingDiff] = useState(false);
  const cacheRef = useRef(new Map()); // documentId -> { history, total }

  useEffect(() => {
    if (!documentId) {
      setHistory([]);
      setModalEntry(null);
      setDiffData(null);
      return;
    }

    // Use cache if available and not a forced refresh
    const cacheKey = `${documentId}:${refreshKey}`;
    const cached = cacheRef.current.get(cacheKey);
    if (cached) {
      setHistory(cached.history);
      setTotal(cached.total);
      setModalEntry(null);
      setDiffData(null);
      return;
    }

    setLoading(true);
    setModalEntry(null);
    setDiffData(null);
    api.getHistory(documentId)
      .then((data) => {
        setHistory(data.history);
        setTotal(data.total);
        cacheRef.current.set(cacheKey, data);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [documentId, refreshKey]);

  const handleClickEntry = async (entry) => {
    setModalEntry(entry);
    setLoadingDiff(true);
    setDiffData(null);
    try {
      const detail = await api.getHistoryEntry(documentId, entry.id);
      setDiffData({ before: detail.previous_content, after: detail.resulting_content });
    } catch (err) {
      console.error(err);
      setModalEntry(null);
    } finally {
      setLoadingDiff(false);
    }
  };

  const closeModal = () => {
    setModalEntry(null);
    setDiffData(null);
  };

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') closeModal(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  if (!documentId) return null;

  const summarize = (changes) => {
    return changes.map((c) => {
      const target = c.target?.text || '';
      const replacement = c.replacement || '';
      const tShort = target.length > 25 ? target.slice(0, 25) + '...' : target;
      const rShort = replacement.length > 25 ? replacement.slice(0, 25) + '...' : replacement;
      if (!replacement) return `Removed "${tShort}"`;
      if (!target) return `Inserted "${rShort}"`;
      return `"${tShort}" → "${rShort}"`;
    });
  };

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700 shrink-0">
        <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          Change History ({total})
        </h3>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && <div className="p-3 text-xs text-gray-400">Loading...</div>}
        {!loading && history.length === 0 && (
          <div className="p-3 text-xs text-gray-400 text-center">No changes yet</div>
        )}
        {history.map((entry) => (
          <button
            key={entry.id}
            onClick={() => handleClickEntry(entry)}
            className="w-full text-left px-3 py-2 border-b border-gray-100 dark:border-gray-700 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors cursor-pointer"
          >
            <div className="text-xs text-gray-400 mb-0.5">
              {new Date(entry.created_at).toLocaleString()}
            </div>
            {summarize(entry.changes).map((s, i) => (
              <div key={i} className="text-xs text-gray-600 dark:text-gray-300 font-mono truncate">{s}</div>
            ))}
          </button>
        ))}
      </div>

      {/* Loading overlay */}
      {loadingDiff && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="bg-white dark:bg-gray-800 rounded-lg px-6 py-4 shadow-lg text-sm text-gray-600 dark:text-gray-300">
            Loading diff...
          </div>
        </div>
      )}

      {/* Diff modal */}
      {modalEntry && diffData && (
        <DiffModal diffData={diffData} entry={modalEntry} onClose={closeModal} />
      )}
    </div>
  );
}
