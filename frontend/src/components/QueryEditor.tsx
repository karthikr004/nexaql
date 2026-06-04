import { useEffect, useRef, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import type * as MonacoType from 'monaco-editor';
import type { NodeInfo } from '../types';

interface Props {
  value: string;
  onChange: (v: string) => void;
  onRun: () => void;
  insertText?: string;
  onInsertConsumed: () => void;
  ontologyNodes?: NodeInfo[];
  theme?: 'dark' | 'light';
}

const LANG = 'nexaql';

// ── Language + theme registration (sync, before editor renders) ───────────────

function beforeMount(monaco: typeof MonacoType) {
  if (!monaco.languages.getLanguages().some((l) => l.id === LANG)) {
    monaco.languages.register({ id: LANG });

    monaco.languages.setMonarchTokensProvider(LANG, {
      keywords: ['query'],
      tokenizer: {
        root: [
          [/#[^\n]*/, 'comment'],
          [/\/\/[^\n]*/, 'comment'],
          [/@[a-zA-Z_]\w*/, 'directive'],
          [/\b(query)\b/, 'keyword'],
          [/\b(true|false|null)\b/, 'constant'],
          [/\b(sum|avg|min|max|count|calc)\b/, 'aggregate'],
          [/\b(CURRENT_DATE|CURRENT_TIMESTAMP|CURRENT_TIME|NOW)\b/, 'constant'],
          [
            /\b(EXTRACT|DATE_TRUNC|DATE_PART|AGE|ROUND|CEIL|FLOOR|ABS|GREATEST|LEAST|COALESCE|NULLIF|TO_DATE)\b/,
            'aggregate',
          ],
          [/"[^"]*"/, 'string'],
          [/'[^']*'/, 'string'],
          [/-?\d+\.\d+/, 'number.float'],
          [/-?\d+/, 'number'],
          [/[a-zA-Z_]\w*(?=\s*\()/, 'node'],
          [/[a-zA-Z_]\w*(?=\s*\{)/, 'node'],
          [/[a-zA-Z_]\w*(?=\s*:)/, 'field-alias'],
          [/[a-zA-Z_]\w*/, 'field'],
          [/[{}()[\]:,@]/, 'delimiter'],
        ],
      },
    });
  }

  monaco.editor.defineTheme('nexaql-dark', {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'comment', foreground: '475569', fontStyle: 'italic' },
      { token: 'keyword', foreground: 'a78bfa', fontStyle: 'bold' },
      { token: 'directive', foreground: '22d3ee' },
      { token: 'node', foreground: '4f8ef7', fontStyle: 'bold' },
      { token: 'field', foreground: '3dd68c' },
      { token: 'field-alias', foreground: 'e2e8f0' },
      { token: 'aggregate', foreground: 'a78bfa' },
      { token: 'constant', foreground: 'f97316' },
      { token: 'string', foreground: 'f97316' },
      { token: 'number', foreground: '22d3ee' },
      { token: 'number.float', foreground: '22d3ee' },
      { token: 'delimiter', foreground: '64748b' },
    ],
    colors: {
      'editor.background': '#0f1117',
      'editor.foreground': '#e2e8f0',
      'editor.lineHighlightBackground': '#161b27',
      'editor.selectionBackground': '#1e3a5f',
      'editorLineNumber.foreground': '#334155',
      'editorLineNumber.activeForeground': '#64748b',
      'editorCursor.foreground': '#4f8ef7',
      'editorWidget.background': '#141926',
      'editorSuggestWidget.background': '#141926',
      'editorSuggestWidget.border': '#252d3d',
      'editorSuggestWidget.selectedBackground': '#1e2d4a',
      'list.hoverBackground': '#1e2535',
      'editor.inactiveSelectionBackground': '#1e3a5f60',
      'editorGutter.background': '#0f1117',
    },
  });

  monaco.editor.defineTheme('nexaql-light', {
    base: 'vs',
    inherit: true,
    rules: [
      { token: 'comment', foreground: '94a3b8', fontStyle: 'italic' },
      { token: 'keyword', foreground: '7c3aed', fontStyle: 'bold' },
      { token: 'directive', foreground: '0891b2' },
      { token: 'node', foreground: '2563eb', fontStyle: 'bold' },
      { token: 'field', foreground: '16a34a' },
      { token: 'field-alias', foreground: '334155' },
      { token: 'aggregate', foreground: '7c3aed' },
      { token: 'constant', foreground: 'ea580c' },
      { token: 'string', foreground: 'ea580c' },
      { token: 'number', foreground: '0891b2' },
      { token: 'number.float', foreground: '0891b2' },
      { token: 'delimiter', foreground: '94a3b8' },
    ],
    colors: {
      'editor.background': '#ffffff',
      'editor.foreground': '#0f172a',
      'editor.lineHighlightBackground': '#f8fafc',
      'editor.selectionBackground': '#bfdbfe',
      'editorLineNumber.foreground': '#94a3b8',
      'editorLineNumber.activeForeground': '#475569',
      'editorCursor.foreground': '#2563eb',
      'editorWidget.background': '#f8fafc',
      'editorSuggestWidget.background': '#ffffff',
      'editorSuggestWidget.border': '#e2e8f0',
      'editorSuggestWidget.selectedBackground': '#eff6ff',
      'list.hoverBackground': '#f1f5f9',
      'editor.inactiveSelectionBackground': '#bfdbfe60',
      'editorGutter.background': '#ffffff',
    },
  });
}

// ── Context analysis for completions ─────────────────────────────────────────

/** True when the cursor is inside an unmatched `(` — i.e. inside filter args */
function isInsideFilterParens(text: string): boolean {
  let depth = 0;
  let inString = false;
  let quote = '';
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (ch === '\\') {
        i++;
        continue;
      }
      if (ch === quote) inString = false;
      continue;
    }
    if (ch === '"' || ch === "'") {
      inString = true;
      quote = ch;
      continue;
    }
    if (ch === '(') depth++;
    if (ch === ')') depth--;
  }
  return depth > 0;
}

/** True when the cursor is inside a calc( expression */
function isInsideCalcExpr(text: string): boolean {
  // Look for last unmatched calc( before cursor
  const calcStart = text.lastIndexOf('calc(');
  if (calcStart === -1) return false;
  // Count parens from that position to cursor
  let depth = 0;
  for (let i = calcStart + 4; i < text.length; i++) {
    if (text[i] === '(') depth++;
    if (text[i] === ')') {
      if (depth === 0) return false;
      depth--;
    }
  }
  return true; // still inside unmatched calc(
}

/**
 * Returns the field name just before a colon on the current line, if any.
 * e.g. "  status: " -> "status"
 */
function getFieldBeforeColon(text: string): string | null {
  const lastLine = text.split('\n').pop() ?? '';
  const m = lastLine.match(/(\w+)\s*:\s*(?:"[^"]*"?)?$/);
  return m?.[1] ?? null;
}

/**
 * Returns the stack of node-like names opened by unmatched `{` blocks.
 * e.g. "query Foo {\n  invoice_header {\n    su" -> ["Foo", "invoice_header"]
 */
function getNodeStack(text: string): string[] {
  const stack: string[] = [];
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    // Skip strings
    if (ch === '"' || ch === "'") {
      const q = ch;
      i++;
      while (i < text.length && text[i] !== q) {
        if (text[i] === '\\') i++;
        i++;
      }
      i++;
      continue;
    }
    // Skip line comments
    if (ch === '#' || (ch === '/' && text[i + 1] === '/')) {
      while (i < text.length && text[i] !== '\n') i++;
      continue;
    }
    if (ch === '{') {
      const before = text.substring(0, i);
      // Match last identifier before {, ignoring (args) and @directives
      const m = before.match(/(\w+)\s*(?:\([^)]*\))?\s*(?:@[^\s{]+\s*)*\s*$/);
      stack.push(m?.[1] ?? '');
      i++;
      continue;
    }
    if (ch === '}') {
      stack.pop();
      i++;
      continue;
    }
    i++;
  }
  return stack;
}

// ── System functions / constants for calc() completions ──────────────────────

// biome-ignore-start lint/suspicious/noTemplateCurlyInString: Monaco snippet syntax uses ${n:placeholder} not JS template literals
const CALC_SYSTEM_FUNCTIONS = [
  // constants
  { label: 'CURRENT_DATE', insert: 'CURRENT_DATE', detail: 'date', doc: "Today's date" },
  { label: 'CURRENT_TIMESTAMP', insert: 'CURRENT_TIMESTAMP', detail: 'timestamp', doc: 'Current date + time' },
  // date functions
  {
    label: 'EXTRACT',
    insert: 'EXTRACT(${1|DAY,MONTH,YEAR,HOUR,EPOCH|} FROM ${2:expr})',
    detail: 'numeric',
    doc: 'Extract part of a date/interval',
  },
  {
    label: 'DATE_TRUNC',
    insert: "DATE_TRUNC('${1|year,month,week,day|}', ${2:field})",
    detail: 'date',
    doc: 'Truncate date to unit',
  },
  {
    label: 'DATE_PART',
    insert: "DATE_PART('${1|day,month,year,hour|}', ${2:field})",
    detail: 'numeric',
    doc: 'Extract numeric date component',
  },
  {
    label: 'AGE',
    insert: 'AGE(${1:end_date}, ${2:start_date})',
    detail: 'interval',
    doc: 'Interval between two dates',
  },
  { label: 'TO_DATE', insert: "TO_DATE(${1:field}, 'YYYY-MM-DD')", detail: 'date', doc: 'Parse string to date' },
  // math
  { label: 'ROUND', insert: 'ROUND(${1:expr}, ${2:2})', detail: 'numeric', doc: 'Round to N decimal places' },
  { label: 'CEIL', insert: 'CEIL(${1:expr})', detail: 'integer', doc: 'Round up to nearest integer' },
  { label: 'FLOOR', insert: 'FLOOR(${1:expr})', detail: 'integer', doc: 'Round down to nearest integer' },
  { label: 'ABS', insert: 'ABS(${1:expr})', detail: 'numeric', doc: 'Absolute value' },
  {
    label: 'GREATEST',
    insert: 'GREATEST(${1:expr1}, ${2:expr2})',
    detail: 'numeric',
    doc: 'Largest of arguments — useful to clamp to 0',
  },
  { label: 'LEAST', insert: 'LEAST(${1:expr1}, ${2:expr2})', detail: 'numeric', doc: 'Smallest of arguments' },
  // null handling
  { label: 'COALESCE', insert: 'COALESCE(${1:field}, ${2:0})', detail: 'any', doc: 'First non-null value' },
  {
    label: 'NULLIF',
    insert: 'NULLIF(${1:expr}, ${2:0})',
    detail: 'any',
    doc: 'NULL if two values are equal (prevent /0)',
  },
  // type casts
  { label: '::INTEGER', insert: '::INTEGER', detail: 'cast', doc: 'Cast to integer' },
  { label: '::NUMERIC', insert: '::NUMERIC', detail: 'cast', doc: 'Cast to numeric' },
  { label: '::TEXT', insert: '::TEXT', detail: 'cast', doc: 'Cast to text' },
  { label: '::DATE', insert: '::DATE', detail: 'cast', doc: 'Cast timestamp to date' },
];
// biome-ignore-end lint/suspicious/noTemplateCurlyInString: end of Monaco snippet section

// ── Example queries ───────────────────────────────────────────────────────────

const EXAMPLE_QUERIES = [
  {
    name: 'All Orders',
    query: `# List all orders with customer details
query AllOrders {
  order @orderby(ordered_at, DESC) @limit(50) {
    id
    ordered_at
    status
    total_amount
    customer {
      name
    }
  }
}`,
  },
  {
    name: 'Customer Orders',
    query: `# Traverse from customers to their orders and line items
query CustomerOrders {
  customer @orderby(name, ASC) {
    name
    email
    orders {
      id
      ordered_at
      total_amount
      items {
        quantity
        unit_price
        product {
          name
        }
      }
    }
  }
}`,
  },
  {
    name: 'Revenue by Product',
    query: `# Aggregate revenue grouped by product
query RevenueByProduct {
  order_item @orderby(total_revenue, DESC) {
    product_id
    total_revenue: sum(unit_price)
    items_sold: count()
    avg_price: avg(unit_price)
  }
}`,
  },
  {
    name: 'High Value Items',
    query: `# Find line items where the extended price exceeds a threshold
query HighValueItems {
  order_item(calc(quantity * unit_price): { gt: 500 }) {
    quantity
    unit_price
    line_total: calc(quantity * unit_price)
    product {
      name
    }
    order {
      id
      customer {
        name
      }
    }
  }
}`,
  },
  {
    name: 'Recent Orders',
    query: `# Orders placed recently
query RecentOrders {
  order(ordered_at: { gte: "2024-01-01" }) @orderby(ordered_at, DESC) @limit(20) {
    id
    ordered_at
    status
    total_amount
    customer {
      name
      email
    }
  }
}`,
  },
];

// ── Component ─────────────────────────────────────────────────────────────────

export default function QueryEditor({
  value,
  onChange,
  onRun,
  insertText,
  onInsertConsumed,
  ontologyNodes = [],
  theme = 'dark',
}: Props) {
  const editorRef = useRef<MonacoType.editor.IStandaloneCodeEditor | null>(null);
  const onRunRef = useRef(onRun);
  const onChangeRef = useRef(onChange);
  const ontologyNodesRef = useRef(ontologyNodes);
  const completionRef = useRef<MonacoType.IDisposable | null>(null);

  useEffect(() => {
    onRunRef.current = onRun;
  }, [onRun]);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);
  useEffect(() => {
    ontologyNodesRef.current = ontologyNodes;
  }, [ontologyNodes]);

  // Wire up Cmd/Ctrl+Enter AND register context-aware completion provider after mount
  const handleEditorMount = useCallback(
    (editor: MonacoType.editor.IStandaloneCodeEditor, m: typeof MonacoType) => {
      editorRef.current = editor;

      // Cmd/Ctrl+Enter -> run
      editor.addCommand(m.KeyMod.CtrlCmd | m.KeyCode.Enter, () => {
        onRunRef.current();
      });

      // Dispose any previous registration, then register fresh
      completionRef.current?.dispose();
      completionRef.current = m.languages.registerCompletionItemProvider(LANG, {
        triggerCharacters: ['{', '(', ' ', '\n', '@', ':'],
        provideCompletionItems(model, position) {
          const word = model.getWordUntilPosition(position);

          // Extend range leftward to include a leading '@' if present
          const charBeforeWord =
            word.startColumn > 1
              ? model.getValueInRange({
                  startLineNumber: position.lineNumber,
                  endLineNumber: position.lineNumber,
                  startColumn: word.startColumn - 1,
                  endColumn: word.startColumn,
                })
              : '';
          const startCol = charBeforeWord === '@' ? word.startColumn - 1 : word.startColumn;

          const range: MonacoType.IRange = {
            startLineNumber: position.lineNumber,
            endLineNumber: position.lineNumber,
            startColumn: startCol,
            endColumn: position.column,
          };

          const textBefore = model.getValueInRange({
            startLineNumber: 1,
            startColumn: 1,
            endLineNumber: position.lineNumber,
            endColumn: position.column,
          });

          const nodes = ontologyNodesRef.current;
          const suggestions: MonacoType.languages.CompletionItem[] = [];
          const K = m.languages.CompletionItemKind;
          const ISR = m.languages.CompletionItemInsertTextRule.InsertAsSnippet;

          const addSnippet = (
            label: string,
            insert: string,
            kind: MonacoType.languages.CompletionItemKind,
            detail?: string,
            doc?: string,
            sortPrefix = '5',
          ) =>
            suggestions.push({
              label,
              kind,
              detail,
              documentation: doc,
              insertText: insert,
              insertTextRules: ISR,
              sortText: sortPrefix + label,
              range,
            });

          // ── 1. Directive completions (@...) ───────────────────────────
          if (charBeforeWord === '@' || textBefore.match(/@\w*$/)) {
            // biome-ignore lint/suspicious/noTemplateCurlyInString: Monaco snippet syntax
            addSnippet('@limit', '@limit(${1:10})', K.Keyword, undefined, 'Limit result rows', '1');
            // biome-ignore lint/suspicious/noTemplateCurlyInString: Monaco snippet syntax
            addSnippet('@offset', '@offset(${1:0})', K.Keyword, undefined, 'Skip N rows', '1');
            // biome-ignore lint/suspicious/noTemplateCurlyInString: Monaco snippet syntax
            addSnippet('@orderby', '@orderby(${1:field}, ${2|ASC,DESC|})', K.Keyword, undefined, 'Sort results', '1');
            addSnippet('@distinct', '@distinct', K.Keyword, undefined, 'Remove duplicates', '1');
            return { suggestions };
          }

          // ── 2. Inside calc(...) — system functions + constants ────────
          if (isInsideCalcExpr(textBefore)) {
            for (const fn of CALC_SYSTEM_FUNCTIONS) {
              addSnippet(fn.label, fn.insert, K.Function, fn.detail, fn.doc, '1');
            }
            // Also suggest current node's fields as bare names
            const stack = getNodeStack(textBefore);
            const topName = stack[stack.length - 1] ?? '';
            const node = nodes.find((n) => n.name === topName);
            if (node) {
              for (const f of node.fields) {
                addSnippet(f.name, f.name, K.Field, f.type, undefined, '2');
              }
            }
            return { suggestions };
          }

          const stack = getNodeStack(textBefore);
          const topName = stack.length > 0 ? stack[stack.length - 1] : '';
          const currentNode = nodes.find((n) => n.name === topName);

          // ── 3. Inside filter parens — filter keys + enum values ───────
          if (isInsideFilterParens(textBefore) && currentNode) {
            // Check if we're after a colon — suggest enum values for that field
            const fieldName = getFieldBeforeColon(textBefore);
            if (fieldName) {
              // Object-style filter operators after colon + {
              if (textBefore.match(/:\s*\{\s*\w*$/)) {
                for (const [op, doc] of [
                  ['eq', 'Equal to'],
                  ['ne', 'Not equal'],
                  ['gt', 'Greater than'],
                  ['gte', 'Greater than or equal'],
                  ['lt', 'Less than'],
                  ['lte', 'Less than or equal'],
                  ['like', 'ILIKE pattern match'],
                  ['in', 'In list [a, b, c]'],
                  ['not_in', 'Not in list'],
                  ['null', 'IS NULL / IS NOT NULL'],
                ] as [string, string][]) {
                  addSnippet(op, `${op}: \${1:value}`, K.Operator, 'operator', doc, '1');
                }
                return { suggestions };
              }
            }

            // Filter key suggestions — all fields as potential filter keys
            for (const f of currentNode.fields) {
              addSnippet(f.name, `${f.name}: \${1:value}`, K.Field, f.type, undefined, '2');
            }

            // Special filters
            for (const sf of currentNode.specialFilters) {
              addSnippet(sf.name, `${sf.name}: true`, K.Value, 'special filter', sf.description, '2');
            }

            // calc() filter form
            addSnippet(
              'calc(...): filter',
              // biome-ignore lint/suspicious/noTemplateCurlyInString: Monaco snippet syntax
              'calc(${1:expr}): { ${2|gt,gte,lt,lte,eq,ne|}: ${3:value} }',
              K.Keyword,
              'calc filter',
              'Filter rows by a computed expression',
              '3',
            );
            return { suggestions };
          }

          if (!currentNode) {
            // ── 4. Top-level: query keyword + root nodes ──────────────
            if (!textBefore.trim() || textBefore.match(/^\s*(?:#[^\n]*)?\s*$/)) {
              addSnippet(
                'query',
                // biome-ignore lint/suspicious/noTemplateCurlyInString: Monaco snippet syntax
                'query ${1:QueryName} {\n  $0\n}',
                K.Keyword,
                undefined,
                'Start a new NexaQL query',
                '1',
              );
            }
            for (const n of nodes) {
              addSnippet(n.name, `${n.name} {\n  \${1}\n}`, K.Class, n.description, undefined, '2');
            }
          } else {
            // ── 5. Inside node body: fields, calc, aggs, edges ────────

            // Generic calc() snippet
            addSnippet(
              'calc(...)',
              // biome-ignore lint/suspicious/noTemplateCurlyInString: Monaco snippet syntax
              '${1:alias}: calc(${2:expr})',
              K.Keyword,
              'computed field',
              'Inline computed expression',
              '1',
            );

            // Scalar fields
            for (const f of currentNode.fields) {
              addSnippet(f.name, f.name, K.Field, f.type, undefined, '2');
            }

            // Aggregation functions
            for (const [fn, doc] of [
              ['sum', 'Sum of values'],
              ['avg', 'Average of values'],
              ['min', 'Minimum value'],
              ['max', 'Maximum value'],
              ['count', 'Count of rows'],
            ] as [string, string][]) {
              addSnippet(
                fn,
                `\${1:alias}: ${fn}(\${2:field})`,
                K.Function,
                `${fn.toUpperCase()} aggregation`,
                doc,
                '3',
              );
            }

            // Edge fields (with first 3 child fields pre-filled)
            for (const e of currentNode.edges) {
              const targetNode = nodes.find((n) => n.name === e.target);
              const firstFields =
                targetNode?.fields
                  .slice(0, 3)
                  .map((f) => `    ${f.name}`)
                  .join('\n') ?? '    ';
              addSnippet(e.name, `${e.name} {\n${firstFields}\n  }`, K.Module, `-> ${e.target}`, e.description, '4');
            }

            // Directives
            // biome-ignore lint/suspicious/noTemplateCurlyInString: Monaco snippet syntax
            addSnippet('@limit', '@limit(${1:10})', K.Keyword, undefined, 'Limit result rows', '5');
            // biome-ignore lint/suspicious/noTemplateCurlyInString: Monaco snippet syntax
            addSnippet('@offset', '@offset(${1:0})', K.Keyword, undefined, 'Skip N rows', '5');
            // biome-ignore lint/suspicious/noTemplateCurlyInString: Monaco snippet syntax
            addSnippet('@orderby', '@orderby(${1:field}, ${2|ASC,DESC|})', K.Keyword, undefined, 'Sort results', '5');
            addSnippet('@distinct', '@distinct', K.Keyword, undefined, 'Remove duplicates', '5');
          }

          return { suggestions };
        },
      });
    },
    [], // stable — uses refs only
  );

  // Insert text at cursor position (from schema explorer clicks)
  useEffect(() => {
    if (!insertText || !editorRef.current) return;
    const editor = editorRef.current;
    const selection = editor.getSelection();
    if (selection) {
      editor.executeEdits('schema-explorer', [
        {
          range: selection,
          text: insertText,
          forceMoveMarkers: true,
        },
      ]);
    }
    editor.focus();
    onInsertConsumed();
  }, [insertText, onInsertConsumed]);

  return (
    <div className="flex h-full flex-col">
      {/* Example query bar */}
      <div className="flex shrink-0 items-center gap-1.5 overflow-x-auto border-b px-3 py-2" style={{ backgroundColor: 'var(--bg-primary)', borderColor: 'var(--border)' }}>
        <span className="mr-1 shrink-0 text-[10px]" style={{ color: 'var(--text-muted)' }}>Examples:</span>
        {EXAMPLE_QUERIES.map((q) => (
          <button
            type="button"
            key={q.name}
            onClick={() => onChangeRef.current(q.query)}
            className="shrink-0 whitespace-nowrap rounded border px-2 py-1 text-[10px] transition-colors"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-input)', color: 'var(--text-secondary)' }}
          >
            {q.name}
          </button>
        ))}
      </div>

      {/* Monaco Editor */}
      <div className="min-h-0 flex-1">
        <Editor
          height="100%"
          language={LANG}
          theme={theme === 'light' ? 'nexaql-light' : 'nexaql-dark'}
          value={value}
          beforeMount={beforeMount}
          onChange={(v) => onChangeRef.current(v ?? '')}
          onMount={handleEditorMount}
          options={{
            fontSize: 13,
            fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
            fontLigatures: true,
            lineNumbers: 'on',
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            automaticLayout: true,
            tabSize: 2,
            insertSpaces: true,
            wordWrap: 'on',
            padding: { top: 16, bottom: 16 },
            renderLineHighlight: 'line',
            cursorBlinking: 'smooth',
            smoothScrolling: true,
            contextmenu: false,
            quickSuggestions: { other: true, comments: false, strings: false },
            suggestOnTriggerCharacters: true,
            acceptSuggestionOnEnter: 'on',
            bracketPairColorization: { enabled: true },
            guides: { bracketPairs: true },
            scrollbar: { verticalScrollbarSize: 6, horizontalScrollbarSize: 6 },
            readOnly: false,
          }}
        />
      </div>

      {/* Footer hint */}
      <div className="shrink-0 border-t px-3 py-1.5" style={{ backgroundColor: 'var(--bg-primary)', borderColor: 'var(--border)' }}>
        <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{'⌘↩'} to run {'·'} {'⌃'}Space for suggestions {'·'} Ctrl+/ to comment</span>
      </div>
    </div>
  );
}
