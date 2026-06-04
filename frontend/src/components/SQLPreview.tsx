import { useState } from 'react';

interface Props {
  queryPreview: string | null;
  adapterType: string | null;
  isLoading: boolean;
}

// Very basic SQL syntax highlighter for display
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
  out = out.replace(/\b(\d+)\b/g, (_, n) => `<span style="color: #22d3ee">${n}</span>`);
  out = out.replace(/\b([a-z][a-z0-9]*)\./g, (_, alias) => `<span style="color: var(--text-muted)">${alias}.</span>`);

  return out;
}

function highlightURL(url: string): string {
  const out = url.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // Method (GET / POST)
  return out.replace(/^(GET|POST)\s+(.+)$/, (_, method, rest) => {
    // Split on query string
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
  mysql: { label: 'MySQL', colorVar: '#f97316' },
  mongodb: { label: 'MongoDB', colorVar: 'var(--success)' },
  rest: { label: 'REST API', colorVar: '#a78bfa' },
};

export default function SQLPreview({ queryPreview, adapterType, isLoading }: Props) {
  const [copied, setCopied] = useState(false);
  const [copyHover, setCopyHover] = useState(false);

  const copy = async () => {
    if (!queryPreview) return;
    await navigator.clipboard.writeText(queryPreview);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const isREST = adapterType === 'rest';
  const adapterMeta: { label: string; colorVar: string } = (adapterType ? ADAPTER_LABELS[adapterType] : undefined) ?? {
    label: adapterType ?? 'SQL',
    colorVar: 'var(--success)',
  };
  const panelLabel = isREST ? 'Request Preview' : 'SQL Preview';
  const emptyHint = isREST
    ? 'Write a REST node query to see the generated request'
    : 'Write a query to see the generated SQL';

  const highlighted = queryPreview ? (isREST ? highlightURL(queryPreview) : highlightSQL(queryPreview)) : null;

  return (
    <div className="flex h-full flex-col" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* Header */}
      <div
        className="flex shrink-0 items-center justify-between border-b px-3 py-2"
        style={{ borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <span
            className="font-semibold text-[10px] uppercase tracking-widest"
            style={{ color: 'var(--text-secondary)' }}
          >
            {panelLabel}
          </span>
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
        </div>
        {queryPreview && (
          <button
            type="button"
            onClick={copy}
            onMouseEnter={() => setCopyHover(true)}
            onMouseLeave={() => setCopyHover(false)}
            className="rounded border px-2 py-1 text-[10px] transition-colors"
            style={{
              borderColor: 'var(--border)',
              backgroundColor: 'var(--bg-elevated)',
              color: copyHover ? 'var(--text-primary)' : 'var(--text-secondary)',
            }}
          >
            {copied ? '✓ Copied' : 'Copy'}
          </button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-3">
        {isLoading && (
          <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
            <div
              className="h-3 w-3 animate-spin rounded-full border border-t-transparent"
              style={{ borderColor: 'var(--accent)', borderTopColor: 'transparent' }}
            />
            Translating…
          </div>
        )}

        {!isLoading && !queryPreview && (
          <div className="mt-8 text-center font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
            {emptyHint}
          </div>
        )}

        {!isLoading && highlighted && (
          <pre
            className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed"
            style={{ color: 'var(--text-primary)' }}
            dangerouslySetInnerHTML={{ __html: highlighted }}
          />
        )}
      </div>
    </div>
  );
}
