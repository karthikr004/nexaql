import { useState, useRef, useEffect, useCallback } from 'react';
import type { ChatTurn } from '../../types';
import { useDomain } from '../contexts/DomainContext';
import ChatMessage from '../components/ChatMessage';
import TracePanel from '../components/TracePanel';

const SUGGESTIONS = [
  'Show me all available data',
  'What tables and fields are available?',
  'Summarize the key metrics',
  'Show me recent records',
];

export default function ChatPage() {
  const { activeDomain } = useDomain();
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [apiKeyMissing, setApiKeyMissing] = useState(false);
  const [traceTurnId, setTraceTurnId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const traceOpen = traceTurnId !== null;
  const traceTurn = traceTurnId ? turns.find((t) => t.id === traceTurnId) : null;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns]);

  useEffect(() => {
    fetch('/api/api-keys')
      .then((r) => r.json())
      .then((data) => {
        const keys = data.api_keys ?? [];
        setApiKeyMissing(keys.length === 0);
      })
      .catch(() => {});
  }, []);

  const handleTraceClick = useCallback((turnId: string) => {
    if (traceTurnId === turnId) {
      setTraceTurnId(null);
    } else {
      setTraceTurnId(turnId);
    }
  }, [traceTurnId]);

  const sendMessage = useCallback(
    async (question: string) => {
      if (!question.trim() || loading) return;

      const turnId = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;

      if (apiKeyMissing) {
        const errTurn: ChatTurn = {
          id: turnId,
          question,
          loading: false,
          nexaqlQuery: null,
          queryPreview: null,
          adapterType: null,
          rows: [],
          columns: [],
          rowCount: 0,
          shape: null,
          summary: '',
          error: 'LLM API key not configured. Add one in Settings > API Keys to enable Agent Chat.',
          intent: null,
          generationMode: null,
        };
        setTurns((prev) => [...prev, errTurn]);
        setInput('');
        return;
      }

      setTurns((prev) => [
        ...prev,
        {
          id: turnId,
          question,
          nexaqlQuery: null,
          queryPreview: null,
          adapterType: null,
          rows: [],
          columns: [],
          rowCount: 0,
          shape: null,
          summary: '',
          error: null,
          loading: true,
          intent: null,
          generationMode: null,
        },
      ]);
      setInput('');
      setLoading(true);

      const history = turns.flatMap((t) => [
        { role: 'user' as const, content: t.question },
        {
          role: 'assistant' as const,
          content: t.nexaqlQuery ? `${t.summary}\n\n\`\`\`nexaql\n${t.nexaqlQuery}\n\`\`\`` : t.summary,
        },
      ]);

      try {
        const startTime = performance.now();
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 60000);
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question, history }),
          signal: controller.signal,
        });
        clearTimeout(timeout);
        const data = await res.json();
        const durationMs = Math.round(performance.now() - startTime);

        const completedTurn: ChatTurn = {
          id: turnId,
          question,
          loading: false,
          nexaqlQuery: data.nexaqlQuery ?? null,
          queryPreview: data.queryPreview ?? null,
          adapterType: data.adapterType ?? null,
          rows: data.rows ?? [],
          columns: data.columns ?? [],
          rowCount: data.rowCount ?? 0,
          shape: data.shape ?? null,
          summary: data.summary ?? data.explanation ?? '',
          error: data.error ?? null,
          intent: data.intent ?? null,
          generationMode: data.generationMode ?? null,
          durationMs,
        };

        setTurns((prev) => prev.map((t) => (t.id !== turnId ? t : completedTurn)));
      } catch (e) {
        const msg = e instanceof DOMException && e.name === 'AbortError'
          ? 'Request timed out. The LLM provider may be unreachable.'
          : String(e);
        const errTurn: ChatTurn = {
          id: turnId,
          question,
          loading: false,
          nexaqlQuery: null,
          queryPreview: null,
          adapterType: null,
          rows: [],
          columns: [],
          rowCount: 0,
          shape: null,
          summary: '',
          error: msg,
          intent: null,
          generationMode: null,
        };
        setTurns((prev) => prev.map((t) => (t.id !== turnId ? t : errTurn)));
      } finally {
        setLoading(false);
      }
    },
    [turns, loading, apiKeyMissing],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const handleTextareaInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  };

  return (
    <div
      style={{
        display: 'flex',
        height: '100%',
        background: 'var(--v2-bg-app)',
        overflow: 'hidden',
      }}
    >
      {/* Chat column — full width, content centered when trace closed */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          minWidth: 0,
          overflow: 'hidden',
        }}
      >
        {/* Message thread */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {turns.length === 0 ? (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                gap: 24,
                padding: 32,
              }}
            >
              {apiKeyMissing && (
                <div
                  style={{
                    maxWidth: 480,
                    width: '100%',
                    padding: '12px 16px',
                    borderRadius: 'var(--v2-radius-md)',
                    background: 'var(--v2-amber-50)',
                    border: '1px solid var(--v2-amber-100)',
                    color: 'var(--v2-amber-700)',
                    fontSize: 13,
                  }}
                >
                  <strong>LLM API key required.</strong> Add one in Settings &gt; API Keys to enable chat.
                </div>
              )}

              <div style={{ textAlign: 'center' }}>
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: 'var(--v2-radius-lg)',
                    background: 'var(--v2-accent-subtle)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    margin: '0 auto 12px',
                  }}
                >
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--v2-accent)" strokeWidth="2">
                    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                  </svg>
                </div>
                <h2 className="v2-heading-lg">Ask anything about your data</h2>
                <p className="v2-body-sm" style={{ marginTop: 6 }}>
                  {activeDomain
                    ? `Querying ${activeDomain} domain`
                    : 'Natural language queries, powered by your ontology'}
                </p>
              </div>

              <div style={{ maxWidth: 480, width: '100%', display: 'flex', flexDirection: 'column', gap: 6 }}>
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => sendMessage(s)}
                    className="v2-btn-secondary"
                    style={{
                      width: '100%',
                      justifyContent: 'flex-start',
                      padding: '10px 14px',
                      fontSize: 13,
                      fontWeight: 400,
                      textAlign: 'left',
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div
              style={{
                maxWidth: traceOpen ? 'none' : 720,
                margin: traceOpen ? 0 : '0 auto',
                padding: '20px 24px',
                transition: 'max-width 0.2s ease, margin 0.2s ease',
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                {turns.map((turn) => (
                  <ChatMessage
                    key={turn.id}
                    turn={turn}
                    isTraceActive={traceTurnId === turn.id}
                    onTraceClick={() => handleTraceClick(turn.id)}
                  />
                ))}
              </div>
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Input area */}
        <div
          style={{
            borderTop: '1px solid var(--v2-border)',
            background: 'var(--v2-bg-app)',
            flexShrink: 0,
          }}
        >
          <div
            style={{
              maxWidth: traceOpen ? 'none' : 720,
              margin: traceOpen ? 0 : '0 auto',
              padding: '12px 24px 16px',
              transition: 'max-width 0.2s ease, margin 0.2s ease',
            }}
          >
            {turns.length > 0 && (
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
                <button
                  type="button"
                  onClick={() => { setTurns([]); setTraceTurnId(null); }}
                  className="v2-btn-ghost v2-btn-sm"
                  style={{ fontSize: 11, color: 'var(--v2-text-tertiary)' }}
                >
                  Clear chat
                </button>
              </div>
            )}

            <div
              style={{
                display: 'flex',
                gap: 10,
                alignItems: 'flex-end',
                padding: '10px 14px',
                borderRadius: 'var(--v2-radius-lg)',
                border: '1px solid var(--v2-border)',
                background: 'var(--v2-bg-input)',
                transition: 'border-color var(--v2-transition-fast)',
              }}
              onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--v2-border-focus)'; }}
              onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--v2-border)'; }}
            >
              <textarea
                ref={inputRef}
                value={input}
                onChange={handleTextareaInput}
                onKeyDown={handleKeyDown}
                placeholder="Ask a question about your data..."
                rows={1}
                style={{
                  flex: 1,
                  resize: 'none',
                  border: 'none',
                  outline: 'none',
                  background: 'transparent',
                  fontFamily: 'var(--v2-font-sans)',
                  fontSize: 14,
                  lineHeight: 1.6,
                  color: 'var(--v2-text-primary)',
                  padding: 0,
                }}
              />
              <button
                type="button"
                onClick={() => sendMessage(input)}
                disabled={!input.trim() || loading}
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 'var(--v2-radius-md)',
                  border: 'none',
                  cursor: !input.trim() || loading ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  background: !input.trim() || loading ? 'var(--v2-bg-hover)' : 'var(--v2-accent)',
                  transition: 'all var(--v2-transition-fast)',
                }}
              >
                {loading ? (
                  <div
                    style={{
                      width: 14,
                      height: 14,
                      borderRadius: '50%',
                      border: '2px solid var(--v2-text-tertiary)',
                      borderTopColor: 'transparent',
                      animation: 'v2-spin 0.8s linear infinite',
                    }}
                  />
                ) : (
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke={!input.trim() ? 'var(--v2-text-tertiary)' : 'white'}
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <line x1="22" y1="2" x2="11" y2="13" />
                    <polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                )}
              </button>
            </div>

            <p style={{ fontSize: 11, color: 'var(--v2-text-tertiary)', marginTop: 6, textAlign: 'center' }}>
              Press Enter to send, Shift+Enter for new line
            </p>
          </div>
        </div>
      </div>

      {/* Trace panel — slides in from right */}
      {traceOpen && traceTurn && (
        <TracePanel turn={traceTurn} onClose={() => setTraceTurnId(null)} />
      )}
    </div>
  );
}
