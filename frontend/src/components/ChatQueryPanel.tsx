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
        return `<span style="color: var(--text-secondary); font-style: italic">${line}</span>`;
      }

      // query/mutation keyword + query name (same line, single pass)
      line = line.replace(
        /\b(query|mutation)\b(\s+)(\w+)/g,
        `<span style="color: #a78bfa; font-weight: 600">$1</span>$2<span style="color: var(--accent); font-weight: 600">$3</span>`,
      );

      // Directives @word
      line = line.replace(/@(\w+)/g, `<span style="color: #f97316">@$1</span>`);

      // Aggregation aliases / field aliases  word: (before any parens)
      line = line.replace(/\b([a-z_]\w*)\s*:/g, `<span style="color: var(--success)">$1</span>:`);

      // String values "..."
      line = line.replace(/"([^"]*)"/g, `<span style="color: #fb923c">"$1"</span>`);

      // Numbers
      line = line.replace(/\b(\d+(?:\.\d+)?)\b/g, `<span style="color: #22d3ee">$1</span>`);

      // Booleans / null
      line = line.replace(/\b(true|false|null)\b/g, `<span style="color: #a78bfa">$1</span>`);

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
    out = out.replace(new RegExp(`\\b${kw}\\b`, 'g'), `<span style="color: #a78bfa; font-weight: 600">${kw}</span>`);
  });
  out = out.replace(/'[^']*'/g, (m) => `<span style="color: #fb923c">${m}</span>`);
  out = out.replace(/\b(\d+)\b/g, `<span style="color: #22d3ee">$1</span>`);
  out = out.replace(/\b([a-z][a-z0-9]*)\./g, `<span style="color: var(--text-muted)">$1.</span>`);
  return out;
}

function highlightURL(url: string): string {
  const out = url.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return out.replace(/^(GET|POST)\s+(.+)$/, (_, method, rest) => {
    const qIdx = rest.indexOf('?');
    if (qIdx === -1) {
      return `<span style="color: #a78bfa; font-weight: 600">${method}</span> <span style="color: var(--accent)">${rest}</span>`;
    }
    const path = rest.slice(0, qIdx);
    const params = rest
      .slice(qIdx + 1)
      .split('&amp;')
      .map((p: string) => {
        const [k, v] = p.split('=');
        return `<span style="color: #22d3ee">${k}</span>=<span style="color: #fb923c">${v ?? ''}</span>`;
      })
      .join(`<span style="color: var(--text-secondary)">&amp;</span>`);
    return `<span style="color: #a78bfa; font-weight: 600">${method}</span> <span style="color: var(--accent)">${path}</span><span style="color: var(--text-secondary)">?</span>${params}`;
  });
}

const ADAPTER_LABELS: Record<string, { label: string; colorVar: string }> = {
  postgresql: { label: 'PostgreSQL', colorVar: 'var(--success)' },
  rest: { label: 'REST API', colorVar: '#a78bfa' },
  mysql: { label: 'MySQL', colorVar: '#f97316' },
  mongodb: { label: 'MongoDB', colorVar: 'var(--success)' },
};

// ── CopyButton ─────────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const [hover, setHover] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button
      type="button"
      onClick={copy}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className="rounded border px-1.5 py-0.5 text-[10px] transition-colors"
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-elevated)',
        color: hover ? 'var(--text-primary)' : 'var(--text-secondary)',
      }}
    >
      {copied ? '✓' : 'Copy'}
    </button>
  );
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function ChatQueryPanel({ nexaqlQuery, queryPreview, adapterType }: Props) {
  const adapterMeta: { label: string; colorVar: string } = (adapterType ? ADAPTER_LABELS[adapterType] : undefined) ?? {
    label: adapterType ?? 'Query',
    colorVar: 'var(--text-secondary)',
  };

  const isREST = adapterType === 'rest';

  const nexaqlHighlighted = nexaqlQuery ? highlightNexaQL(nexaqlQuery) : null;
  const previewHighlighted = queryPreview ? (isREST ? highlightURL(queryPreview) : highlightSQL(queryPreview)) : null;

  return (
    <div className="flex h-full flex-col overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* ── NexaQL Query ── */}
      <div
        className="flex shrink-0 items-center justify-between border-b px-3 py-2"
        style={{ borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <span
            className="font-semibold text-[10px] uppercase tracking-widest"
            style={{ color: 'var(--text-secondary)' }}
          >
            NexaQL Query
          </span>
          <span
            className="rounded border px-1.5 py-0.5 text-[9px]"
            style={{
              borderColor: 'var(--border)',
              backgroundColor: 'var(--bg-elevated)',
              color: 'var(--accent)',
            }}
          >
            generated
          </span>
        </div>
        {nexaqlQuery && <CopyButton text={nexaqlQuery} />}
      </div>

      <div className="shrink-0 overflow-auto p-3" style={{ maxHeight: '45%' }}>
        {nexaqlHighlighted ? (
          <pre
            className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed"
            style={{ color: 'var(--text-primary)' }}
            dangerouslySetInnerHTML={{ __html: nexaqlHighlighted }}
          />
        ) : (
          <div className="mt-4 text-center font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
            Send a message to generate a query
          </div>
        )}
      </div>

      {/* ── Divider ── */}
      <div className="shrink-0 border-t" style={{ borderColor: 'var(--border)' }} />

      {/* ── Translated preview ── */}
      <div
        className="flex shrink-0 items-center justify-between border-b px-3 py-2"
        style={{ borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <span
            className="font-semibold text-[10px] uppercase tracking-widest"
            style={{ color: 'var(--text-secondary)' }}
          >
            {isREST ? 'Request' : 'SQL'}
          </span>
          {adapterType && (
            <span
              className="rounded border px-1.5 py-0.5 text-[9px]"
              style={{
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-elevated)',
                color: adapterMeta.colorVar,
              }}
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
            className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed"
            style={{ color: 'var(--text-primary)' }}
            dangerouslySetInnerHTML={{ __html: previewHighlighted }}
          />
        ) : (
          <div className="mt-4 text-center font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
            {nexaqlQuery ? 'No translation available' : 'Translation will appear here'}
          </div>
        )}
      </div>
    </div>
  );
}
