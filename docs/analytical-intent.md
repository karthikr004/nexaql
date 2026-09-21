# Typed cumulative comparisons

Intent generation supports an optional `cumulative_comparison` object:

```json
{
  "node": "invoice_line",
  "cumulative_comparison": {
    "operation": "sum",
    "measure": "amount",
    "reference": "purchase_order_line",
    "threshold": "amount",
    "operator": "gt"
  },
  "output_grain": {
    "path": ["purchase_order_line", "purchase_order"],
    "fields": ["po_number"]
  }
}
```

The compiler validates numeric fields and a direct reference to the target primary
key. It derives the grouping key, cumulative expression, and comparison. Output
paths resolve through ontology edges, include the target primary key, and deduplicate
after filtering. Selected relationships must be provably many-to-one through a
single equality join to a declared target primary key; unsupported joins fail
explicitly. The metadata survives intent transformations and repair cannot silently
replace the typed comparison.

Current scope is SUM of a root measure compared to a numeric field on its directly
referenced entity. This is not a general analytical algebra. Existing untyped
intent remains supported. Initial semantic interpretation still uses the model;
typed compilation guarantees do not establish that interpretation's correctness.
