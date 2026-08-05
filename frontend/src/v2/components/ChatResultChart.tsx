import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import type { ColumnMeta } from '../../types';

const COLORS = ['#8B5CF6', '#6366F1', '#EC4899', '#F59E0B', '#10B981', '#3B82F6'];

interface Visualization {
  chart_type: 'bar' | 'line' | 'pie' | 'stat' | 'table';
  x_field?: string;
  y_fields?: string[];
  title?: string;
}

interface Props {
  rows: Record<string, unknown>[];
  columns: ColumnMeta[];
  visualization: Visualization;
}

function detectFallbackChart(
  rows: Record<string, unknown>[],
  columns: ColumnMeta[],
): Visualization | null {
  if (!rows.length || !columns.length) return null;

  const stringCols = columns.filter((c) => c.type === 'string' || c.type === 'text');
  const numericCols = columns.filter((c) =>
    ['integer', 'float', 'number', 'decimal', 'bigint', 'numeric', 'double'].includes(c.type.toLowerCase()),
  );

  const firstNumeric = numericCols[0];
  const firstString = stringCols[0];

  if (rows.length === 1 && firstNumeric && columns.length <= 2) {
    return { chart_type: 'stat', y_fields: [firstNumeric.name], title: firstNumeric.name };
  }

  if (firstString && firstNumeric) {
    if (rows.length <= 6) {
      return { chart_type: 'pie', x_field: firstString.name, y_fields: [firstNumeric.name] };
    }
    if (rows.length <= 20) {
      return { chart_type: 'bar', x_field: firstString.name, y_fields: [firstNumeric.name] };
    }
  }

  return null;
}

function StatCard({ rows, visualization }: { rows: Record<string, unknown>[]; visualization: Visualization }) {
  const field = visualization.y_fields?.[0];
  const value = field && rows[0] ? rows[0][field] : null;

  return (
    <div style={{ textAlign: 'center', padding: '24px 16px' }}>
      <div style={{ fontSize: 40, fontWeight: 700, color: '#8B5CF6', fontFamily: 'var(--v2-font-mono)' }}>
        {value != null ? Number(value).toLocaleString() : '—'}
      </div>
      {visualization.title && (
        <div style={{ fontSize: 13, color: 'var(--v2-text-tertiary)', marginTop: 8 }}>
          {visualization.title}
        </div>
      )}
    </div>
  );
}

function ChartTitle({ title }: { title?: string }) {
  if (!title) return null;
  return (
    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--v2-text-secondary)', padding: '10px 14px 0' }}>
      {title}
    </div>
  );
}

export default function ChatResultChart({ rows, columns, visualization: vizProp }: Props) {
  const viz = vizProp.chart_type === 'table'
    ? detectFallbackChart(rows, columns)
    : vizProp;

  if (!viz || viz.chart_type === 'table') return null;

  const xField = viz.x_field ?? columns[0]?.name ?? '';
  const yFields = viz.y_fields?.length ? viz.y_fields : [columns[1]?.name ?? ''];

  const data = rows.map((row) => {
    const point: Record<string, unknown> = { [xField]: row[xField] };
    for (const yf of yFields) {
      point[yf] = typeof row[yf] === 'number' ? row[yf] : Number(row[yf]) || 0;
    }
    return point;
  });

  const stripTime = (value: unknown) => {
    const s = String(value);
    return /^\d{4}-\d{2}-\d{2}[T ]/.test(s) ? s.slice(0, 10) : s;
  };

  const formatTooltip = (value: unknown, name: unknown) => [stripTime(value), stripTime(name)];
  const formatTooltipLabel = (label: unknown) => stripTime(label);

  const textColor = 'var(--v2-text-tertiary)';
  const gridColor = 'var(--v2-border)';

  if (viz.chart_type === 'stat') {
    return (
      <div className="v2-card" style={{ overflow: 'hidden' }}>
        <StatCard rows={rows} visualization={viz} />
      </div>
    );
  }

  if (viz.chart_type === 'pie') {
    return (
      <div className="v2-card" style={{ overflow: 'hidden' }}>
        <ChartTitle title={viz.title} />
        <ResponsiveContainer width="100%" height={280}>
          <PieChart>
            <Pie
              data={data}
              dataKey={yFields[0]}
              nameKey={xField}
              cx="50%"
              cy="50%"
              outerRadius={90}
              label={(props) => `${stripTime(props.name ?? '')} ${((props.percent ?? 0) * 100).toFixed(0)}%`}
              labelLine={false}
              fontSize={11}
            >
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip formatter={formatTooltip} labelFormatter={formatTooltipLabel} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (viz.chart_type === 'line') {
    return (
      <div className="v2-card" style={{ overflow: 'hidden' }}>
        <ChartTitle title={viz.title} />
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data} margin={{ top: 16, right: 24, bottom: 4, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
            <XAxis dataKey={xField} tickFormatter={stripTime} tick={{ fontSize: 11, fill: textColor }} />
            <YAxis tick={{ fontSize: 11, fill: textColor }} />
            <Tooltip formatter={formatTooltip} labelFormatter={formatTooltipLabel} />
            {yFields.map((yf, i) => (
              <Line
                key={yf}
                type="monotone"
                dataKey={yf}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            ))}
            {yFields.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  // Default: bar chart
  return (
    <div className="v2-card" style={{ overflow: 'hidden' }}>
      <ChartTitle title={viz.title} />
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 16, right: 24, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
          <XAxis dataKey={xField} tickFormatter={stripTime} tick={{ fontSize: 11, fill: textColor }} />
          <YAxis tick={{ fontSize: 11, fill: textColor }} />
          <Tooltip formatter={formatTooltip} labelFormatter={formatTooltipLabel} />
          {yFields.map((yf, i) => (
            <Bar key={yf} dataKey={yf} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} />
          ))}
          {yFields.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
