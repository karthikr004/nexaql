import { useState, useCallback, useEffect, useRef } from 'react';

interface Thread {
  id: number;
  title: string | null;
  domain: string | null;
  updated_at: string | null;
  message_count: number;
  last_message: string | null;
}

interface ThreadSidebarProps {
  activeThreadId: number | null;
  onSelectThread: (threadId: number) => void;
  onNewChat: () => void;
  onClose: () => void;
  refreshKey: number;
}

export default function ThreadSidebar({ activeThreadId, onSelectThread, onNewChat, onClose, refreshKey }: ThreadSidebarProps) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const editRef = useRef<HTMLInputElement>(null);

  const fetchThreads = useCallback(async () => {
    try {
      const res = await fetch('/api/chat/threads', { credentials: 'include' });
      if (res.ok) {
        setThreads(await res.json());
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => { fetchThreads(); }, [fetchThreads, refreshKey]);

  const handleDelete = async (e: React.MouseEvent, threadId: number) => {
    e.stopPropagation();
    const res = await fetch(`/api/chat/threads/${threadId}`, {
      method: 'DELETE',
      credentials: 'include',
    });
    if (res.ok) {
      fetchThreads();
      if (activeThreadId === threadId) {
        onNewChat();
      }
    }
  };

  const handleRename = async (threadId: number) => {
    if (!editTitle.trim()) {
      setEditingId(null);
      return;
    }
    await fetch(`/api/chat/threads/${threadId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: editTitle.trim() }),
      credentials: 'include',
    });
    setEditingId(null);
    fetchThreads();
  };

  const startEdit = (e: React.MouseEvent, thread: Thread) => {
    e.stopPropagation();
    setEditingId(thread.id);
    setEditTitle(thread.title || '');
    setTimeout(() => editRef.current?.focus(), 0);
  };

  const groupThreads = (list: Thread[]) => {
    const now = new Date();
    const today: Thread[] = [];
    const week: Thread[] = [];
    const older: Thread[] = [];

    for (const t of list) {
      if (!t.updated_at) { older.push(t); continue; }
      const d = new Date(t.updated_at);
      const diff = (now.getTime() - d.getTime()) / 86400000;
      if (diff < 1) today.push(t);
      else if (diff < 7) week.push(t);
      else older.push(t);
    }
    return { today, week, older };
  };

  const { today, week, older } = groupThreads(threads);

  const renderThread = (t: Thread) => {
    const isActive = activeThreadId === t.id;
    const displayTitle = t.title || t.last_message || 'New chat';

    return (
      <div
        key={t.id}
        className={`v2-thread-item ${isActive ? 'active' : ''}`}
        onClick={() => onSelectThread(t.id)}
      >
        {editingId === t.id ? (
          <input
            ref={editRef}
            className="v2-thread-edit-input"
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            onBlur={() => handleRename(t.id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleRename(t.id);
              if (e.key === 'Escape') setEditingId(null);
            }}
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <>
            <span className="v2-thread-title">{displayTitle}</span>
            <div className="v2-thread-actions">
              <button
                type="button"
                className="v2-thread-action-btn"
                onClick={(e) => startEdit(e, t)}
                title="Rename"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
              </button>
              <button
                type="button"
                className="v2-thread-action-btn v2-thread-delete"
                onClick={(e) => handleDelete(e, t.id)}
                title="Delete"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                </svg>
              </button>
            </div>
          </>
        )}
      </div>
    );
  };

  const renderGroup = (label: string, items: Thread[]) => {
    if (items.length === 0) return null;
    return (
      <div className="v2-thread-group">
        <div className="v2-thread-group-label">{label}</div>
        {items.map(renderThread)}
      </div>
    );
  };

  return (
    <div className="v2-thread-sidebar">
      <div className="v2-thread-sidebar-header" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <button
          type="button"
          className="v2-btn v2-btn-primary v2-btn-sm"
          onClick={onNewChat}
          style={{ flex: 1, justifyContent: 'center', gap: 6 }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          New chat
        </button>
        <button
          type="button"
          className="v2-thread-action-btn"
          onClick={onClose}
          title="Close sidebar"
          style={{ width: 28, height: 28 }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
      <div className="v2-thread-list">
        {threads.length === 0 ? (
          <div className="v2-thread-empty">
            <p>No conversations yet</p>
          </div>
        ) : (
          <>
            {renderGroup('Today', today)}
            {renderGroup('This week', week)}
            {renderGroup('Older', older)}
          </>
        )}
      </div>
    </div>
  );
}
