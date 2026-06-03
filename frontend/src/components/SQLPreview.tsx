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
    out = out.replace(new RegExp(`\\b${kw}\\b`, 'g'), `<span class="text-[#a78bfa] font-semibold">${kw}</span>`);
  });

  out = out.replace(/'[^']*'/g, (m) => `<span class="text-orange-400">${m}</span>`);
  out = out.replace(/\b(\d+)\b/g, (_, n) => `<span class="text-cyan-400">${n}</span>`);
  out = out.replace(/\b([a-z][a-z0-9]*)\./g, (_, alias) => `<span class="text-slate-400">${alias}.</span>`);
  out = out.replace(/--.*/g, (m) => `<span class="text-slate-600 italic">${m}</span>`);

  return out;
}

function highlightURL(url: string): string {
  const out = url.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // Method (GET / POST)
  return out.replace(/^(GET|POST)\s+(.+)$/, (_, method, rest) => {
    // Split on query string
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
  mysql: { label: 'MySQL', color: 'text-[#f97316]' },
  mongodb: { label: 'MongoDB', color: 'text-[#3dd68c]' },
  rest: { label: 'REST API', color: 'text-[#a78bfa]' },
};

export default function SQLPreview({ queryPreview, adapterType, isLoading }: Props) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    if (!queryPreview) return;
    await navigator.clipboard.writeText(queryPreview);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const isREST = adapterType === 'rest';
  const adapterMeta: { label: string; color: string } = (adapterType ? ADAPTER_LABELS[adapterType] : undefined) ?? {
    label: adapterType ?? 'SQL',
    color: 'text-[#3dd68c]',
  };
  const panelLabel = isREST ? 'Request Preview' : 'SQL Preview';
  const emptyHint = isREST
    ? 'Write a REST node query to see the generated request'
    : 'Write a query to see the generated SQL';

  const highlighted = queryPreview ? (isREST ? highlightURL(queryPreview) : highlightSQL(queryPreview)) : null;

  return (
    <div className="flex h-full flex-col bg-[#0f1117]">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-[#252d3d] border-b px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-[10px] text-slate-400 uppercase tracking-widest">{panelLabel}</span>
          <span
            className={`rounded border border-[#252d3d] bg-[#1e2535] px-1.5 py-0.5 text-[9px] ${adapterMeta.color}`}
          >
            {adapterMeta.label}
          </span>
        </div>
        {queryPreview && (
          <button
            type="button"
            onClick={copy}
            className="rounded border border-[#252d3d] bg-[#1e2535] px-2 py-1 text-[10px] text-slate-400 transition-colors hover:text-slate-200"
          >
            {copied ? '✓ Copied' : 'Copy'}
          </button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-3">
        {isLoading && (
          <div className="flex items-center gap-2 text-slate-500 text-xs">
            <div className="h-3 w-3 animate-spin rounded-full border border-[#4f8ef7] border-t-transparent" />
            Translating…
          </div>
        )}

        {!isLoading && !queryPreview && (
          <div className="mt-8 text-center font-mono text-slate-600 text-xs">{emptyHint}</div>
        )}

        {!isLoading && highlighted && (
          <pre
            className="whitespace-pre-wrap font-mono text-[11px] text-slate-300 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: highlighted }}
          />
        )}
      </div>
    </div>
  );
}
