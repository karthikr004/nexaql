import { useState, useCallback, useRef } from 'react';

interface CsvUploadFormProps {
  onUploaded: () => void;
  onCancel: () => void;
  onToast: (t: { message: string; type: 'success' | 'error' }) => void;
}

interface UploadResult {
  connector_name: string;
  table_name: string;
  row_count: number;
  column_count: number;
  columns: { name: string; type: string; nullable: boolean }[];
}

export default function CsvUploadForm({ onUploaded, onCancel, onToast }: CsvUploadFormProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((f: File) => {
    const ext = f.name.split('.').pop()?.toLowerCase();
    if (!ext || !['csv', 'tsv', 'txt'].includes(ext)) {
      onToast({ message: 'Only CSV, TSV, and TXT files are supported', type: 'error' });
      return;
    }
    setFile(f);
    setResult(null);
  }, [onToast]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, [handleFile]);

  const handleUpload = useCallback(async () => {
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch('/api/connectors/upload', {
        method: 'POST',
        body: formData,
        credentials: 'include',
      });

      const body = await res.json();
      if (res.ok) {
        setResult({
          connector_name: body.connector_name,
          table_name: body.table_name,
          row_count: body.row_count,
          column_count: body.column_count,
          columns: body.columns,
        });
        onToast({
          message: `"${file.name}" uploaded — ${body.row_count} rows, ${body.column_count} columns`,
          type: 'success',
        });
        onUploaded();
      } else {
        onToast({ message: body.error || 'Upload failed', type: 'error' });
      }
    } catch (err) {
      onToast({ message: `Upload error: ${err}`, type: 'error' });
    } finally {
      setUploading(false);
    }
  }, [file, onUploaded, onToast]);

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="v2-card" style={{ padding: 24, marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <h2 className="v2-heading-md">Upload CSV / TSV</h2>
        <button type="button" className="v2-btn v2-btn-ghost v2-btn-sm" onClick={onCancel}>Cancel</button>
      </div>

      {!result ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Drop zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            style={{
              border: `2px dashed ${dragOver ? 'var(--v2-accent)' : 'var(--v2-border)'}`,
              borderRadius: 'var(--v2-radius-md)',
              padding: '32px 24px',
              textAlign: 'center',
              cursor: 'pointer',
              background: dragOver ? 'var(--v2-purple-50)' : 'transparent',
              transition: 'all 0.15s',
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.tsv,.txt"
              style={{ display: 'none' }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFile(f);
              }}
            />
            <svg
              width="32" height="32" viewBox="0 0 24 24" fill="none"
              stroke="var(--v2-text-tertiary)" strokeWidth="1.5"
              strokeLinecap="round" strokeLinejoin="round"
              style={{ margin: '0 auto 8px' }}
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <p style={{ fontSize: 13, color: 'var(--v2-text-secondary)', marginBottom: 4 }}>
              {file ? file.name : 'Drop a CSV or TSV file here, or click to browse'}
            </p>
            {file && (
              <p style={{ fontSize: 12, color: 'var(--v2-text-tertiary)' }}>
                {formatSize(file.size)}
              </p>
            )}
          </div>

          {file && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div
                style={{
                  flex: 1,
                  padding: '8px 12px',
                  borderRadius: 'var(--v2-radius-sm)',
                  background: 'var(--v2-bg-hover)',
                  fontSize: 13,
                  fontFamily: 'var(--v2-font-mono)',
                  color: 'var(--v2-text-primary)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--v2-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {file.name}
                </span>
                <span style={{ color: 'var(--v2-text-tertiary)', flexShrink: 0 }}>{formatSize(file.size)}</span>
              </div>
              <button
                type="button"
                className="v2-btn v2-btn-primary"
                onClick={handleUpload}
                disabled={uploading}
                style={{ opacity: uploading ? 0.5 : 1, flexShrink: 0 }}
              >
                {uploading ? 'Uploading...' : 'Upload & Process'}
              </button>
            </div>
          )}

          <p style={{ fontSize: 11, color: 'var(--v2-text-tertiary)' }}>
            Supported: .csv, .tsv, .txt — max 100 MB. Data is loaded into DuckDB for querying.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{
            padding: 12,
            borderRadius: 'var(--v2-radius-md)',
            background: 'var(--v2-teal-50)',
            border: '1px solid var(--v2-teal-500)',
            fontSize: 13,
            color: 'var(--v2-teal-700)',
          }}>
            File processed successfully — connector <strong>{result.connector_name}</strong> created
          </div>

          <div style={{ display: 'flex', gap: 16 }}>
            <Stat label="Rows" value={result.row_count.toLocaleString()} />
            <Stat label="Columns" value={String(result.column_count)} />
            <Stat label="Table" value={result.table_name} mono />
          </div>

          <div style={{
            borderRadius: 'var(--v2-radius-md)',
            border: '1px solid var(--v2-border)',
            maxHeight: 200,
            overflowY: 'auto',
          }}>
            {result.columns.map((col) => (
              <div
                key={col.name}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '4px 12px',
                  borderBottom: '1px solid var(--v2-border-light)',
                  fontSize: 12,
                }}
              >
                <span style={{ fontFamily: 'var(--v2-font-mono)', color: 'var(--v2-text-primary)' }}>
                  {col.name}
                </span>
                <span className="v2-badge v2-badge-gray" style={{ fontSize: 10 }}>
                  {col.type}
                </span>
              </div>
            ))}
          </div>

          <p style={{ fontSize: 11, color: 'var(--v2-text-tertiary)' }}>
            Next: go to Domains and generate an ontology from this connector to start querying.
          </p>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{
      flex: 1,
      padding: '8px 12px',
      borderRadius: 'var(--v2-radius-sm)',
      background: 'var(--v2-bg-hover)',
    }}>
      <div style={{ fontSize: 11, color: 'var(--v2-text-tertiary)', marginBottom: 2 }}>{label}</div>
      <div style={{
        fontSize: 14,
        fontWeight: 600,
        color: 'var(--v2-text-primary)',
        fontFamily: mono ? 'var(--v2-font-mono)' : 'inherit',
      }}>
        {value}
      </div>
    </div>
  );
}
