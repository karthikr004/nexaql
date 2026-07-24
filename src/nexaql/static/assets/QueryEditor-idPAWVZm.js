import{r as m,j as E,F as z}from"./index-DN8qixE3.js";const T="nexaql";function W(r){r.languages.getLanguages().some(d=>d.id===T)||(r.languages.register({id:T}),r.languages.setMonarchTokensProvider(T,{keywords:["query"],tokenizer:{root:[[/#[^\n]*/,"comment"],[/\/\/[^\n]*/,"comment"],[/@[a-zA-Z_]\w*/,"directive"],[/\b(query)\b/,"keyword"],[/\b(true|false|null)\b/,"constant"],[/\b(sum|avg|min|max|count|calc)\b/,"aggregate"],[/\b(CURRENT_DATE|CURRENT_TIMESTAMP|CURRENT_TIME|NOW)\b/,"constant"],[/\b(EXTRACT|DATE_TRUNC|DATE_PART|AGE|ROUND|CEIL|FLOOR|ABS|GREATEST|LEAST|COALESCE|NULLIF|TO_DATE)\b/,"aggregate"],[/"[^"]*"/,"string"],[/'[^']*'/,"string"],[/-?\d+\.\d+/,"number.float"],[/-?\d+/,"number"],[/[a-zA-Z_]\w*(?=\s*\()/,"node"],[/[a-zA-Z_]\w*(?=\s*\{)/,"node"],[/[a-zA-Z_]\w*(?=\s*:)/,"field-alias"],[/[a-zA-Z_]\w*/,"field"],[/[{}()[\]:,@]/,"delimiter"]]}})),r.editor.defineTheme("nexaql-dark",{base:"vs-dark",inherit:!0,rules:[{token:"comment",foreground:"475569",fontStyle:"italic"},{token:"keyword",foreground:"a78bfa",fontStyle:"bold"},{token:"directive",foreground:"22d3ee"},{token:"node",foreground:"4f8ef7",fontStyle:"bold"},{token:"field",foreground:"3dd68c"},{token:"field-alias",foreground:"e2e8f0"},{token:"aggregate",foreground:"a78bfa"},{token:"constant",foreground:"f97316"},{token:"string",foreground:"f97316"},{token:"number",foreground:"22d3ee"},{token:"number.float",foreground:"22d3ee"},{token:"delimiter",foreground:"64748b"}],colors:{"editor.background":"#0f1117","editor.foreground":"#e2e8f0","editor.lineHighlightBackground":"#161b27","editor.selectionBackground":"#1e3a5f","editorLineNumber.foreground":"#334155","editorLineNumber.activeForeground":"#64748b","editorCursor.foreground":"#4f8ef7","editorWidget.background":"#141926","editorSuggestWidget.background":"#141926","editorSuggestWidget.border":"#252d3d","editorSuggestWidget.selectedBackground":"#1e2d4a","list.hoverBackground":"#1e2535","editor.inactiveSelectionBackground":"#1e3a5f60","editorGutter.background":"#0f1117"}}),r.editor.defineTheme("nexaql-light",{base:"vs",inherit:!0,rules:[{token:"comment",foreground:"94a3b8",fontStyle:"italic"},{token:"keyword",foreground:"7c3aed",fontStyle:"bold"},{token:"directive",foreground:"0891b2"},{token:"node",foreground:"2563eb",fontStyle:"bold"},{token:"field",foreground:"16a34a"},{token:"field-alias",foreground:"334155"},{token:"aggregate",foreground:"7c3aed"},{token:"constant",foreground:"ea580c"},{token:"string",foreground:"ea580c"},{token:"number",foreground:"0891b2"},{token:"number.float",foreground:"0891b2"},{token:"delimiter",foreground:"94a3b8"}],colors:{"editor.background":"#ffffff","editor.foreground":"#0f172a","editor.lineHighlightBackground":"#f8fafc","editor.selectionBackground":"#bfdbfe","editorLineNumber.foreground":"#94a3b8","editorLineNumber.activeForeground":"#475569","editorCursor.foreground":"#2563eb","editorWidget.background":"#f8fafc","editorSuggestWidget.background":"#ffffff","editorSuggestWidget.border":"#e2e8f0","editorSuggestWidget.selectedBackground":"#eff6ff","list.hoverBackground":"#f1f5f9","editor.inactiveSelectionBackground":"#bfdbfe60","editorGutter.background":"#ffffff"}})}function O(r){let d=0,e=!1,a="";for(let f=0;f<r.length;f++){const l=r[f];if(e){if(l==="\\"){f++;continue}l===a&&(e=!1);continue}if(l==='"'||l==="'"){e=!0,a=l;continue}l==="("&&d++,l===")"&&d--}return d>0}function j(r){const d=r.lastIndexOf("calc(");if(d===-1)return!1;let e=0;for(let a=d+4;a<r.length;a++)if(r[a]==="("&&e++,r[a]===")"){if(e===0)return!1;e--}return!0}function H(r){const e=(r.split(`
`).pop()??"").match(/(\w+)\s*:\s*(?:"[^"]*"?)?$/);return(e==null?void 0:e[1])??null}function q(r){const d=[];let e=0;for(;e<r.length;){const a=r[e];if(a==='"'||a==="'"){const f=a;for(e++;e<r.length&&r[e]!==f;)r[e]==="\\"&&e++,e++;e++;continue}if(a==="#"||a==="/"&&r[e+1]==="/"){for(;e<r.length&&r[e]!==`
`;)e++;continue}if(a==="{"){const l=r.substring(0,e).match(/(\w+)\s*(?:\([^)]*\))?\s*(?:@[^\s{]+\s*)*\s*$/);d.push((l==null?void 0:l[1])??""),e++;continue}if(a==="}"){d.pop(),e++;continue}e++}return d}const Y=[{label:"CURRENT_DATE",insert:"CURRENT_DATE",detail:"date",doc:"Today's date"},{label:"CURRENT_TIMESTAMP",insert:"CURRENT_TIMESTAMP",detail:"timestamp",doc:"Current date + time"},{label:"EXTRACT",insert:"EXTRACT(${1|DAY,MONTH,YEAR,HOUR,EPOCH|} FROM ${2:expr})",detail:"numeric",doc:"Extract part of a date/interval"},{label:"DATE_TRUNC",insert:"DATE_TRUNC('${1|year,month,week,day|}', ${2:field})",detail:"date",doc:"Truncate date to unit"},{label:"DATE_PART",insert:"DATE_PART('${1|day,month,year,hour|}', ${2:field})",detail:"numeric",doc:"Extract numeric date component"},{label:"AGE",insert:"AGE(${1:end_date}, ${2:start_date})",detail:"interval",doc:"Interval between two dates"},{label:"TO_DATE",insert:"TO_DATE(${1:field}, 'YYYY-MM-DD')",detail:"date",doc:"Parse string to date"},{label:"ROUND",insert:"ROUND(${1:expr}, ${2:2})",detail:"numeric",doc:"Round to N decimal places"},{label:"CEIL",insert:"CEIL(${1:expr})",detail:"integer",doc:"Round up to nearest integer"},{label:"FLOOR",insert:"FLOOR(${1:expr})",detail:"integer",doc:"Round down to nearest integer"},{label:"ABS",insert:"ABS(${1:expr})",detail:"numeric",doc:"Absolute value"},{label:"GREATEST",insert:"GREATEST(${1:expr1}, ${2:expr2})",detail:"numeric",doc:"Largest of arguments — useful to clamp to 0"},{label:"LEAST",insert:"LEAST(${1:expr1}, ${2:expr2})",detail:"numeric",doc:"Smallest of arguments"},{label:"COALESCE",insert:"COALESCE(${1:field}, ${2:0})",detail:"any",doc:"First non-null value"},{label:"NULLIF",insert:"NULLIF(${1:expr}, ${2:0})",detail:"any",doc:"NULL if two values are equal (prevent /0)"},{label:"::INTEGER",insert:"::INTEGER",detail:"cast",doc:"Cast to integer"},{label:"::NUMERIC",insert:"::NUMERIC",detail:"cast",doc:"Cast to numeric"},{label:"::TEXT",insert:"::TEXT",detail:"cast",doc:"Cast to text"},{label:"::DATE",insert:"::DATE",detail:"cast",doc:"Cast timestamp to date"}],X=[{name:"All Orders",query:`# List all orders with customer details
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
}`},{name:"Customer Orders",query:`# Traverse from customers to their orders and line items
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
}`},{name:"Revenue by Product",query:`# Aggregate revenue grouped by product
query RevenueByProduct {
  order_item @orderby(total_revenue, DESC) {
    product_id
    total_revenue: sum(unit_price)
    items_sold: count()
    avg_price: avg(unit_price)
  }
}`},{name:"High Value Items",query:`# Find line items where the extended price exceeds a threshold
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
}`},{name:"Recent Orders",query:`# Orders placed recently
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
}`}];function Z({value:r,onChange:d,onRun:e,insertText:a,onInsertConsumed:f,ontologyNodes:l=[],examples:S,theme:M="dark"}){const N=m.useRef(null),x=m.useRef(e),R=m.useRef(d),L=m.useRef(l),_=m.useRef(null);m.useEffect(()=>{x.current=e},[e]),m.useEffect(()=>{R.current=d},[d]),m.useEffect(()=>{L.current=l},[l]);const F=m.useCallback((u,g)=>{var w;N.current=u,u.addCommand(g.KeyMod.CtrlCmd|g.KeyCode.Enter,()=>{x.current()}),(w=_.current)==null||w.dispose(),_.current=g.languages.registerCompletionItemProvider(T,{triggerCharacters:["{","("," ",`
`,"@",":","_"],provideCompletionItems($,b){const y=$.getWordUntilPosition(b),I=y.startColumn>1?$.getValueInRange({startLineNumber:b.lineNumber,endLineNumber:b.lineNumber,startColumn:y.startColumn-1,endColumn:y.startColumn}):"",U=I==="@"?y.startColumn-1:y.startColumn,D={startLineNumber:b.lineNumber,endLineNumber:b.lineNumber,startColumn:U,endColumn:b.column},c=$.getValueInRange({startLineNumber:1,startColumn:1,endLineNumber:b.lineNumber,endColumn:b.column}),C=L.current,h=[],n=g.languages.CompletionItemKind,B=g.languages.CompletionItemInsertTextRule.InsertAsSnippet,i=(t,o,p,s,K,G="5")=>h.push({label:t,kind:p,detail:s,documentation:K,insertText:o,insertTextRules:B,sortText:G+t,range:D});if(I==="@"||c.match(/@\w*$/))return i("@limit","@limit(${1:10})",n.Keyword,void 0,"Limit result rows","1"),i("@offset","@offset(${1:0})",n.Keyword,void 0,"Skip N rows","1"),i("@orderby","@orderby(${1:field}, ${2|ASC,DESC|})",n.Keyword,void 0,"Sort results","1"),i("@distinct","@distinct",n.Keyword,void 0,"Remove duplicates","1"),{suggestions:h};if(j(c)){for(const s of Y)i(s.label,s.insert,n.Function,s.detail,s.doc,"1");const t=q(c),o=t[t.length-1]??"",p=C.find(s=>s.name===o);if(p)for(const s of p.fields)i(s.name,s.name,n.Field,s.type,void 0,"2");return{suggestions:h}}const A=q(c),P=A.length>0?A[A.length-1]:"",v=C.find(t=>t.name===P);let k=v;if(!k&&O(c)){const t=c.match(/(\w+)\s*\([^)]*$/);t&&(k=C.find(o=>o.name===t[1]))}if(O(c)&&k){if(H(c)&&c.match(/:\s*\{\s*\w*$/)){for(const[o,p]of[["eq","Equal to"],["ne","Not equal"],["gt","Greater than"],["gte","Greater than or equal"],["lt","Less than"],["lte","Less than or equal"],["like","ILIKE pattern match"],["in","In list [a, b, c]"],["not_in","Not in list"],["null","IS NULL / IS NOT NULL"]])i(o,`${o}: \${1:value}`,n.Operator,"operator",p,"1");return{suggestions:h}}for(const o of k.fields)i(o.name,`${o.name}: \${1:value}`,n.Field,o.type,void 0,"2");for(const o of k.specialFilters)i(o.name,`${o.name}: true`,n.Value,"special filter",o.description,"2");return i("calc(...): filter","calc(${1:expr}): { ${2|gt,gte,lt,lte,eq,ne|}: ${3:value} }",n.Keyword,"calc filter","Filter rows by a computed expression","3"),{suggestions:h}}if(v){i("calc(...)","${1:alias}: calc(${2:expr})",n.Keyword,"computed field","Inline computed expression","1");for(const t of v.fields)i(t.name,t.name,n.Field,t.type,void 0,"2");for(const[t,o]of[["sum","Sum of values"],["avg","Average of values"],["min","Minimum value"],["max","Maximum value"],["count","Count of rows"]])i(t,`\${1:alias}: ${t}(\${2:field})`,n.Function,`${t.toUpperCase()} aggregation`,o,"3");for(const t of v.edges){const o=C.find(s=>s.name===t.target),p=(o==null?void 0:o.fields.slice(0,3).map(s=>`    ${s.name}`).join(`
`))??"    ";i(t.name,`${t.name} {
${p}
  }`,n.Module,`-> ${t.target}`,t.description,"4")}i("@limit","@limit(${1:10})",n.Keyword,void 0,"Limit result rows","5"),i("@offset","@offset(${1:0})",n.Keyword,void 0,"Skip N rows","5"),i("@orderby","@orderby(${1:field}, ${2|ASC,DESC|})",n.Keyword,void 0,"Sort results","5"),i("@distinct","@distinct",n.Keyword,void 0,"Remove duplicates","5")}else{(!c.trim()||c.match(/^\s*(?:#[^\n]*)?\s*$/))&&i("query",`query \${1:QueryName} {
  $0
}`,n.Keyword,void 0,"Start a new NexaQL query","1");for(const t of C)i(t.name,`${t.name} {
  \${1}
}`,n.Class,t.description,void 0,"2")}return{suggestions:h}}})},[]);return m.useEffect(()=>{if(!a||!N.current)return;const u=N.current,g=u.getSelection();g&&u.executeEdits("schema-explorer",[{range:g,text:a,forceMoveMarkers:!0}]),u.focus(),f()},[a,f]),E.jsxs("div",{className:"flex h-full flex-col",children:[E.jsxs("div",{className:"flex shrink-0 items-center gap-1.5 overflow-x-auto border-b px-3 py-2",style:{backgroundColor:"var(--bg-primary)",borderColor:"var(--border)"},children:[E.jsx("span",{className:"mr-1 shrink-0 text-[10px]",style:{color:"var(--text-muted)"},children:"Examples:"}),(S&&S.length>0?S:X).map(u=>E.jsx("button",{type:"button",onClick:()=>R.current(u.query),className:"shrink-0 whitespace-nowrap rounded border px-2 py-1 text-[10px] transition-colors",style:{borderColor:"var(--border)",backgroundColor:"var(--bg-input)",color:"var(--text-secondary)"},children:u.name},u.name))]}),E.jsx("div",{className:"min-h-0 flex-1",children:E.jsx(z,{height:"100%",language:T,theme:M==="light"?"nexaql-light":"nexaql-dark",value:r,beforeMount:W,onChange:u=>R.current(u??""),onMount:F,options:{fontSize:13,fontFamily:"'JetBrains Mono', 'Fira Code', monospace",fontLigatures:!0,lineNumbers:"on",minimap:{enabled:!1},scrollBeyondLastLine:!1,automaticLayout:!0,tabSize:2,insertSpaces:!0,wordWrap:"on",padding:{top:16,bottom:16},renderLineHighlight:"line",cursorBlinking:"smooth",smoothScrolling:!0,contextmenu:!1,quickSuggestions:{other:!0,comments:!1,strings:!1},suggestOnTriggerCharacters:!0,acceptSuggestionOnEnter:"on",bracketPairColorization:{enabled:!0},guides:{bracketPairs:!0},scrollbar:{verticalScrollbarSize:6,horizontalScrollbarSize:6},readOnly:!1}})}),E.jsx("div",{className:"shrink-0 border-t px-3 py-1.5",style:{backgroundColor:"var(--bg-primary)",borderColor:"var(--border)"},children:E.jsxs("span",{className:"text-[10px]",style:{color:"var(--text-muted)"},children:["⌘↩"," to run ","·"," ","⌃","Space for suggestions ","·"," Ctrl+/ to comment"]})})]})}export{Z as default};
