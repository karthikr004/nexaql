import { useState } from 'react';

interface Props {
  nexaqlQuery: string | null;
  queryPreview: string | null;
  adapterType: string | null;
}

// ── Syntax highlighters ────────────────────────────────────────────────────────

// Process line by line to avoid cascading regex interference on HTML tags
function highlightNexaQL(code: string): string {
  return code
    .split('\n')
    .map((rawLine) => {
      // Escape HTML special chars in this line's text
      let line = rawLine.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

      // Whole-line comments
      if (/^\s*#/.test(line)) {
        return `<span class="text-slate-600 italic">${line}</span>`;
      }

      // query/mutation keyword + query name (same line, single pass)
      line = line.replace(
        /\b(query|mutation)\b(\s+)(\w+)/g,
        `<span class="text-[#a78bfa] font-semibold">$1</span>$2<span class="text-[#4f8ef7] font-semibold">$3</span>`,
      );

      // Directives @word
      line = line.replace(/@(\w+)/g, `<span class="text-[#f97316]">@$1</span>`);

      // Aggregation aliases / field aliases  word: (before any parens)
      line = line.replace(/\b([a-z_]\w*)\s*:/g, `<span class="text-[#3dd68c]">$1</span>:`);

      // String values "..."
      line = line.replace(/"([^"]*)"/g, `<span class="text-orange-400">"$1"</span>`);

      // Numbers
      line = line.replace(/\b(\d+(?:\.\d+)?)\b/g, `<span class="text-cyan-400">$1</span>`);

      // Booleans / null
      line = line.replace(/\b(true|false|null)\b/g, `<span class="text-[#a78bfa]">$1</span>`);

      return line;
    })
    .join('\n');
}

function highlightSQL(sql: string): string {
  const keywords = [
    'SELECT',
    'FROM',
    'WHERE',
    'JOIN',
    'LEFT JOIN',
    'INNER JOIN',
    'GROUP BY',
    'ORDER BY',
    'HAVING',
    'LIMIT',
    'OFFSET',
    'ON',
    'AND',
    'OR',
    'NOT',
    'IN',
    'IS',
    'NULL',
    'AS',
    'DISTINCT',
    'COUNT',
    'SUM',
    'AVG',
    'MIN',
    'MAX',
    'EXISTS',
    'INTERVAL',
    'CURRENT_DATE',
    'TRUE',
    'FALSE',
  ];

  let out = sql.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  keywords.forEach((kw) => {
    out = out.replace(new RegExp(`\\b${kw}\\b`, 'g'), `<span class="text-[#a78bfa] font-semibold">${kw}</span>`);
  });
  out = out.replace(/'[^']*'/g, (m) => `<span class="text-orange-400">${m}</span>`);
  out = out.replace(/\b(\d+)\b/g, `<span class="text-cyan-400">$1</span>`);
  out = out.replace(/\b([a-z][a-z0-9]*)\./g, `<span class="text-slate-400">$1.</span>`);
  out = out.replace(/--.*/g, (m) => `<span class="text-slate-600 italic">${m}</span>`);
  return out;
}

function highlightURL(url: string): string {
  const out = url.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return out.replace(/^(GET|POST)\s+(.+)$/, (_, method, rest) => {
    const qIdx = rest.indexOf('?');
    if (qIdx === -1) {
      return `<span class="text-[#a78bfa] font-semibold">${method}</span> <span class="text-[#4f8ef7]">${rest}</span>`;
    }
    const path = rest.slice(0, qIdx);
    const params = rest
      .slice(qIdx + 1)
      .split('&amp;')
      .map((p: string) => {
        const [k, v] = p.split('=');
        return `<span class="text-cyan-400">${k}</span>=<span class="text-orange-400">${v ?? ''}</span>`;
      })
      .join("<span class='text-slate-600'>&amp;</span>");
    return `<span class="text-[#a78bfa] font-semibold">${method}</span> <span class="text-[#4f8ef7]">${path}</span><span class="text-slate-600">?</span>${params}`;
  });
}

const ADAPTER_LABELS: Record<string, { label: string; color: string }> = {
  postgresql: { label: 'PostgreSQL', color: 'text-[#3dd68c]' },
  rest: { label: 'REST API', color: 'text-[#a78bfa]' },
  mysql: { label: 'MySQL', color: 'text-[#f97316]' },
  mongodb: { label: 'MongoDB', color: 'text-[#3dd68c]' },
};

// ── CopyButton ─────────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button
      type="button"
      onClick={copy}
      className="rounded border border-[#252d3d] bg-[#1e2535] px-1.5 py-0.5 text-[10px] text-slate-400 transition-colors hover:text-slate-200"
    >
      {copied ? '✓' : 'Copy'}
    </button>
  );
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function ChatQueryPanel({ nexaqlQuery, queryPreview, adapterType }: Props) {
  const adapterMeta: { label: string; color: string } = (adapterType ? ADAPTER_LABELS[adapterType] : undefined) ?? {
    label: adapterType ?? 'Query',
    color: 'text-slate-400',
  };

  const isREST = adapterType === 'rest';

  const nexaqlHighlighted = nexaqlQuery ? highlightNexaQL(nexaqlQuery) : null;
  const previewHighlighted = queryPreview ? (isREST ? highlightURL(queryPreview) : highlightSQL(queryPreview)) : null;

  return (
    <div className="flex h-full flex-col overflow-hidden bg-[#0f1117]">
      {/* ── NexaQL Query ── */}
      <div className="flex shrink-0 items-center justify-between border-[#252d3d] border-b px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-[10px] text-slate-400 uppercase tracking-widest">NexaQL Query</span>
          <span className="rounded border border-[#252d3d] bg-[#1e2535] px-1.5 py-0.5 text-[#4f8ef7] text-[9px]">
            generated
          </span>
        </div>
        {nexaqlQuery && <CopyButton text={nexaqlQuery} />}
      </div>

      <div className="shrink-0 overflow-auto p-3" style={{ maxHeight: '45%' }}>
        {nexaqlHighlighted ? (
          <pre
            className="whitespace-pre-wrap font-mono text-[11px] text-slate-300 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: nexaqlHighlighted }}
          />
        ) : (
          <div className="mt-4 text-center font-mono text-slate-600 text-xs">Send a message to generate a query</div>
        )}
      </div>

      {/* ── Divider ── */}
      <div className="shrink-0 border-[#252d3d] border-t" />

      {/* ── Translated preview ── */}
      <div className="flex shrink-0 items-center justify-between border-[#252d3d] border-b px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-[10px] text-slate-400 uppercase tracking-widest">
            {isREST ? 'Request' : 'SQL'}
          </span>
          {adapterType && (
            <span
              className={`rounded border border-[#252d3d] bg-[#1e2535] px-1.5 py-0.5 text-[9px] ${adapterMeta.color}`}
            >
              {adapterMeta.label}
            </span>
          )}
        </div>
        {queryPreview && <CopyButton text={queryPreview} />}
      </div>

      <div className="flex-1 overflow-auto p-3">
        {previewHighlighted ? (
          <pre
            className="whitespace-pre-wrap font-mono text-[11px] text-slate-300 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: previewHighlighted }}
          />
        ) : (
          <div className="mt-4 text-center font-mono text-slate-600 text-xs">
            {nexaqlQuery ? 'No translation available' : 'Translation will appear here'}
          </div>
        )}
      </div>
    </div>
  );
}
