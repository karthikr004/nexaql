# Query reliability checkpoint

This checkpoint adds optional caller context, bounded query repair, ontology
validation of calculated references, typed cumulative comparisons, relationship
absence queries, multi-hop output projection, and window filtering before output
pagination. Semantic review receives compiled SQL; mixed-currency summaries avoid
unsupported cross-currency comparisons.

Validation performed locally:

- 102 engine checks passed; Ruff passed on changed Python files.
- Twelve live procurement questions were compared to independent read-only SQL
  over all requested result values, not only row counts. Ten initially matched.
- The no-purchase-order supplier query and monthly invoice aggregation failures
  were corrected and rerun successfully. Currency summaries were also corrected.
- Absence behavior was verified with a non-empty synthetic fixture and an
  unrelated author/book ontology.
- The full test suite could not start because the local environment lacks
  `mcp.server.fastmcp`.

Limits: this is a local checkpoint, not production certification. The live audit
used one procurement dataset and an admin identity. It does not establish behavior
for every domain, access policy, connector, or repeated model run. Automated domain
qualification is not implemented. Typed comparisons currently cover a root SUM
against a numeric field on a directly referenced entity with a provable to-one
join. Existing untyped intent remains supported. The explicit raw generation mode
remains, but structured generation no longer silently falls back to raw output.
Application integration and deployment are separate work.
