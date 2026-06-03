export interface NodeShape {
  edgeName: string | null;
  node: string;
  columnAliases: string[];
  aggregationAliases: string[];
  children: NodeShape[];
}

export interface ColumnMeta {
  name: string;
  type: string;
}

export interface FieldInfo {
  name: string;
  type: string;
  description: string;
  filterable: boolean;
  values?: string[];
  visibleTo?: string[];
  pii?: boolean;
  maskWith?: string;
}

export interface EdgeInfo {
  name: string;
  target: string;
  description: string;
}

export interface SpecialFilterInfo {
  name: string;
  description: string;
  type?: string;
}

export interface NodeInfo {
  name: string;
  description: string;
  table: string;
  fieldCount: number;
  fields: FieldInfo[];
  edges: EdgeInfo[];
  specialFilters: SpecialFilterInfo[];
  visibleTo?: string[];
}

export interface OntologySummary {
  domain: string;
  description: string;
  nodes: NodeInfo[];
}

export interface ExecuteResult {
  queryPreview?: string;
  adapterType?: string;
  shape?: NodeShape;
  rows: Record<string, unknown>[];
  rowCount?: number;
  columns: ColumnMeta[];
  durationMs?: number;
  error?: string;
  warnings?: string[];
}

export interface ValidationState {
  valid: boolean;
  errors: string[];
  warnings: string[];
  queryPreview?: string;
  adapterType?: string;
}

export interface ChatTurn {
  id: string;
  question: string;
  nexaqlQuery: string | null;
  queryPreview: string | null;
  adapterType: string | null;
  rows: Record<string, unknown>[];
  columns: ColumnMeta[];
  rowCount: number;
  shape: NodeShape | null;
  summary: string;
  error: string | null;
  loading: boolean;
}

export interface HistoryEntry {
  id: string;
  query: string;
  queryName: string;
  timestamp: number;
  rowCount?: number;
  durationMs?: number;
  hadError: boolean;
}
