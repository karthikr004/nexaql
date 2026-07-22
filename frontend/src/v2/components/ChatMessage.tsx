import Markdown from 'react-markdown';
import type { ChatTurn } from '../../types';
import ProcessingStep from './ProcessingStep';
import ChatResultTable from './ChatResultTable';

function FormattedMarkdown({ text }: { text: string }) {
  return (
    <div style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--v2-text-primary)' }}>
      <Markdown
        components={{
          h1: ({ children }) => (
            <h1 style={{ fontSize: 18, fontWeight: 600, marginTop: 16, marginBottom: 8, color: 'var(--v2-text-primary)' }}>{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 style={{ fontSize: 16, fontWeight: 600, marginTop: 14, marginBottom: 6, color: 'var(--v2-text-primary)' }}>{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 style={{ fontSize: 14, fontWeight: 600, marginTop: 12, marginBottom: 4, color: 'var(--v2-text-primary)' }}>{children}</h3>
          ),
          p: ({ children }) => (
            <p style={{ marginBottom: 8 }}>{children}</p>
          ),
          strong: ({ children }) => (
            <strong style={{ fontWeight: 600, color: 'var(--v2-text-primary)' }}>{children}</strong>
          ),
          ul: ({ children }) => (
            <ul style={{ paddingLeft: 20, marginBottom: 8 }}>{children}</ul>
          ),
          ol: ({ children }) => (
            <ol style={{ paddingLeft: 20, marginBottom: 8 }}>{children}</ol>
          ),
          li: ({ children }) => (
            <li style={{ marginBottom: 2 }}>{children}</li>
          ),
          code: ({ className, children }) => {
            const isBlock = className?.includes('language-');
            if (isBlock) {
              return (
                <pre className="v2-code-block" style={{ margin: '8px 0' }}>
                  {String(children).trim()}
                </pre>
              );
            }
            return (
              <code
                style={{
                  fontFamily: 'var(--v2-font-mono)',
                  fontSize: 12,
                  padding: '1px 5px',
                  borderRadius: 'var(--v2-radius-sm)',
                  background: 'var(--v2-bg-code)',
                  color: 'var(--v2-accent-text)',
                }}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => <>{children}</>,
        }}
      >
        {text}
      </Markdown>
    </div>
  );
}

function UserMessage({ text }: { text: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
      <div
        style={{
          maxWidth: '75%',
          padding: '10px 14px',
          borderRadius: 'var(--v2-radius-lg)',
          background: 'var(--v2-accent)',
          color: 'var(--v2-text-inverse)',
          fontSize: 14,
          lineHeight: 1.6,
        }}
      >
        {text}
      </div>
    </div>
  );
}

function LoadingIndicator() {
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <div
        style={{
          width: 28,
          height: 28,
          borderRadius: 'var(--v2-radius-full)',
          background: 'var(--v2-accent-subtle)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--v2-accent)" strokeWidth="2">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
        </svg>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 4 }}>
        <div
          style={{
            width: 14,
            height: 14,
            borderRadius: '50%',
            border: '2px solid var(--v2-accent)',
            borderTopColor: 'transparent',
            animation: 'v2-spin 0.8s linear infinite',
          }}
        />
        <span style={{ fontSize: 13, color: 'var(--v2-text-tertiary)' }}>Thinking...</span>
      </div>
    </div>
  );
}

function AssistantMessage({ turn }: { turn: ChatTurn }) {
  const hasProcessingSteps = turn.intent || turn.nexaqlQuery || turn.queryPreview;

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <div
        style={{
          width: 28,
          height: 28,
          borderRadius: 'var(--v2-radius-full)',
          background: 'var(--v2-accent-subtle)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--v2-accent)" strokeWidth="2">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
        </svg>
      </div>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {/* Processing steps (collapsible) */}
        {hasProcessingSteps && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {turn.intent && (
              <ProcessingStep label="Intent analysis" icon="🎯" badge={turn.generationMode || undefined} badgeVariant="purple">
                <pre className="v2-code-block" style={{ fontSize: 12 }}>
                  {JSON.stringify(turn.intent, null, 2)}
                </pre>
              </ProcessingStep>
            )}
            {turn.nexaqlQuery && (
              <ProcessingStep label="Generated query" icon="⚡">
                <pre className="v2-code-block" style={{ fontSize: 12 }}>
                  {turn.nexaqlQuery}
                </pre>
              </ProcessingStep>
            )}
            {turn.queryPreview && (
              <ProcessingStep label="SQL preview" icon="🗄️" badge={turn.adapterType || undefined} badgeVariant="teal">
                <pre className="v2-code-block" style={{ fontSize: 12 }}>
                  {turn.queryPreview}
                </pre>
              </ProcessingStep>
            )}
          </div>
        )}

        {/* Summary */}
        {turn.summary && <FormattedMarkdown text={turn.summary} />}

        {/* Error */}
        {turn.error && (
          <div
            style={{
              padding: '10px 14px',
              borderRadius: 'var(--v2-radius-md)',
              background: 'var(--v2-red-50)',
              border: '1px solid var(--v2-red-100)',
              color: 'var(--v2-red-600)',
              fontSize: 13,
              fontFamily: 'var(--v2-font-mono)',
            }}
          >
            {turn.error}
          </div>
        )}

        {/* Results table */}
        {!turn.error && turn.rows.length > 0 && (
          <ChatResultTable rows={turn.rows} columns={turn.columns} rowCount={turn.rowCount} />
        )}

        {/* Duration */}
        {turn.durationMs != null && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--v2-text-tertiary)' }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            <span>
              {turn.durationMs >= 1000
                ? `${(turn.durationMs / 1000).toFixed(1)}s`
                : `${turn.durationMs}ms`}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ChatMessage({ turn }: { turn: ChatTurn }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <UserMessage text={turn.question} />
      {turn.loading ? <LoadingIndicator /> : <AssistantMessage turn={turn} />}
    </div>
  );
}
