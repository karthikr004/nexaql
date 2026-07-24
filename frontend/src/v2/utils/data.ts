import type { NodeShape, ColumnMeta } from '../../types';

export function nestRows(rows: Record<string, unknown>[], shape: NodeShape): Record<string, unknown>[] {
  if (rows.length === 0) return [];
  const keyColumns = [...shape.columnAliases, ...shape.aggregationAliases];
  const groups = new Map<string, Record<string, unknown>[]>();

  for (const row of rows) {
    const key = keyColumns.map((c) => String(row[c] ?? '\x00')).join('\x01');
    const existing = groups.get(key);
    if (existing) existing.push(row);
    else groups.set(key, [row]);
  }

  return Array.from(groups.values()).map((groupRows) => {
    const first = groupRows[0]!;
    const result: Record<string, unknown> = {};
    for (const alias of shape.columnAliases) {
      const fieldName = alias.includes('__') ? alias.slice(alias.indexOf('__') + 2) : alias;
      result[fieldName] = first[alias];
    }
    for (const agg of shape.aggregationAliases) {
      result[agg] = first[agg];
    }
    for (const child of shape.children) {
      const childKey = child.edgeName ?? child.node;
      result[childKey] = nestRows(groupRows, child);
    }
    return result;
  });
}

export function downloadCSV(rows: Record<string, unknown>[], columns: ColumnMeta[]): void {
  const header = columns.map((c) => c.name.replace(/__/g, '.')).join(',');
  const body = rows.map((row) =>
    columns.map((c) => {
      const v = row[c.name];
      const s = v === null || v === undefined ? '' : String(v);
      return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s;
    }).join(','),
  ).join('\n');
  const blob = new Blob([`${header}\n${body}`], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  Object.assign(document.createElement('a'), { href: url, download: 'nexaql-results.csv' }).click();
  URL.revokeObjectURL(url);
}

export function cellValue(value: unknown): string {
  if (value === null || value === undefined) return 'NULL';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function cellColor(type: string, value: unknown): string {
  if (value === null || value === undefined) return 'var(--v2-text-tertiary)';
  if (type === 'boolean') return '#c084fc';
  if (['integer', 'bigint', 'smallint', 'numeric', 'float4', 'float8'].includes(type)) return 'var(--v2-teal-500)';
  return 'var(--v2-text-primary)';
}
