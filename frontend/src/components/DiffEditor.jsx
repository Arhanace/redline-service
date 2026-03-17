import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../api/client';

function computeChanges(oldText, newText) {
  if (oldText === newText) return [];
  if (oldText === '') {
    return [{ operation: 'replace', target: { text: '', occurrence: 1 }, replacement: newText }];
  }

  // Find the exact region that changed by scanning from both ends
  let firstDiff = 0;
  const minLen = Math.min(oldText.length, newText.length);
  while (firstDiff < minLen && oldText[firstDiff] === newText[firstDiff]) firstDiff++;

  let tailOld = oldText.length;
  let tailNew = newText.length;
  while (tailOld > firstDiff && tailNew > firstDiff &&
         oldText[tailOld - 1] === newText[tailNew - 1]) {
    tailOld--;
    tailNew--;
  }

  // Extract the changed region with enough unique context to identify it
  const CONTEXT = 80;
  const ctxStart = Math.max(0, firstDiff - CONTEXT);
  const oldRegion = oldText.slice(ctxStart, tailOld + CONTEXT);
  const newRegion = newText.slice(ctxStart, tailNew + CONTEXT);

  // The target is the old region, replacement is the new region
  // This is precise — exactly the text that changed plus context for uniqueness
  const targetText = oldText.slice(ctxStart, tailOld);
  const replacement = newText.slice(ctxStart, tailNew);

  if (!targetText && !replacement) return [];

  return [{ operation: 'replace', target: { text: targetText, occurrence: 1 }, replacement }];
}

function findAllPositions(text, search) {
  if (!search) return [];
  const positions = [];
  let pos = 0;
  while ((pos = text.indexOf(search, pos)) !== -1) { positions.push(pos); pos += 1; }
  return positions;
}

function FindReplaceBar({ getContent, onReplace, onDirectChange, textareaRef }) {
  const [findText, setFindText] = useState('');
  const [replaceText, setReplaceText] = useState('');
  const [matchCount, setMatchCount] = useState(0);
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    const content = getContent();
    const positions = findText ? findAllPositions(content, findText) : [];
    setMatchCount(positions.length);
    setCurrentIndex(0);
    if (findText && positions.length > 0) {
      const ta = textareaRef?.current;
      if (ta) {
        const activeEl = document.activeElement;
        ta.setSelectionRange(positions[0], positions[0] + findText.length);
        ta.blur(); ta.focus();
        if (activeEl && activeEl !== ta) activeEl.focus();
      }
    }
  }, [findText]);

  const goToMatch = (idx) => {
    const content = getContent();
    const positions = findAllPositions(content, findText);
    if (!positions.length) return;
    const safeIdx = ((idx % positions.length) + positions.length) % positions.length;
    setCurrentIndex(safeIdx);
    const ta = textareaRef?.current;
    if (ta) {
      const pos = positions[safeIdx];
      // Set selection then blur/focus to force browser to scroll selection into view
      ta.setSelectionRange(pos, pos + findText.length);
      ta.blur();
      ta.focus();
    }
  };

  const handleReplace = (all) => {
    if (!findText || matchCount === 0) return;
    const content = getContent();
    if (all) {
      onReplace(content.replaceAll(findText, replaceText));
      // Track as a direct API change — avoids expensive diff on large docs
      onDirectChange({ operation: 'replace', target: { text: findText, occurrence: 'all' }, replacement: replaceText });
    } else {
      const positions = findAllPositions(content, findText);
      const pos = positions[currentIndex];
      if (pos !== undefined) {
        onReplace(content.slice(0, pos) + replaceText + content.slice(pos + findText.length));
        // Record with enough surrounding context to uniquely identify the occurrence
        const ctxBefore = content.slice(Math.max(0, pos - 40), pos);
        const ctxAfter = content.slice(pos + findText.length, pos + findText.length + 40);
        const uniqueTarget = ctxBefore + findText + ctxAfter;
        const uniqueReplacement = ctxBefore + replaceText + ctxAfter;
        onDirectChange({ operation: 'replace', target: { text: uniqueTarget, occurrence: 1 }, replacement: uniqueReplacement });
      }
    }
    // Recount matches after replace
    setTimeout(() => {
      const newContent = getContent();
      const newPositions = findText ? findAllPositions(newContent, findText) : [];
      setMatchCount(newPositions.length);
    }, 0);
  };

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-yellow-50 dark:bg-yellow-900/20 border-b border-gray-200 dark:border-gray-700 text-sm shrink-0">
      <span className="text-xs font-medium text-gray-500 shrink-0">Find & Replace</span>
      <input value={findText} onChange={(e) => setFindText(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); goToMatch(e.shiftKey ? currentIndex - 1 : currentIndex + 1); } }}
        placeholder="Find..." className="border border-gray-300 dark:border-gray-600 rounded px-2 py-0.5 text-sm bg-white dark:bg-gray-800 dark:text-white w-36" autoFocus />
      <input value={replaceText} onChange={(e) => setReplaceText(e.target.value)}
        placeholder="Replace with..." className="border border-gray-300 dark:border-gray-600 rounded px-2 py-0.5 text-sm bg-white dark:bg-gray-800 dark:text-white w-36" />
      <span className="text-xs text-gray-400 shrink-0 tabular-nums min-w-[70px]">
        {findText ? (matchCount > 0 ? `${currentIndex + 1} of ${matchCount}` : '0 matches') : ''}
      </span>
      <button onClick={() => goToMatch(currentIndex - 1)} disabled={matchCount === 0}
        className="text-xs bg-gray-200 hover:bg-gray-300 disabled:opacity-40 dark:bg-gray-700 dark:hover:bg-gray-600 rounded px-1.5 py-0.5 shrink-0">Prev</button>
      <button onClick={() => goToMatch(currentIndex + 1)} disabled={matchCount === 0}
        className="text-xs bg-gray-200 hover:bg-gray-300 disabled:opacity-40 dark:bg-gray-700 dark:hover:bg-gray-600 rounded px-1.5 py-0.5 shrink-0">Next</button>
      <button onClick={() => handleReplace(false)} disabled={matchCount === 0}
        className="text-xs bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white rounded px-2 py-0.5 shrink-0">Replace</button>
      <button onClick={() => handleReplace(true)} disabled={matchCount === 0}
        className="text-xs bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white rounded px-2 py-0.5 shrink-0">Replace All</button>
    </div>
  );
}

export default function DiffEditor({ document, loading, onUpdate, onDelete }) {
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState(null);
  const [showFindReplace, setShowFindReplace] = useState(false);
  const [showRedline, setShowRedline] = useState(false);
  const [diffContent, setDiffContent] = useState(null);
  const textareaRef = useRef(null);
  const originalRef = useRef('');
  const pendingChangesRef = useRef([]);

  useEffect(() => {
    if (document) {
      originalRef.current = document.content;
      pendingChangesRef.current = [];
      if (textareaRef.current) {
        textareaRef.current.value = document.content;
        textareaRef.current.scrollTop = 0;
      }
      setError(null);
      setDeleting(false);
      setShowFindReplace(false);
      setShowRedline(false);
      setDiffContent(null);
    }
  }, [document?.id, document?.version]);

  const getContent = useCallback(() => textareaRef.current?.value || '', []);

  const handleDirectChange = (change) => {
    pendingChangesRef.current.push(change);
  };

  const handleDiscard = () => {
    if (textareaRef.current) textareaRef.current.value = originalRef.current;
    pendingChangesRef.current = [];
    setShowRedline(false);
    setDiffContent(null);
    setError(null);
  };

  const handlePreviewRedline = () => {
    setShowRedline(true);
    setDiffContent(null);

    requestAnimationFrame(() => {
      const current = getContent();
      const original = originalRef.current;
      if (current === original) { setShowRedline(false); return; }

      // If we have tracked Find & Replace operations, show ALL occurrences
      if (pendingChangesRef.current.length > 0) {
        const items = [];
        const CTX = 60;
        let expectedContent = original;

        for (const change of pendingChangesRef.current) {
          const target = change.target?.text || '';
          const replacement = change.replacement || '';
          const isAll = change.target?.occurrence === 'all' || change.target?.occurrence === 0;

          if (isAll) {
            let pos = 0;
            let count = 0;
            while ((pos = expectedContent.indexOf(target, pos)) !== -1) {
              count++;
              items.push({
                prefix: expectedContent.slice(Math.max(0, pos - CTX), pos),
                removed: target,
                added: replacement,
                suffix: expectedContent.slice(pos + target.length, pos + target.length + CTX),
                label: `#${count}`,
              });
              pos += 1;
            }
            expectedContent = expectedContent.replaceAll(target, replacement);
          } else {
            // Single occurrence — search in expectedContent (which has prior changes applied)
            const pos = expectedContent.indexOf(target);
            if (pos >= 0) {
              items.push({
                prefix: expectedContent.slice(Math.max(0, pos - CTX), pos),
                removed: target,
                added: replacement,
                suffix: expectedContent.slice(pos + target.length, pos + target.length + CTX),
              });
              expectedContent = expectedContent.slice(0, pos) + replacement + expectedContent.slice(pos + target.length);
            }
          }
        }

        // Check for additional manual edits beyond the tracked changes
        if (current !== expectedContent) {
          let fd = 0;
          const ml = Math.min(expectedContent.length, current.length);
          while (fd < ml && expectedContent[fd] === current[fd]) fd++;
          let to = expectedContent.length, tn = current.length;
          while (to > fd && tn > fd && expectedContent[to-1] === current[tn-1]) { to--; tn--; }
          items.push({
            prefix: expectedContent.slice(Math.max(0, fd - CTX), fd),
            removed: expectedContent.slice(fd, to),
            added: current.slice(fd, tn),
            suffix: expectedContent.slice(to, Math.min(expectedContent.length, to + CTX)),
            label: 'manual edit',
          });
        }

        setDiffContent({ type: 'changes', items, total: items.length });
        return;
      }

      // Fallback: scan for single manual edit
      let firstDiff = 0;
      const minLen = Math.min(original.length, current.length);
      while (firstDiff < minLen && original[firstDiff] === current[firstDiff]) firstDiff++;

      let tailOld = original.length;
      let tailNew = current.length;
      while (tailOld > firstDiff && tailNew > firstDiff &&
             original[tailOld - 1] === current[tailNew - 1]) {
        tailOld--;
        tailNew--;
      }

      const CTX = 150;
      setDiffContent({
        type: 'single',
        prefix: original.slice(Math.max(0, firstDiff - CTX), firstDiff),
        removed: original.slice(firstDiff, tailOld),
        added: current.slice(firstDiff, tailNew),
        suffix: original.slice(tailOld, Math.min(original.length, tailOld + CTX)),
      });
    });
  };

  const handleReplace = (newContent) => {
    if (textareaRef.current) textareaRef.current.value = newContent;
  };

  const handleDelete = async () => {
    if (!confirm(`Delete "${document.title}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await api.deleteDocument(document.id);
      onDelete(document.id);
    } catch (err) {
      setError(err.message);
      setDeleting(false);
    }
  };

  const handleSubmit = async () => {
    const current = getContent();
    if (current === originalRef.current) return;
    setSubmitting(true);
    setError(null);

    // Combine tracked find-replace operations with any additional manual edits
    let changes = [];
    if (pendingChangesRef.current.length > 0) {
      changes = [...pendingChangesRef.current];
      // Apply tracked changes to original to get expected content
      let expected = originalRef.current;
      for (const c of changes) {
        const t = c.target?.text || '';
        const r = c.replacement || '';
        if (c.target?.occurrence === 'all' || c.target?.occurrence === 0) {
          expected = expected.replaceAll(t, r);
        } else {
          const pos = expected.indexOf(t);
          if (pos >= 0) expected = expected.slice(0, pos) + r + expected.slice(pos + t.length);
        }
      }
      // If there are additional manual edits, add them
      if (current !== expected) {
        const manualChanges = computeChanges(expected, current);
        changes = changes.concat(manualChanges);
      }
    } else {
      changes = computeChanges(originalRef.current, current);
    }

    if (changes.length === 0) {
      setError('No replaceable changes detected.');
      setSubmitting(false);
      return;
    }

    try {
      const updated = await api.patchDocument(document.id, changes);
      onUpdate(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <div className="text-center">
          <div className="text-lg mb-1">Loading document...</div>
        </div>
      </div>
    );
  }

  if (!document) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <div className="text-4xl">Select a document to start editing</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 shrink-0">
        <div>
          <h1 className="text-lg font-semibold dark:text-white">{document.title}</h1>
          <span className="text-xs text-gray-400">Version {document.version}</span>
        </div>
        <div className="flex items-center gap-2">
          {error && <span className="text-xs text-red-500 max-w-xs truncate">{error}</span>}
          <button onClick={() => setShowFindReplace(!showFindReplace)}
            className={`text-sm px-2 py-1 rounded transition-colors ${showFindReplace ? 'bg-yellow-100 text-yellow-700' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'}`}>
            Find & Replace
          </button>
          <button onClick={handlePreviewRedline}
            className="text-sm text-blue-600 hover:text-blue-800 hover:bg-blue-50 px-2 py-1 rounded transition-colors">
            Preview Redline
          </button>
          <button onClick={handleDelete} disabled={deleting}
            className="text-sm text-red-500 hover:text-red-700 hover:bg-red-50 px-2 py-1 rounded transition-colors">
            {deleting ? 'Deleting...' : 'Delete'}
          </button>
          <button onClick={handleDiscard}
            className="text-sm text-gray-500 hover:text-gray-700 px-2 py-1">
            Discard
          </button>
          <button onClick={handleSubmit} disabled={submitting}
            className="text-sm bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white rounded px-4 py-1.5 transition-colors">
            {submitting ? 'Saving...' : 'Submit Changes'}
          </button>
        </div>
      </div>

      {showFindReplace && (
        <FindReplaceBar getContent={getContent} onReplace={handleReplace} onDirectChange={handleDirectChange} textareaRef={textareaRef} />
      )}

      {/* Editor — uncontrolled textarea, no word-wrap for perf on large docs */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <textarea
          ref={textareaRef}
          defaultValue={document.content}
          className="w-full h-full p-4 text-sm font-mono resize-none border-0 outline-none bg-white dark:bg-gray-900 dark:text-white leading-relaxed"
          style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', contain: 'strict' }}
          spellCheck={false}
        />
      </div>

      {/* Redline preview — on demand only */}
      {showRedline && !diffContent && (
        <div className="border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 p-4 text-center text-xs text-gray-400 shrink-0">
          Computing diff...
        </div>
      )}
      {showRedline && diffContent && (
        <div className="border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 max-h-80 overflow-auto shrink-0">
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-gray-100 dark:border-gray-700 sticky top-0 bg-gray-50 dark:bg-gray-800 z-10">
            <span className="text-xs font-medium text-gray-500">
              Redline Preview
              {diffContent.total && <span className="ml-2 text-gray-400">({diffContent.total} changes)</span>}
            </span>
            <button onClick={() => { setShowRedline(false); setDiffContent(null); }}
              className="text-xs text-gray-400 hover:text-gray-600">Close</button>
          </div>
          <div className="p-3 text-sm font-mono leading-relaxed whitespace-pre-wrap break-words">
            {diffContent.type === 'changes' && diffContent.items.map((item, i) => (
              <div key={i} className="mb-2 pb-2 border-b border-gray-100 dark:border-gray-700 last:border-0 text-xs">
                <span className="text-gray-400">...{item.prefix}</span>
                <span className="bg-red-100 text-red-700 line-through">{item.removed}</span>
                <span className="bg-green-100 text-green-700">{item.added}</span>
                <span className="text-gray-400">{item.suffix}...</span>
                {item.label && <span className="ml-2 text-gray-300 text-xs">{item.label}</span>}
              </div>
            ))}
            {diffContent.type === 'single' && (
              <>
                {diffContent.prefix && <span className="text-gray-400">...{diffContent.prefix}</span>}
                <span className="bg-red-100 text-red-700 line-through">{diffContent.removed}</span>
                <span className="bg-green-100 text-green-700">{diffContent.added}</span>
                {diffContent.suffix && <span className="text-gray-400">{diffContent.suffix}...</span>}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
