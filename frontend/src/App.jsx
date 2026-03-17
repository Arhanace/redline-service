import { useState, useEffect, useCallback, useRef } from 'react';
import DocumentList from './components/DocumentList';
import SearchBar from './components/SearchBar';
import DiffEditor from './components/DiffEditor';
import ChangeHistory from './components/ChangeHistory';
import { api } from './api/client';

export default function App() {
  const [documents, setDocuments] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);
  const docCacheRef = useRef(new Map());
  const abortRef = useRef(null);

  const loadDocuments = useCallback(async () => {
    try {
      const data = await api.listDocuments();
      setDocuments(data.documents);
    } catch (err) {
      console.error('Failed to load documents:', err);
    }
  }, []);

  useEffect(() => { loadDocuments(); }, [loadDocuments]);

  useEffect(() => {
    if (abortRef.current) abortRef.current.abort();
    if (!selectedId) {
      setSelectedDoc(null);
      setLoadingDoc(false);
      return;
    }

    const cached = docCacheRef.current.get(selectedId);
    if (cached) {
      setSelectedDoc(cached);
      setLoadingDoc(false);
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    setLoadingDoc(true);

    api.getDocument(selectedId, controller.signal)
      .then((doc) => {
        if (controller.signal.aborted) return;
        docCacheRef.current.set(selectedId, doc);
        setSelectedDoc(doc);
        setLoadingDoc(false);
      })
      .catch((err) => {
        if (err.name === 'AbortError') return;
        console.error(err);
        setLoadingDoc(false);
      });

    return () => controller.abort();
  }, [selectedId]);

  const handleUpdate = async (patchResult) => {
    // PATCH returns metadata only (no content), re-fetch full doc
    try {
      const doc = await api.getDocument(patchResult.id);
      docCacheRef.current.set(doc.id, doc);
      setSelectedDoc(doc);
    } catch (err) {
      console.error(err);
    }
    setHistoryKey((k) => k + 1);
    loadDocuments();
  };

  const handleDelete = (deletedId) => {
    docCacheRef.current.delete(deletedId);
    setSelectedId(null);
    setSelectedDoc(null);
    setDocuments((docs) => docs.filter((d) => d.id !== deletedId));
  };

  return (
    <div className="h-screen flex bg-white dark:bg-gray-900">
      <div className="w-72 border-r border-gray-200 dark:border-gray-700 flex flex-col bg-gray-50 dark:bg-gray-800 shrink-0">
        <SearchBar onSelectDocument={setSelectedId} />
        <DocumentList
          documents={documents}
          selected={selectedId}
          onSelect={setSelectedId}
          onRefresh={loadDocuments}
        />
      </div>
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 min-h-0">
          <DiffEditor
            document={selectedDoc}
            loading={loadingDoc}
            onUpdate={handleUpdate}
            onDelete={handleDelete}
          />
        </div>
        <div className={`h-48 border-t border-gray-200 dark:border-gray-700 shrink-0 ${selectedId ? '' : 'hidden'}`}>
          <ChangeHistory documentId={selectedId} refreshKey={historyKey} />
        </div>
      </div>
    </div>
  );
}
