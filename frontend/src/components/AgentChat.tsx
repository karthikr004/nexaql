import { useState, useRef, useEffect, useCallback } from 'react';
import type { ChatTurn, ColumnMeta } from '../types';

// ── Compact inline results table ───────────────────────────────────────────────

function CompactTable({
  rows,
  columns,
  rowCount,
}: {
  rows: Record<string, unknown>[];
  columns: ColumnMeta[];
  rowCount: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const display = expanded ? rows : rows.slice(0, 5);
  const hasMore = rows.length > 5;
  const cleanName = (n: string) => n.replace(/__/g, '.');

  if (!rows.length) return null;

  return (
    <div
      className="overflow-hidden rounded border text-[11px]"
      style={{ borderColor: 'var(--border)' }}
    >
      {/* mini header */}
      <div
        className="flex items-center gap-2 border-b px-3 py-1.5"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)' }}
      >
        <span
          className="font-semibold text-[9px] uppercase tracking-widest"
          style={{ color: 'var(--text-muted)' }}
        >
          Results
        </span>
        <span
          className="rounded border px-1.5 py-0.5 text-[9px]"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)', color: 'var(--success)' }}
        >
          {rowCount} row{rowCount !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr
              className="border-b"
              style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)' }}
            >
              {columns.map((c) => (
                <th
                  key={c.name}
                  className="whitespace-nowrap px-3 py-1.5 font-mono text-[10px]"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {cleanName(c.name)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {display.map((row, i) => (
              <tr
                key={i}
                className="group border-b"
                style={{ borderColor: 'var(--border)' }}
                onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-secondary)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = ''; }}
              >
                {columns.map((c) => {
                  const v = row[c.name];
                  return (
                    <td
                      key={c.name}
                      className="max-w-[220px] truncate whitespace-nowrap px-3 py-1.5 font-mono"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {v === null || v === undefined ? (
                        <span className="italic" style={{ color: 'var(--text-secondary)' }}>null</span>
                      ) : (
                        String(v)
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hasMore && (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="w-full border-t py-1.5 text-[10px] transition-colors"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)' }}
          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-primary)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)'; }}
        >
          {expanded ? '▲ Show less' : `▼ Show all ${rowCount} rows`}
        </button>
      )}
    </div>
  );
}

// ── Syntax highlighter for NexaQL code blocks (single-pass) ─────────────────

const _esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const _KW = new Set(['query', 'mutation']);
const _BOOL = new Set(['true', 'false', 'null']);
const _TOKEN_RE = new RegExp(
  [
    /#[^\n]*/g.source,              // comments
    /"[^"]*"/g.source,              // strings
    /@\w+/g.source,                 // directives
    /\b[a-z_]\w*\s*(?=:)/g.source,  // field key (lookahead colon)
    /\b\w+\b/g.source,              // words
    /\d+(?:\.\d+)?/g.source,        // numbers
  ].join('|'),
  'g',
);

function highlightNexaQL(code: string): string {
  return _esc(code).replace(_TOKEN_RE, (tok) => {
    if (tok.startsWith('#'))
      return `<span style="color:var(--text-secondary);font-style:italic">${tok}</span>`;
    if (tok.startsWith('"'))
      return `<span style="color:#fb923c">${tok}</span>`;
    if (tok.startsWith('@'))
      return `<span style="color:#f97316">${tok}</span>`;
    if (/^[a-z_]\w*$/.test(tok) && _KW.has(tok))
      return `<span style="color:#a78bfa;font-weight:600">${tok}</span>`;
    if (/^[a-z_]\w*$/.test(tok) && _BOOL.has(tok))
      return `<span style="color:#a78bfa">${tok}</span>`;
    if (/^[a-z_]\w*$/.test(tok))
      return `<span style="color:var(--success)">${tok}</span>`;
    if (/^\d/.test(tok))
      return `<span style="color:#22d3ee">${tok}</span>`;
    return tok;
  });
}

// ── Formatted summary with code block support ────────────────────────────────

function FormattedSummary({ text }: { text: string }) {
  // Split on fenced code blocks: ```lang\n...\n```
  const parts = text.split(/(```[\s\S]*?```)/g);

  return (
    <div className="space-y-2">
      {parts.map((part, i) => {
        const codeMatch = part.match(/^```(\w*)\n?([\s\S]*?)```$/);
        if (codeMatch) {
          const code = (codeMatch[2] ?? '').trim();
          const isNexaql = /^(nexaql|graphql)?$/i.test(codeMatch[1] ?? '');
          return (
            <pre
              key={i}
              className="overflow-x-auto rounded border px-3 py-2 font-mono text-[11px] leading-relaxed"
              style={{
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-secondary)',
                color: 'var(--text-primary)',
              }}
              {...(isNexaql
                ? { dangerouslySetInnerHTML: { __html: highlightNexaQL(code) } }
                : { children: code }
              )}
            />
          );
        }
        // Regular text — render paragraphs, handle inline code with backticks
        const trimmed = part.trim();
        if (!trimmed) return null;
        return (
          <p key={i} className="text-[13px] leading-relaxed" style={{ color: 'var(--text-primary)' }}>
            {trimmed.split(/(`[^`]+`)/g).map((seg, j) => {
              if (seg.startsWith('`') && seg.endsWith('`')) {
                return (
                  <code
                    key={j}
                    className="rounded px-1 py-0.5 font-mono text-[11px]"
                    style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--accent)' }}
                  >
                    {seg.slice(1, -1)}
                  </code>
                );
              }
              return seg;
            })}
          </p>
        );
      })}
    </div>
  );
}

// ── Chat bubble ────────────────────────────────────────────────────────────────

function ChatBubble({ turn }: { turn: ChatTurn }) {
  if (turn.loading) {
    return (
      <div className="flex gap-3">
        <div
          className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[10px]"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
        >
          ⬡
        </div>
        <div className="flex items-center gap-2 pt-1 text-xs" style={{ color: 'var(--text-muted)' }}>
          <div
            className="h-3 w-3 animate-spin rounded-full border border-t-transparent"
            style={{ borderColor: 'var(--accent)', borderTopColor: 'transparent' }}
          />
          Thinking…
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <div
        className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[10px]"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
      >
        ⬡
      </div>
      <div className="min-w-0 flex-1 space-y-2.5">
        {/* Summary */}
        <FormattedSummary text={turn.summary} />

        {/* Error */}
        {turn.error && (
          <p
            className="rounded border px-2 py-1.5 font-mono text-[11px]"
            style={{ borderColor: 'var(--error)', backgroundColor: 'var(--bg-error)', color: 'var(--error)' }}
          >
            {turn.error}
          </p>
        )}

        {/* Compact results */}
        {!turn.error && turn.rows.length > 0 && (
          <CompactTable rows={turn.rows} columns={turn.columns} rowCount={turn.rowCount} />
        )}
      </div>
    </div>
  );
}

// ── Fallback suggestions (used when no domain-specific ones are available) ────

const FALLBACK_SUGGESTIONS = [
  'Show me all available data',
  'What tables and fields are available?',
  'Summarize the key metrics',
  'Show me recent records',
];

// ── Main component ─────────────────────────────────────────────────────────────

interface Props {
  onTurnComplete?: (turn: ChatTurn) => void;
  suggestions?: string[];
}

export default function AgentChat({ onTurnComplete, suggestions }: Props) {
  const SUGGESTIONS = suggestions?.length ? suggestions : FALLBACK_SUGGESTIONS;
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns]);

  const sendMessage = useCallback(
    async (question: string) => {
      if (!question.trim() || loading) return;

      const turnId = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;

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
        },
      ]);
      setInput('');
      setLoading(true);

      // Build history for multi-turn context
      const history = turns.flatMap((t) => [
        { role: 'user' as const, content: t.question },
        {
          role: 'assistant' as const,
          content: t.nexaqlQuery ? `${t.summary}\n\n\`\`\`nexaql\n${t.nexaqlQuery}\n\`\`\`` : t.summary,
        },
      ]);

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question, history }),
        });
        const data = await res.json();

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
        };

        setTurns((prev) => prev.map((t) => (t.id !== turnId ? t : completedTurn)));
        onTurnComplete?.(completedTurn);
      } catch (e) {
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
          summary: `Error: ${String(e)}`,
          error: String(e),
        };
        setTurns((prev) => prev.map((t) => (t.id !== turnId ? t : errTurn)));
        onTurnComplete?.(errTurn);
      } finally {
        setLoading(false);
      }
    },
    [turns, loading, onTurnComplete],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <div className="flex h-full flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* Thread */}
      <div className="flex-1 overflow-y-auto">
        {turns.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-5 px-6">
            <div className="text-center">
              <div className="mb-2 text-2xl">⬡</div>
              <p className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>Ask anything about your data</p>
              <p className="mt-1 text-xs" style={{ color: 'var(--text-secondary)' }}>Queries are generated and run automatically</p>
            </div>
            <div className="w-full max-w-md space-y-1.5">
              {SUGGESTIONS.map((s) => (
                <button
                  type="button"
                  key={s}
                  onClick={() => sendMessage(s)}
                  className="w-full rounded border px-3 py-2 text-left text-[12px] transition-colors"
                  style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = 'var(--accent)';
                    e.currentTarget.style.color = 'var(--text-primary)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'var(--border)';
                    e.currentTarget.style.color = 'var(--text-secondary)';
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-5 p-4">
            {turns.map((turn) => (
              <div key={turn.id} className="space-y-2">
                {/* User question */}
                <div className="flex justify-end">
                  <div
                    className="max-w-[80%] rounded-lg border px-3 py-2 text-[13px]"
                    style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-primary)' }}
                  >
                    {turn.question}
                  </div>
                </div>
                {/* Agent response */}
                <ChatBubble turn={turn} />
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Clear + Input */}
      <div
        className="shrink-0 border-t"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-primary)' }}
      >
        {turns.length > 0 && (
          <div className="flex justify-end px-4 pt-2">
            <button
              type="button"
              onClick={() => setTurns([])}
              className="text-[10px] transition-colors"
              style={{ color: 'var(--text-secondary)' }}
              onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-primary)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-secondary)'; }}
            >
              Clear chat
            </button>
          </div>
        )}
        <div className="flex items-end gap-2 px-4 py-3">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your data…"
            rows={2}
            className="flex-1 resize-none rounded-lg border px-3 py-2 text-[13px] leading-relaxed focus:outline-none"
            style={{
              borderColor: 'var(--border)',
              backgroundColor: 'var(--bg-secondary)',
              color: 'var(--text-primary)',
              '--placeholder-color': 'var(--text-muted)',
            } as React.CSSProperties}
            onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--accent)'; }}
            onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; }}
          />
          <button
            type="button"
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || loading}
            className="shrink-0 rounded-lg px-4 py-2 font-semibold text-[12px] transition-all border"
            style={
              !input.trim() || loading
                ? {
                    borderColor: 'var(--border)',
                    backgroundColor: 'var(--bg-elevated)',
                    color: 'var(--text-secondary)',
                    cursor: 'not-allowed',
                  }
                : {
                    borderColor: 'transparent',
                    backgroundColor: 'var(--accent)',
                    color: '#ffffff',
                  }
            }
          >
            {loading ? (
              <div
                className="h-4 w-4 animate-spin rounded-full border-2 border-t-transparent"
                style={{ borderColor: 'var(--accent)', borderTopColor: 'transparent' }}
              />
            ) : (
              'Send'
            )}
          </button>
        </div>
        <p className="px-4 pb-2 text-[10px]" style={{ color: 'var(--text-secondary)' }}>↵ to send · Shift+↵ for new line</p>
      </div>
    </div>
  );
}
