# Copyright (c) 2026-present NexaQL Contributors
"""Tests for @required directive — parser, translator join semantics, AST transform."""

import pytest

from nexaql.engine.calc_refs import extract_required_edges
from nexaql.engine.parser import parse
from nexaql.engine.transforms import auto_require_edges
from nexaql.engine.types import RequiredDirective


class TestParserRequired:
    def test_required_parsed(self):
        q = """query Test {
          purchase_order {
            po_number
            contract_lines @required {
              unit_price
            }
          }
        }"""
        ast = parse(q)
        edge_field = ast.body.fields[1]
        assert edge_field.kind == "edge"
        directives = edge_field.node.directives
        assert any(isinstance(d, RequiredDirective) for d in directives)

    def test_required_with_other_directives(self):
        q = """query Test {
          purchase_order {
            po_number
            items @required @limit(10) {
              description
            }
          }
        }"""
        ast = parse(q)
        edge = ast.body.fields[1]
        assert edge.kind == "edge"
        types = [d.type for d in edge.node.directives]
        assert "required" in types
        assert "limit" in types

    def test_no_required_by_default(self):
        q = """query Test {
          purchase_order {
            po_number
            items {
              description
            }
          }
        }"""
        ast = parse(q)
        edge = ast.body.fields[1]
        assert edge.kind == "edge"
        assert not any(
            getattr(d, "type", None) == "required" for d in edge.node.directives
        )


class TestAutoRequireTransform:
    def test_dotted_ref_promotes_edge(self):
        q = """query Test {
          purchase_order_line {
            unit_price
            price_diff: calc(unit_price - contract_lines.agreed_unit_price)
            contract_lines {
              agreed_unit_price
            }
          }
        }"""
        ast = parse(q)
        ast = auto_require_edges(ast)
        edge = ast.body.fields[2]
        assert edge.kind == "edge"
        assert any(
            getattr(d, "type", None) == "required" for d in edge.node.directives
        )

    def test_bare_field_name_does_not_promote(self):
        """P1-2 regression: bare identifiers belong to the current node,
        not to edges that happen to expose the same field name."""
        q = """query Test {
          purchase_order_line {
            unit_price
            price_diff: calc(unit_price - agreed_unit_price)
            contract_lines {
              agreed_unit_price
            }
          }
        }"""
        ast = parse(q)
        ast = auto_require_edges(ast)
        edge = ast.body.fields[2]
        assert edge.kind == "edge"
        assert not any(
            getattr(d, "type", None) == "required" for d in edge.node.directives
        )

    def test_coalesce_skips_promotion(self):
        """P1-3 regression: COALESCE-wrapped references intentionally handle
        missing relationships and must not trigger promotion."""
        q = """query Test {
          purchase_order_line {
            unit_price
            safe_price: calc(COALESCE(contract_lines.agreed_unit_price, 0))
            contract_lines {
              agreed_unit_price
            }
          }
        }"""
        ast = parse(q)
        ast = auto_require_edges(ast)
        edge = ast.body.fields[2]
        assert edge.kind == "edge"
        assert not any(
            getattr(d, "type", None) == "required" for d in edge.node.directives
        )

    def test_nullif_skips_promotion(self):
        q = """query Test {
          purchase_order_line {
            unit_price
            adjusted: calc(NULLIF(contract_lines.agreed_unit_price, 0))
            contract_lines {
              agreed_unit_price
            }
          }
        }"""
        ast = parse(q)
        ast = auto_require_edges(ast)
        edge = ast.body.fields[2]
        assert not any(
            getattr(d, "type", None) == "required" for d in edge.node.directives
        )

    def test_no_calc_no_promotion(self):
        q = """query Test {
          purchase_order {
            po_number
            items {
              description
            }
          }
        }"""
        ast = parse(q)
        ast = auto_require_edges(ast)
        edge = ast.body.fields[1]
        assert edge.kind == "edge"
        assert not any(
            getattr(d, "type", None) == "required" for d in edge.node.directives
        )

    def test_already_required_not_duplicated(self):
        q = """query Test {
          purchase_order_line {
            unit_price
            price_diff: calc(unit_price - contract_lines.agreed_unit_price)
            contract_lines @required {
              agreed_unit_price
            }
          }
        }"""
        ast = parse(q)
        ast = auto_require_edges(ast)
        edge = ast.body.fields[2]
        required_count = sum(
            1 for d in edge.node.directives if getattr(d, "type", None) == "required"
        )
        assert required_count == 1

    def test_multiple_dotted_refs_promote_multiple_edges(self):
        q = """query Test {
          purchase_order_line {
            unit_price
            total_diff: calc(contract_lines.agreed_unit_price - supplier.discount_rate)
            contract_lines {
              agreed_unit_price
            }
            supplier {
              discount_rate
            }
          }
        }"""
        ast = parse(q)
        ast = auto_require_edges(ast)
        cl_edge = ast.body.fields[2]
        sup_edge = ast.body.fields[3]
        assert any(
            getattr(d, "type", None) == "required" for d in cl_edge.node.directives
        )
        assert any(
            getattr(d, "type", None) == "required" for d in sup_edge.node.directives
        )

    def test_unselected_edge_synthesized_with_required(self):
        """P2-1 regression: a calc references an edge that has no EdgeField
        selection. The transform must synthesize a @required edge."""
        q = """query Test {
          purchase_order_line {
            line_id
            diff: calc(unit_price - contract_line.unit_price)
          }
        }"""
        ast = parse(q)
        ast = auto_require_edges(ast)
        edge_fields = [f for f in ast.body.fields if f.kind == "edge"]
        assert len(edge_fields) == 1
        synth = edge_fields[0]
        assert synth.node.name == "contract_line"
        assert any(
            getattr(d, "type", None) == "required" for d in synth.node.directives
        )

    def test_partial_null_tolerant_promotes_unprotected_ref(self):
        """P2-2 regression: NULLIF protects a root-field division, but
        the edge ref outside it must still be promoted."""
        q = """query Test {
          purchase_order_line {
            unit_price
            pct_diff: calc((unit_price - contract_line.unit_price) / NULLIF(unit_price, 0))
            contract_line {
              unit_price
            }
          }
        }"""
        ast = parse(q)
        ast = auto_require_edges(ast)
        edge = ast.body.fields[2]
        assert edge.kind == "edge"
        assert any(
            getattr(d, "type", None) == "required" for d in edge.node.directives
        )

    def test_ref_inside_coalesce_still_protected(self):
        """The edge ref inside COALESCE must NOT be promoted even when
        another ref outside would be."""
        q = """query Test {
          purchase_order_line {
            unit_price
            val: calc(supplier.rate - COALESCE(contract_line.unit_price, 0))
            contract_line {
              unit_price
            }
            supplier {
              rate
            }
          }
        }"""
        ast = parse(q)
        ast = auto_require_edges(ast)
        cl_edge = [f for f in ast.body.fields if f.kind == "edge" and f.node.name == "contract_line"][0]
        sup_edge = [f for f in ast.body.fields if f.kind == "edge" and f.node.name == "supplier"][0]
        assert not any(
            getattr(d, "type", None) == "required" for d in cl_edge.node.directives
        )
        assert any(
            getattr(d, "type", None) == "required" for d in sup_edge.node.directives
        )


class TestExtractRequiredEdges:
    def test_simple_dotted_ref(self):
        assert extract_required_edges("a - edge.field") == {"edge"}

    def test_bare_ident_ignored(self):
        assert extract_required_edges("a + b") == set()

    def test_coalesce_protects(self):
        assert extract_required_edges("COALESCE(edge.field, 0)") == set()

    def test_nullif_on_root_does_not_suppress_edge(self):
        assert extract_required_edges("edge.price / NULLIF(qty, 0)") == {"edge"}

    def test_nested_null_tolerant(self):
        assert extract_required_edges("COALESCE(NULLIF(edge.x, 0), 1)") == set()

    def test_mixed_protected_and_unprotected(self):
        result = extract_required_edges("a.x + COALESCE(b.y, 0)")
        assert result == {"a"}

    def test_url_in_string_literal_ignored(self):
        assert extract_required_edges("CONCAT('https://example.com/', line_id)") == set()

    def test_dotted_string_ignored(self):
        assert extract_required_edges("CONCAT('prefix.suffix', edge.field)") == {"edge"}

    def test_escaped_quote_in_string(self):
        assert extract_required_edges("CONCAT('it''s a.test', val)") == set()

    def test_parens_inside_string_ignored(self):
        assert extract_required_edges("COALESCE(edge.x, '(none)')") == set()

    def test_real_ref_outside_string_with_dotted_string(self):
        result = extract_required_edges("edge.field + CONCAT('a.b', 'c.d')")
        assert result == {"edge"}
