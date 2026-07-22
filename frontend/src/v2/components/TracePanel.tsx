import type { ChatTurn } from '../../types';

interface Props {
  turn: ChatTurn;
  onClose: () => void;
}

function TraceSection({ title, icon, badge, badgeVariant, children }: {
  title: string;
  icon: string;
  badge?: string | null;
  badgeVariant?: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 14 }}>{icon}</span>
        <span className="v2-heading-sm">{title}</span>
        {badge && (
          <span className={`v2-badge v2-badge-${badgeVariant || 'gray'}`} style={{ fontSize: 10 }}>{badge}</span>
        )}
      </div>
      {children}
    </div>
  );
}

export default function TracePanel({ turn, onClose }: Props) {
  return (
    <div
      style={{
        width: 420,
        minWidth: 420,
        height: '100%',
        borderLeft: '1px solid var(--v2-border)',
        background: 'var(--v2-bg-app)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '14px 16px',
          borderBottom: '1px solid var(--v2-border)',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--v2-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </svg>
          <span className="v2-heading-sm">Query trace</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="v2-icon-btn"
          style={{ width: 28, height: 28 }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Question */}
        <TraceSection title="Question" icon="💬">
          <div
            style={{
              padding: '10px 12px',
              borderRadius: 'var(--v2-radius-md)',
              background: 'var(--v2-bg-surface)',
              border: '1px solid var(--v2-border-light)',
              fontSize: 13,
              color: 'var(--v2-text-primary)',
              lineHeight: 1.6,
            }}
          >
            {turn.question}
          </div>
        </TraceSection>

        {/* Intent */}
        {turn.intent && (
          <TraceSection title="Intent analysis" icon="🎯" badge={turn.generationMode} badgeVariant="purple">
            <pre className="v2-code-block" style={{ fontSize: 12 }}>
              {JSON.stringify(turn.intent, null, 2)}
            </pre>
          </TraceSection>
        )}

        {/* NexaQL query */}
        {turn.nexaqlQuery && (
          <TraceSection title="NexaQL query" icon="⚡">
            <pre className="v2-code-block" style={{ fontSize: 12 }}>
              {turn.nexaqlQuery}
            </pre>
          </TraceSection>
        )}

        {/* SQL preview */}
        {turn.queryPreview && (
          <TraceSection title="SQL query" icon="🗄️" badge={turn.adapterType} badgeVariant="teal">
            <pre className="v2-code-block" style={{ fontSize: 12 }}>
              {turn.queryPreview}
            </pre>
          </TraceSection>
        )}

        {/* Duration */}
        {turn.durationMs != null && (
          <TraceSection title="Performance" icon="⏱️">
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 12px',
                borderRadius: 'var(--v2-radius-md)',
                background: 'var(--v2-bg-surface)',
                border: '1px solid var(--v2-border-light)',
              }}
            >
              <span style={{ fontSize: 20, fontWeight: 600, color: 'var(--v2-text-primary)', fontFamily: 'var(--v2-font-mono)' }}>
                {turn.durationMs >= 1000
                  ? `${(turn.durationMs / 1000).toFixed(1)}s`
                  : `${turn.durationMs}ms`}
              </span>
              <span className="v2-caption">total latency</span>
            </div>
          </TraceSection>
        )}

        {/* Row count */}
        {turn.rowCount > 0 && (
          <TraceSection title="Results" icon="📊">
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 12px',
                borderRadius: 'var(--v2-radius-md)',
                background: 'var(--v2-bg-surface)',
                border: '1px solid var(--v2-border-light)',
              }}
            >
              <span style={{ fontSize: 20, fontWeight: 600, color: 'var(--v2-text-primary)', fontFamily: 'var(--v2-font-mono)' }}>
                {turn.rowCount}
              </span>
              <span className="v2-caption">row{turn.rowCount !== 1 ? 's' : ''} returned</span>
            </div>
          </TraceSection>
        )}
      </div>
    </div>
  );
}
