import { useState } from 'react';
import { highlightSQL, highlightURL } from '../utils/formatters';

const ADAPTER_LABELS: Record<string, { label: string; color: string }> = {
  postgresql: { label: 'PostgreSQL', color: 'var(--v2-teal-500)' },
  mysql: { label: 'MySQL', color: '#f97316' },
  mongodb: { label: 'MongoDB', color: 'var(--v2-teal-500)' },
  rest: { label: 'REST API', color: 'var(--v2-purple-400)' },
};

interface SQLPreviewProps {
  queryPreview: string | null;
  adapterType: string | null;
  isLoading: boolean;
  onClose: () => void;
}

export default function SQLPreview({ queryPreview, adapterType, isLoading, onClose }: SQLPreviewProps) {
  const [copied, setCopied] = useState(false);

  const isREST = adapterType === 'rest';
  const meta = adapterType ? (ADAPTER_LABELS[adapterType] ?? { label: adapterType, color: 'var(--v2-teal-500)' }) : { label: 'SQL', color: 'var(--v2-teal-500)' };
  const highlighted = queryPreview ? (isREST ? highlightURL(queryPreview) : highlightSQL(queryPreview)) : null;

  const copy = () => {
    if (!queryPreview) return;
    navigator.clipboard.writeText(queryPreview).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div style={{
      borderTop: '1px solid var(--v2-border)',
      background: 'var(--v2-bg-surface)',
      maxHeight: 200,
      display: 'flex',
      flexDirection: 'column',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '6px 16px', borderBottom: '1px solid var(--v2-border)', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="v2-label">{isREST ? 'Request Preview' : 'SQL Preview'}</span>
          <span className="v2-badge v2-badge-gray" style={{ fontSize: 10, color: meta.color }}>{meta.label}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {queryPreview && (
            <button type="button" onClick={copy} className="v2-btn v2-btn-ghost v2-btn-sm" style={{ fontSize: 10, color: copied ? 'var(--v2-teal-500)' : undefined }}>
              {copied ? 'Copied' : 'Copy'}
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--v2-text-tertiary)', padding: '2px', display: 'flex' }}
            title="Close SQL Preview"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 16px' }}>
        {isLoading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--v2-text-tertiary)' }}>
            <div style={{
              width: 12, height: 12, borderRadius: '50%',
              border: '2px solid var(--v2-accent)', borderTopColor: 'transparent',
              animation: 'v2-spin 0.8s linear infinite',
            }} />
            Translating...
          </div>
        )}
        {!isLoading && !queryPreview && (
          <div style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12, color: 'var(--v2-text-tertiary)' }}>
            {isREST ? 'Write a REST query to see the request' : 'Write a query to see the generated SQL'}
          </div>
        )}
        {!isLoading && highlighted && (
          <pre
            style={{ fontFamily: 'var(--v2-font-mono)', fontSize: 12, lineHeight: 1.5, whiteSpace: 'pre-wrap', margin: 0, color: 'var(--v2-text-primary)' }}
            dangerouslySetInnerHTML={{ __html: highlighted }}
          />
        )}
      </div>
    </div>
  );
}
