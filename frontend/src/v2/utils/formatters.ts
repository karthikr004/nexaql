const SQL_KEYWORDS = [
  'SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT JOIN', 'INNER JOIN',
  'GROUP BY', 'ORDER BY', 'HAVING', 'LIMIT', 'OFFSET', 'ON',
  'AND', 'OR', 'NOT', 'IN', 'IS', 'NULL', 'AS', 'DISTINCT',
  'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'EXISTS', 'INTERVAL',
  'CURRENT_DATE', 'TRUE', 'FALSE',
];

const JSON_COLORS = {
  key: '#7dd3fc',
  string: '#86efac',
  number: '#fbbf24',
  bool: '#c084fc',
  null: '#64748b',
  punct: '#94a3b8',
};

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function highlightSQL(sql: string): string {
  let out = escapeHtml(sql);
  out = out.replace(/'[^']*'/g, (m) => `\x00STR${m}\x00END`);
  for (const kw of SQL_KEYWORDS) {
    out = out.replace(new RegExp(`\\b${kw}\\b`, 'g'), `\x00KW${kw}\x00END`);
  }
  out = out.replace(/\b(\d+)\b/g, `\x00NUM$1\x00END`);
  out = out.replace(/\b([a-z][a-z0-9]*)\./g, `\x00AL$1\x00END.`);
  out = out.replace(/\x00KW(.*?)\x00END/g, '<span style="color:#a78bfa;font-weight:600">$1</span>');
  out = out.replace(/\x00STR(.*?)\x00END/g, '<span style="color:#fb923c">$1</span>');
  out = out.replace(/\x00NUM(.*?)\x00END/g, '<span style="color:#22d3ee">$1</span>');
  out = out.replace(/\x00AL(.*?)\x00END/g, '<span style="color:var(--v2-text-tertiary)">$1</span>');
  return out;
}

export function highlightURL(url: string): string {
  let out = escapeHtml(url);
  out = out.replace(/^(GET|POST)\s+(.+)$/, (_, method: string, rest: string) => {
    const qIdx = rest.indexOf('?');
    if (qIdx === -1) {
      return `<span style="color:var(--v2-purple-400);font-weight:600">${method}</span> <span style="color:var(--v2-accent)">${rest}</span>`;
    }
    const path = rest.slice(0, qIdx);
    const params = rest.slice(qIdx + 1).split('&amp;').map((p: string) => {
      const [k, v] = p.split('=');
      return `<span style="color:#22d3ee">${k}</span>=<span style="color:#fb923c">${v ?? ''}</span>`;
    }).join(`<span style="color:var(--v2-text-secondary)">&amp;</span>`);
    return `<span style="color:var(--v2-purple-400);font-weight:600">${method}</span> <span style="color:var(--v2-accent)">${path}</span><span style="color:var(--v2-text-secondary)">?</span>${params}`;
  });
  return out;
}

export function highlightJson(json: string): string {
  const escaped = escapeHtml(json);
  const tokenized = escaped.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
    (match) => {
      if (/^"/.test(match)) {
        if (/:$/.test(match)) {
          const key = match.slice(0, -1);
          return `<span style="color:${JSON_COLORS.key}">${key}</span><span style="color:${JSON_COLORS.punct}">:</span>`;
        }
        return `<span style="color:${JSON_COLORS.string}">${match}</span>`;
      }
      if (/true|false/.test(match)) return `<span style="color:${JSON_COLORS.bool}">${match}</span>`;
      if (/null/.test(match)) return `<span style="color:${JSON_COLORS.null}">${match}</span>`;
      return `<span style="color:${JSON_COLORS.number}">${match}</span>`;
    },
  );
  return tokenized.replace(/(?<=>|^)([^<]*)(?=<|$)/g, (chunk) =>
    chunk.replace(/([{}[\],])/g, `<span style="color:${JSON_COLORS.punct}">$1</span>`),
  );
}
