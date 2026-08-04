import { useState, useCallback, useEffect } from 'react';

interface CloudConnector {
  id: number;
  name: string;
  type: string;
}

interface CloudAccount {
  id: number;
  connector_id: number;
  provider: string;
  email: string;
  display_name: string | null;
}

interface CloudFile {
  id: string;
  name: string;
  mime_type: string;
  size: number | null;
  modified_at: string | null;
  is_folder: boolean;
  parent_id: string | null;
}

interface ImportResult {
  connector_name: string;
  table_name: string;
  row_count: number;
  column_count: number;
  columns: { name: string; type: string; nullable: boolean }[];
  preview: Record<string, string | null>[];
  header_row: number;
  status: string;
}

interface CloudDrivePickerProps {
  onImported: (result: ImportResult) => void;
  onToast: (message: string, type: 'success' | 'error') => void;
}

interface BreadcrumbItem {
  id: string | null;
  name: string;
}

const CLOUD_DRIVE_TYPES = new Set(['google_drive', 'onedrive', 'dropbox']);

const PROVIDER_LABELS: Record<string, string> = {
  google_drive: 'Google Drive',
  onedrive: 'OneDrive',
  dropbox: 'Dropbox',
};

const MIME_LABELS: Record<string, string> = {
  'application/vnd.google-apps.spreadsheet': 'Google Sheet',
  'text/csv': 'CSV',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'XLSX',
  'text/tab-separated-values': 'TSV',
};

function formatFileSize(bytes: number | null): string {
  if (bytes == null) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function CloudDrivePicker({ onImported, onToast }: CloudDrivePickerProps) {
  const [connectors, setConnectors] = useState<CloudConnector[]>([]);
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAccount, setSelectedAccount] = useState<CloudAccount | null>(null);

  const [files, setFiles] = useState<CloudFile[]>([]);
  const [browsing, setBrowsing] = useState(false);
  const [breadcrumb, setBreadcrumb] = useState<BreadcrumbItem[]>([{ id: null, name: 'My Drive' }]);
  const [importing, setImporting] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [connRes, accRes] = await Promise.all([
        fetch('/api/connectors'),
        fetch('/api/cloud-drive/accounts'),
      ]);
      if (connRes.ok) {
        const data = await connRes.json();
        const cloudConns = (data.connectors ?? []).filter(
          (c: { type: string }) => CLOUD_DRIVE_TYPES.has(c.type)
        );
        setConnectors(cloudConns);
      }
      if (accRes.ok) {
        const data = await accRes.json();
        const accs: CloudAccount[] = data.accounts ?? [];
        setAccounts(accs);
        if (accs.length > 0 && !selectedAccount) {
          setSelectedAccount(accs[0] ?? null);
        }
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const browse = useCallback(async (accountId: number, folderId: string | null) => {
    setBrowsing(true);
    try {
      const params = folderId ? `?folder_id=${encodeURIComponent(folderId)}` : '';
      const res = await fetch(`/api/cloud-drive/browse/${accountId}${params}`);
      if (res.ok) {
        const data = await res.json();
        setFiles(data.files ?? []);
      } else {
        const body = await res.json();
        onToast(body.detail || 'Failed to browse files', 'error');
      }
    } catch (err) {
      onToast(`Browse error: ${err}`, 'error');
    } finally {
      setBrowsing(false);
    }
  }, [onToast]);

  useEffect(() => {
    if (selectedAccount) {
      const currentFolder = breadcrumb[breadcrumb.length - 1];
      if (currentFolder) browse(selectedAccount.id, currentFolder.id);
    }
  }, [selectedAccount, breadcrumb]);

  const handleConnect = useCallback(async (connectorId: number) => {
    setConnecting(true);
    try {
      const res = await fetch(`/api/cloud-drive/connect/${connectorId}`);
      if (!res.ok) {
        const body = await res.json();
        onToast(body.detail || 'Failed to start connection', 'error');
        setConnecting(false);
        return;
      }
      const data = await res.json();
      const popup = window.open(data.authorize_url, 'cloud-drive-auth', 'width=500,height=700');

      const handleMessage = (event: MessageEvent) => {
        if (event.origin !== window.location.origin) return;
        if (event.data?.type === 'cloud-drive-connected') {
          window.removeEventListener('message', handleMessage);
          setConnecting(false);
          onToast(`Connected ${event.data.email}`, 'success');
          fetchData();
        }
      };
      window.addEventListener('message', handleMessage);

      const check = setInterval(() => {
        if (popup && popup.closed) {
          clearInterval(check);
          window.removeEventListener('message', handleMessage);
          setConnecting(false);
        }
      }, 500);
    } catch (err) {
      onToast(`Connection error: ${err}`, 'error');
      setConnecting(false);
    }
  }, [onToast, fetchData]);

  const handleFolderClick = useCallback((folder: CloudFile) => {
    setBreadcrumb((prev) => [...prev, { id: folder.id, name: folder.name }]);
  }, []);

  const handleBreadcrumbClick = useCallback((index: number) => {
    setBreadcrumb((prev) => prev.slice(0, index + 1));
  }, []);

  const handleImport = useCallback(async (file: CloudFile) => {
    if (!selectedAccount) return;
    setImporting(file.id);
    try {
      const res = await fetch(`/api/cloud-drive/import/${selectedAccount.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: file.id,
          file_name: file.name,
          mime_type: file.mime_type,
        }),
      });
      const body = await res.json();
      if (res.ok) {
        onToast(`"${file.name}" imported — ${body.row_count} rows, ${body.column_count} columns`, 'success');
        onImported(body as ImportResult);
      } else {
        onToast(body.detail || 'Import failed', 'error');
      }
    } catch (err) {
      onToast(`Import error: ${err}`, 'error');
    } finally {
      setImporting(null);
    }
  }, [selectedAccount, onImported, onToast]);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '24px 0' }}>
        <p className="v2-body-sm" style={{ color: 'var(--v2-text-tertiary)' }}>Loading...</p>
      </div>
    );
  }

  if (connectors.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '24px 16px' }}>
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--v2-text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: '0 auto 8px' }}>
          <path d="M22 12H2" /><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z" />
        </svg>
        <p className="v2-body-sm" style={{ marginBottom: 4 }}>No cloud drive connectors configured</p>
        <p style={{ fontSize: 11, color: 'var(--v2-text-tertiary)' }}>
          Add a Google Drive connector in the Connectors page first
        </p>
      </div>
    );
  }

  if (accounts.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '24px 16px' }}>
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--v2-text-tertiary)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: '0 auto 8px' }}>
          <path d="M18 8h1a4 4 0 010 8h-1" /><path d="M2 8h16v9a4 4 0 01-4 4H6a4 4 0 01-4-4V8z" /><line x1="6" y1="1" x2="6" y2="4" /><line x1="10" y1="1" x2="10" y2="4" /><line x1="14" y1="1" x2="14" y2="4" />
        </svg>
        <p className="v2-body-sm" style={{ marginBottom: 10 }}>Connect your cloud drive to browse files</p>
        {connectors.map((c) => (
          <button
            key={c.id}
            type="button"
            className="v2-btn v2-btn-primary v2-btn-sm"
            onClick={() => handleConnect(c.id)}
            disabled={connecting}
            style={{ opacity: connecting ? 0.5 : 1, marginRight: 8 }}
          >
            {connecting ? 'Connecting...' : `Connect ${PROVIDER_LABELS[c.type] ?? c.type}`}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div>
      {/* Account selector */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <select
          className="v2-select"
          value={selectedAccount?.id ?? ''}
          onChange={(e) => {
            const acc = accounts.find((a) => a.id === Number(e.target.value));
            if (acc) {
              setSelectedAccount(acc);
              setBreadcrumb([{ id: null, name: 'My Drive' }]);
            }
          }}
          style={{ flex: 1, fontSize: 12 }}
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.email} ({PROVIDER_LABELS[a.provider] ?? a.provider})
            </option>
          ))}
        </select>
        {connectors.length > 0 && (
          <button
            type="button"
            className="v2-btn v2-btn-ghost v2-btn-sm"
            onClick={() => handleConnect(connectors[0]!.id)}
            disabled={connecting}
            style={{ flexShrink: 0, fontSize: 11 }}
          >
            + Add
          </button>
        )}
      </div>

      {/* Breadcrumb */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 8, flexWrap: 'wrap' }}>
        {breadcrumb.map((item, i) => (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {i > 0 && <span style={{ color: 'var(--v2-text-tertiary)', fontSize: 10 }}>/</span>}
            <button
              type="button"
              onClick={() => handleBreadcrumbClick(i)}
              style={{
                background: 'none',
                border: 'none',
                cursor: i < breadcrumb.length - 1 ? 'pointer' : 'default',
                fontSize: 11,
                fontWeight: i === breadcrumb.length - 1 ? 600 : 400,
                color: i < breadcrumb.length - 1 ? 'var(--v2-accent-text)' : 'var(--v2-text-primary)',
                padding: '2px 4px',
                borderRadius: 'var(--v2-radius-sm)',
                textDecoration: i < breadcrumb.length - 1 ? 'underline' : 'none',
              }}
            >
              {item.name}
            </button>
          </span>
        ))}
      </div>

      {/* File list */}
      <div
        style={{
          border: '1px solid var(--v2-border)',
          borderRadius: 'var(--v2-radius-md)',
          maxHeight: 240,
          overflowY: 'auto',
        }}
      >
        {browsing ? (
          <div style={{ padding: '24px 0', textAlign: 'center' }}>
            <p className="v2-body-sm" style={{ color: 'var(--v2-text-tertiary)' }}>Loading files...</p>
          </div>
        ) : files.length === 0 ? (
          <div style={{ padding: '24px 0', textAlign: 'center' }}>
            <p className="v2-body-sm" style={{ color: 'var(--v2-text-tertiary)' }}>No spreadsheets found</p>
          </div>
        ) : (
          files.map((f) => (
            <div
              key={f.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '7px 12px',
                borderBottom: '1px solid var(--v2-border-light)',
                cursor: f.is_folder ? 'pointer' : 'default',
                fontSize: 12,
              }}
              onClick={f.is_folder ? () => handleFolderClick(f) : undefined}
              onKeyDown={f.is_folder ? (e) => { if (e.key === 'Enter') handleFolderClick(f); } : undefined}
              role={f.is_folder ? 'button' : undefined}
              tabIndex={f.is_folder ? 0 : undefined}
            >
              {/* Icon */}
              {f.is_folder ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="var(--v2-text-tertiary)" stroke="none">
                  <path d="M10 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-2z" />
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--v2-accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
              )}

              {/* Name */}
              <span
                style={{
                  flex: 1,
                  fontWeight: f.is_folder ? 500 : 400,
                  color: 'var(--v2-text-primary)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {f.name}
              </span>

              {/* Meta or action */}
              {f.is_folder ? (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--v2-text-tertiary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              ) : (
                <>
                  <span style={{ fontSize: 10, color: 'var(--v2-text-tertiary)', flexShrink: 0 }}>
                    {MIME_LABELS[f.mime_type] ?? ''} {formatFileSize(f.size)}
                  </span>
                  <button
                    type="button"
                    className="v2-btn v2-btn-primary v2-btn-sm"
                    onClick={(e) => { e.stopPropagation(); handleImport(f); }}
                    disabled={importing === f.id}
                    style={{ flexShrink: 0, fontSize: 10, padding: '3px 8px', opacity: importing === f.id ? 0.5 : 1 }}
                  >
                    {importing === f.id ? 'Importing...' : 'Import'}
                  </button>
                </>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
