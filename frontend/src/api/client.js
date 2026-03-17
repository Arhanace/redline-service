const BASE = import.meta.env.VITE_API_URL || '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Request failed', code: res.status }));
    throw new Error(err.error || err.detail || 'Request failed');
  }
  if (res.status === 204) return null;
  return res.json();
}

async function fetchDocument(id, signal) {
  const [meta, content] = await Promise.all([
    request(`/documents/${id}?max_length=0`, { signal }),
    fetch(`${BASE}/documents/${id}/content`, { signal }).then((r) => {
      if (!r.ok) throw new Error('Failed to fetch content');
      return r.text();
    }),
  ]);
  return { ...meta, content, content_length: content.length };
}

export const api = {
  listDocuments: () => request('/documents'),
  getDocument: (id, signal) => fetchDocument(id, signal),
  createDocument: (data) => request('/documents', { method: 'POST', body: JSON.stringify(data) }),
  patchDocument: (id, changes) => request(`/documents/${id}`, { method: 'PATCH', body: JSON.stringify({ changes }) }),
  deleteDocument: (id) => request(`/documents/${id}`, { method: 'DELETE' }),
  searchDocuments: (q, limit = 50, offset = 0) => request(`/documents/search?q=${encodeURIComponent(q)}&limit=${limit}&offset=${offset}`),
  getHistory: (id) => request(`/documents/${id}/history`),
  getHistoryEntry: (docId, entryId) => request(`/documents/${docId}/history/${entryId}`),
  uploadDocument: async (file) => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${BASE}/documents/upload`, { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: 'Upload failed' }));
      throw new Error(err.error || 'Upload failed');
    }
    return res.json();
  },
};
