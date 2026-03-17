import { useState, useRef } from 'react';
import { api } from '../api/client';

export default function DocumentList({ documents, selected, onSelect, onRefresh }) {
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState('');
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    await api.createDocument({ title: title.trim(), content: '' });
    setTitle('');
    setShowCreate(false);
    onRefresh();
  };

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const doc = await api.uploadDocument(file);
      onRefresh();
      onSelect(doc.id);
    } catch (err) {
      alert(err.message);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Documents</h2>
        <div className="flex gap-1">
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="flex-1 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded px-3 py-1.5 transition-colors"
          >
            + New
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex-1 text-sm bg-gray-600 hover:bg-gray-700 disabled:bg-gray-400 text-white rounded px-3 py-1.5 transition-colors"
          >
            {uploading ? 'Uploading...' : 'Upload'}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={handleUpload}
            className="hidden"
          />
        </div>
        {showCreate && (
          <form onSubmit={handleCreate} className="mt-2 flex gap-1">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Title..."
              className="flex-1 text-sm border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 dark:text-white"
              autoFocus
            />
            <button type="submit" className="text-sm bg-green-600 text-white rounded px-2 py-1">Go</button>
          </form>
        )}
      </div>
      <div className="flex-1 overflow-y-auto">
        {documents.map((doc) => {
          const size = doc.content_length || 0;
          const sizeStr = size < 1024 ? `${size} B`
            : size < 1024 * 1024 ? `${(size / 1024).toFixed(1)} KB`
            : `${(size / (1024 * 1024)).toFixed(1)} MB`;
          return (
            <button
              key={doc.id}
              onClick={() => onSelect(doc.id)}
              className={`w-full text-left px-3 py-2.5 border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors ${
                selected === doc.id ? 'bg-blue-50 dark:bg-blue-900/30 border-l-2 border-l-blue-600' : ''
              }`}
            >
              <div className="text-sm font-medium truncate dark:text-white">{doc.title}</div>
              <div className="text-xs text-gray-400 mt-0.5">v{doc.version} &middot; {new Date(doc.updated_at).toLocaleDateString()} &middot; {sizeStr}</div>
            </button>
          );
        })}
        {documents.length === 0 && (
          <div className="p-4 text-sm text-gray-400 text-center">No documents yet</div>
        )}
      </div>
    </div>
  );
}
