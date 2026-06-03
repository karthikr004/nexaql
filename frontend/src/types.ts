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

// ── Full ontology structure for admin editing ────────────────────────────────

export interface OntologyData {
  version: string;
  domain: string;
  description: string;
  nodes: Record<string, NodeData>;
}

export interface NodeData {
  table?: string;
  primary_key: string;
  description: string;
  datasource?: string;
  visible_to?: string[];
  row_policies?: RowPolicyData[];
  fields: Record<string, FieldData>;
  edges?: Record<string, EdgeData>;
  special_filters?: Record<string, SpecialFilterData>;
}

export interface FieldData {
  type: string;
  description: string;
  filterable?: boolean;
  values?: string[];
  derived?: boolean;
  sql_expr?: string;
  visible_to?: string[];
  pii?: boolean;
  mask_with?: string;
}

export interface EdgeData {
  node: string;
  description: string;
  join_type?: string;
  join_steps: JoinStepData[];
}

export interface JoinStepData {
  table: string;
  alias_key: string;
  condition: string;
}

export interface SpecialFilterData {
  description: string;
  sql: string;
  type?: string;
}

export interface RowPolicyData {
  condition: string;
  roles: string[];
  except_roles?: string[];
}
