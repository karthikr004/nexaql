import { useState } from 'react';

interface Props {
  nexaqlQuery: string | null;
  queryPreview: string | null;
  adapterType: string | null;
  intent: Record<string, unknown> | null;
  generationMode: string | null;
}

// ── Syntax highlighters (single-pass to avoid cascading regex bugs) ───────────

const _esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const _NEXAQL_KW = new Set(['query', 'mutation']);
const _NEXAQL_BOOL = new Set(['true', 'false', 'null']);

// Single-pass: one regex matches ALL token types at once — no replacement ever
// sees another replacement's HTML output.
const _NEXAQL_TOKEN =
  /#[^\n]*/g.source + '|' +          // comments
  /"[^"]*"/g.source + '|' +          // strings
  /@\w+/g.source + '|' +             // directives
  /\b[a-z_]\w*\s*(?=:)/g.source + '|' + // field key (lookahead for colon)
  /\b\w+\b/g.source + '|' +          // words (keywords, bools, identifiers)
  /\d+(?:\.\d+)?/g.source;           // numbers
const _NEXAQL_RE = new RegExp(_NEXAQL_TOKEN, 'g');

function highlightNexaQL(code: string): string {
  return _esc(code).replace(_NEXAQL_RE, (tok) => {
    if (tok.startsWith('#'))
      return `<span style="color:var(--text-secondary);font-style:italic">${tok}</span>`;
    if (tok.startsWith('"'))
      return `<span style="color:#fb923c">${tok}</span>`;
    if (tok.startsWith('@'))
      return `<span style="color:#f97316">${tok}</span>`;
    if (/^[a-z_]\w*$/.test(tok) && _NEXAQL_KW.has(tok))
      return `<span style="color:#a78bfa;font-weight:600">${tok}</span>`;
    if (/^[a-z_]\w*$/.test(tok) && _NEXAQL_BOOL.has(tok))
      return `<span style="color:#a78bfa">${tok}</span>`;
    // field key (matched by lookahead for colon)
    if (/^[a-z_]\w*$/.test(tok))
      return `<span style="color:var(--success)">${tok}</span>`;
    if (/^\d/.test(tok))
      return `<span style="color:#22d3ee">${tok}</span>`;
    return tok;
  });
}

const _SQL_KW = new Set([
  'SELECT','FROM','WHERE','JOIN','LEFT','INNER','RIGHT','OUTER','CROSS',
  'GROUP','ORDER','BY','HAVING','LIMIT','OFFSET','ON','AND','OR','NOT',
  'IN','IS','NULL','AS','DISTINCT','COUNT','SUM','AVG','MIN','MAX',
  'EXISTS','INTERVAL','CURRENT_DATE','TRUE','FALSE','CASE','WHEN','THEN',
  'ELSE','END','BETWEEN','LIKE','ILIKE','UNION','ALL','INSERT','UPDATE',
  'DELETE','SET','VALUES','INTO','CREATE','TABLE','INDEX','ALTER','DROP',
  'DESC','ASC','COALESCE','CAST','OVER','PARTITION','ROWS','RANGE',
]);

const _SQL_TOKEN =
  /'[^']*'/g.source + '|' +          // strings
  /\b\d+(?:\.\d+)?\b/g.source + '|' + // numbers
  /\b[A-Za-z_]\w*\b/g.source + '|' + // words
  /[a-z]\w*\./g.source;              // table aliases (word.)
const _SQL_RE = new RegExp(_SQL_TOKEN, 'g');

function highlightSQL(sql: string): string {
  return _esc(sql).replace(_SQL_RE, (tok) => {
    if (tok.startsWith("'"))
      return `<span style="color:#fb923c">${tok}</span>`;
    if (/^\d/.test(tok))
      return `<span style="color:#22d3ee">${tok}</span>`;
    if (tok.endsWith('.'))
      return `<span style="color:var(--text-muted)">${tok}</span>`;
    if (_SQL_KW.has(tok.toUpperCase()))
      return `<span style="color:#a78bfa;font-weight:600">${tok}</span>`;
    return tok;
  });
}

// Simple JSON syntax highlighting
function highlightJSON(json: string): string {
  return _esc(json)
    .replace(/"([^"]+)"(?=\s*:)/g, '<span style="color:#22d3ee">"$1"</span>') // keys
    .replace(/:\s*"([^"]*)"/g, ': <span style="color:#fb923c">"$1"</span>') // string values
    .replace(/:\s*(\d+(?:\.\d+)?)/g, ': <span style="color:#a78bfa">$1</span>') // numbers
    .replace(/:\s*(true|false|null)/g, ': <span style="color:#a78bfa;font-weight:600">$1</span>'); // booleans
}

function highlightURL(url: string): string {
  const safe = _esc(url);
  return safe.replace(/^(GET|POST)\s+(.+)$/, (_, method, rest) => {
    const qIdx = rest.indexOf('?');
    if (qIdx === -1) {
      return `<span style="color:#a78bfa;font-weight:600">${method}</span> <span style="color:var(--accent)">${rest}</span>`;
    }
    const path = rest.slice(0, qIdx);
    const params = rest
      .slice(qIdx + 1)
      .split('&amp;')
      .map((p: string) => {
        const [k, v] = p.split('=');
        return `<span style="color:#22d3ee">${k}</span>=<span style="color:#fb923c">${v ?? ''}</span>`;
      })
      .join(`<span style="color:var(--text-secondary)">&amp;</span>`);
    return `<span style="color:#a78bfa;font-weight:600">${method}</span> <span style="color:var(--accent)">${path}</span><span style="color:var(--text-secondary)">?</span>${params}`;
  });
}

const ADAPTER_LABELS: Record<string, { label: string; colorVar: string }> = {
  postgresql: { label: 'PostgreSQL', colorVar: 'var(--success)' },
  rest: { label: 'REST API', colorVar: '#a78bfa' },
  mysql: { label: 'MySQL', colorVar: '#f97316' },
  mongodb: { label: 'MongoDB', colorVar: 'var(--success)' },
};

const MODE_LABELS: Record<string, { label: string; color: string }> = {
  intent: { label: 'Intent', color: 'var(--success)' },
  raw: { label: 'Raw', color: '#f97316' },
  raw_fallback: { label: 'Raw (fallback)', color: '#f97316' },
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

// ── Collapsible section ──────────────────────────────────────────────────────

function Section({
  title,
  badge,
  badgeColor,
  copyText,
  defaultOpen = true,
  children,
}: {
  title: string;
  badge?: string;
  badgeColor?: string;
  copyText?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div>
      <div
        className="flex shrink-0 items-center justify-between border-b px-3 py-2 cursor-pointer select-none"
        style={{ borderColor: 'var(--border)' }}
        onClick={() => setOpen((o) => !o)}
      >
        <div className="flex items-center gap-2">
          <span
            className="text-[10px] transition-transform"
            style={{ color: 'var(--text-secondary)', display: 'inline-block', transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}
          >
            ▶
          </span>
          <span
            className="font-semibold text-[10px] uppercase tracking-widest"
            style={{ color: 'var(--text-secondary)' }}
          >
            {title}
          </span>
          {badge && (
            <span
              className="rounded border px-1.5 py-0.5 text-[9px]"
              style={{
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-elevated)',
                color: badgeColor ?? 'var(--accent)',
              }}
            >
              {badge}
            </span>
          )}
        </div>
        {copyText && open && (
          <div onClick={(e) => e.stopPropagation()}>
            <CopyButton text={copyText} />
          </div>
        )}
      </div>
      {open && children}
    </div>
  );
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function ChatQueryPanel({ nexaqlQuery, queryPreview, adapterType, intent, generationMode }: Props) {
  const adapterMeta: { label: string; colorVar: string } = (adapterType ? ADAPTER_LABELS[adapterType] : undefined) ?? {
    label: adapterType ?? 'Query',
    colorVar: 'var(--text-secondary)',
  };

  const modeMeta = generationMode ? MODE_LABELS[generationMode] ?? { label: generationMode, color: 'var(--text-secondary)' } : null;

  const isREST = adapterType === 'rest';

  const nexaqlHighlighted = nexaqlQuery ? highlightNexaQL(nexaqlQuery) : null;
  const previewHighlighted = queryPreview ? (isREST ? highlightURL(queryPreview) : highlightSQL(queryPreview)) : null;
  const intentJSON = intent ? JSON.stringify(intent, null, 2) : null;
  const intentHighlighted = intentJSON ? highlightJSON(intentJSON) : null;

  return (
    <div className="flex h-full flex-col overflow-hidden" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <div className="flex-1 overflow-y-auto">

        {/* ── LLM Intent JSON (Option B only) ── */}
        {intentHighlighted && (
          <Section
            title="LLM Intent"
            badge={modeMeta?.label}
            badgeColor={modeMeta?.color}
            copyText={intentJSON!}
            defaultOpen={true}
          >
            <div className="overflow-auto p-3" style={{ maxHeight: '35%' }}>
              <pre
                className="whitespace-pre-wrap font-mono text-[11px] leading-relaxed"
                style={{ color: 'var(--text-primary)' }}
                dangerouslySetInnerHTML={{ __html: intentHighlighted }}
              />
            </div>
          </Section>
        )}

        {/* ── Divider ── */}
        {intentHighlighted && <div className="shrink-0 border-t" style={{ borderColor: 'var(--border)' }} />}

        {/* ── NexaQL Query ── */}
        <Section
          title="NexaQL Query"
          badge={!intentHighlighted ? (modeMeta?.label ?? 'generated') : 'generated'}
          badgeColor={!intentHighlighted ? modeMeta?.color : 'var(--accent)'}
          copyText={nexaqlQuery ?? undefined}
          defaultOpen={true}
        >
          <div className="overflow-auto p-3" style={{ maxHeight: '35%' }}>
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
        </Section>

        {/* ── Divider ── */}
        <div className="shrink-0 border-t" style={{ borderColor: 'var(--border)' }} />

        {/* ── Translated preview (SQL / REST) ── */}
        <Section
          title={isREST ? 'Request' : 'SQL'}
          badge={adapterType ? adapterMeta.label : undefined}
          badgeColor={adapterMeta.colorVar}
          copyText={queryPreview ?? undefined}
          defaultOpen={true}
        >
          <div className="overflow-auto p-3">
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
        </Section>
      </div>
    </div>
  );
}
