# Analytical reconciliation, first implementation

NexaQL owns the typed plan, identity/grain validation, exact-decimal aggregation,
comparison predicates, independent full-scope counts and display samples, and
execution provenance. Applications own rule definitions and measure semantics.
No domain names or procurement conditions are encoded in this module.

`execute_reconciliation(plan, query, ontology, adapter, user)` executes one
access-controlled NexaQL query. Its root is the expected entity; a direct child
edge supplies actual records. Identity fields must be declared primary keys,
and measures must belong to their declared nodes and be numeric. Only raw
fields are accepted. Limits, offsets, DISTINCT, required joins and child filters
are rejected. Repeated child identities cause a fanout error, never inflated sums.

Results include a normalized plan/hash, schema hash, query, execution ID/time,
entities checked, breach counts, totals separated by comparison and unit,
bounded finding/contributor examples, and validation gaps. Counts are computed
before sampling. Amounts remain decimal strings in JSON. Missing, non-finite,
floating-point, or incompatible-unit values are gaps, not zero/compliance.

## Current boundaries

- Verified adapters: PostgreSQL and DuckDB, single datasource/query only.
- Calculations execute in NexaQL over fetched raw records. Database aggregate
  pushdown and streaming aggregation are future performance work.
- Scope is the records visible under caller access policies, not necessarily
  every record in the underlying database. Applications must disclose this.
- A unit is compared by exact identifier. Unit conversion, currency conversion,
  and equivalence of tax/discount accounting bases require explicit application
  definitions; the engine does not infer these from similarly named columns.
- Cross-datasource reads fail until consistent snapshot support exists.
- Execution metadata supports audit correlation; it does not retain a database
  snapshot or guarantee identical results when a later rerun sees changed data.
- Reconciliation supports exceeds/below/not_equal and nonnegative tolerance.
  Missing-match, duplicate-detection and time-series operators are not yet exposed.


## Validation

`PYTHONPATH=src python -m pytest --confcutdir=tests/analytics tests/analytics`

Includes real DuckDB compilation/execution and access denial, alongside tests
for cumulative amounts, equality, credits, zero, truncation, units, and fanout.
