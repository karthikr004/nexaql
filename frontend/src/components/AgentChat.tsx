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
    <div className="overflow-hidden rounded border border-[#252d3d] text-[11px]">
      {/* mini header */}
      <div className="flex items-center gap-2 border-[#252d3d] border-b bg-[#131920] px-3 py-1.5">
        <span className="font-semibold text-[9px] text-slate-500 uppercase tracking-widest">Results</span>
        <span className="rounded border border-[#252d3d] bg-[#1e2535] px-1.5 py-0.5 text-[#3dd68c] text-[9px]">
          {rowCount} row{rowCount !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="border-[#252d3d] border-b bg-[#0d1117]">
              {columns.map((c) => (
                <th key={c.name} className="whitespace-nowrap px-3 py-1.5 font-mono text-[10px] text-slate-500">
                  {cleanName(c.name)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {display.map((row, i) => (
              <tr key={i} className="border-[#1e2535] border-b hover:bg-[#131920]">
                {columns.map((c) => {
                  const v = row[c.name];
                  return (
                    <td
                      key={c.name}
                      className="max-w-[220px] truncate whitespace-nowrap px-3 py-1.5 font-mono text-slate-300"
                    >
                      {v === null || v === undefined ? <span className="text-slate-600 italic">null</span> : String(v)}
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
          className="w-full border-[#1e2535] border-t bg-[#0d1117] py-1.5 text-[10px] text-slate-500 transition-colors hover:text-slate-300"
        >
          {expanded ? '▲ Show less' : `▼ Show all ${rowCount} rows`}
        </button>
      )}
    </div>
  );
}

// ── Chat bubble ────────────────────────────────────────────────────────────────

function ChatBubble({ turn }: { turn: ChatTurn }) {
  if (turn.loading) {
    return (
      <div className="flex gap-3">
        <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[#252d3d] bg-[#1e2535] text-[10px]">
          ⬡
        </div>
        <div className="flex items-center gap-2 pt-1 text-slate-500 text-xs">
          <div className="h-3 w-3 animate-spin rounded-full border border-[#4f8ef7] border-t-transparent" />
          Thinking…
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[#252d3d] bg-[#1e2535] text-[10px]">
        ⬡
      </div>
      <div className="min-w-0 flex-1 space-y-2.5">
        {/* Summary */}
        <p className="text-[13px] text-slate-200 leading-relaxed">{turn.summary}</p>

        {/* Error */}
        {turn.error && (
          <p className="rounded border border-red-900/40 bg-[#1a0f0f] px-2 py-1.5 font-mono text-[11px] text-red-400">
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

// ── Suggested starter questions ────────────────────────────────────────────────

const SUGGESTIONS = [
  'Show me all orders from the last 30 days',
  'Which customers have spent the most?',
  'What are the top selling products?',
  'Show revenue breakdown by category',
];

// ── Main component ─────────────────────────────────────────────────────────────

interface Props {
  onTurnComplete?: (turn: ChatTurn) => void;
}

export default function AgentChat({ onTurnComplete }: Props) {
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
    <div className="flex h-full flex-col bg-[#0f1117]">
      {/* Thread */}
      <div className="flex-1 overflow-y-auto">
        {turns.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-5 px-6">
            <div className="text-center">
              <div className="mb-2 text-2xl">⬡</div>
              <p className="font-medium text-slate-300 text-sm">Ask anything about your data</p>
              <p className="mt-1 text-slate-600 text-xs">Queries are generated and run automatically</p>
            </div>
            <div className="w-full max-w-md space-y-1.5">
              {SUGGESTIONS.map((s) => (
                <button
                  type="button"
                  key={s}
                  onClick={() => sendMessage(s)}
                  className="w-full rounded border border-[#252d3d] bg-[#131920] px-3 py-2 text-left text-[12px] text-slate-400 transition-colors hover:border-[#4f8ef7] hover:text-slate-200"
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
                  <div className="max-w-[80%] rounded-lg border border-[#2d3f63] bg-[#1e2d4a] px-3 py-2 text-[13px] text-slate-200">
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
      <div className="shrink-0 border-[#252d3d] border-t bg-[#0d1117]">
        {turns.length > 0 && (
          <div className="flex justify-end px-4 pt-2">
            <button
              type="button"
              onClick={() => setTurns([])}
              className="text-[10px] text-slate-600 transition-colors hover:text-slate-400"
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
            className="flex-1 resize-none rounded-lg border border-[#252d3d] bg-[#131920] px-3 py-2 text-[13px] text-slate-200 leading-relaxed placeholder-slate-600 focus:border-[#4f8ef7] focus:outline-none"
          />
          <button
            type="button"
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || loading}
            className={`shrink-0 rounded-lg px-4 py-2 font-semibold text-[12px] transition-all ${
              !input.trim() || loading
                ? 'cursor-not-allowed border border-[#252d3d] bg-[#1e2535] text-slate-600'
                : 'border border-transparent bg-[#4f8ef7] text-white hover:bg-[#3b7de8]'
            }`}
          >
            {loading ? (
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#4f8ef7] border-t-transparent" />
            ) : (
              'Send'
            )}
          </button>
        </div>
        <p className="px-4 pb-2 text-[10px] text-slate-600">↵ to send · Shift+↵ for new line</p>
      </div>
    </div>
  );
}
