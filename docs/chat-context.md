# Optional caller context

Existing `POST /api/chat` requests and Python `ask()` calls remain supported.
`additional_context` is optional; omission or null preserves existing behavior.
Conversation history continues to use `history`.

```json
{
  "question": "Find invoices whose cumulative line amounts exceed the referenced PO line amount",
  "history": [],
  "additional_context": {
    "business_context": [{
      "term": "Overbilling",
      "definition": "Sum invoice-line amounts across invoices by directly referenced PO line. Compare with that PO line amount. Do not join through PO headers."
    }],
    "skill_instructions": "Return matching invoices with supporting line details. Compare amounts only."
  }
}
```

Python callers pass `additional_context=AdditionalContext(...)` to `ask()`.
Import `AdditionalContext` and `BusinessContextEntry` from `nexaql.chat.context`.
Business entries contain `term`, `definition`, and optional `sql_hint`.

NexaQL interprets this context through its existing intent/raw pipeline. Existing
`business_context` arguments and locally discovered business entries are retained;
additional entries are appended without mutating caller data. Both execution
repair paths retain context. Context cannot change access-policy enforcement.

This additive change preserves the existing response schema and generation modes.
It does not introduce pagination or switch OSS clients to a different planner.
Those changes require separate compatibility work.
