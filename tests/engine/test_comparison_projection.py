"""Comparison output must retain reference-grain measures and parent labels."""
from decimal import Decimal

import duckdb
import pytest

from nexaql.chat.analytical_intent import compile_comparison
from nexaql.chat.intent import build_nexaql, parse_intent
from nexaql.chat.output_grain import apply_output_grain
from nexaql.engine.execution import prepare_query
from nexaql.engine.translator import translate
from nexaql.ontology.models import Ontology


def schema():
    def node(table, fields, edges=None):
        return dict(table=table, description='', primary_key='id',
                    fields={k: dict(type=t, description='') for k,t in fields.items()}, edges=edges or {})
    def edge(target, source, fk):
        return dict(node=target, description='', join_steps=[dict(table=target, alias_key=target,
                    condition=f'{{{source}}}.{fk} = {{{target}}}.id', description='')])
    return Ontology.model_validate(dict(version='1', domain='fixture', description='', nodes={
        'invoice_line': node('invoice_line', {'id':'integer','line_id':'integer','amount':'numeric'},
                             {'po_line':edge('po_line','invoice_line','line_id')}),
        'po_line': node('po_line', {'id':'integer','po_id':'integer','amount':'numeric'},
                       {'po':edge('po','po_line','po_id')}),
        'po': node('po', {'id':'integer','number':'string'}),
    }))


def candidate(path, **outputs):
    return parse_intent(dict(node='invoice_line', fields=['id','amount'],
        cumulative_comparison=dict(measure='amount',reference='po_line',threshold='amount',operator='gt',**outputs),
        output_grain=dict(path=path,fields=['id']),
        edges=[dict(name='po_line',fields=['id','amount'],edges=[dict(name='po',fields=['number'])])]))


def run(intent):
    ontology=schema()
    projected=apply_output_grain(compile_comparison(intent,ontology),ontology)
    query=build_nexaql(projected)
    sql=translate(prepare_query(query,ontology).ast,ontology).sql
    with duckdb.connect(':memory:') as db:
        db.execute('CREATE TABLE po(id INT, number VARCHAR)')
        db.execute('CREATE TABLE po_line(id INT, po_id INT, amount DECIMAL(10,2))')
        db.execute('CREATE TABLE invoice_line(id INT, line_id INT, amount DECIMAL(10,2))')
        db.execute("INSERT INTO po VALUES (1,'PO-A'),(2,'PO-B')")
        db.execute('INSERT INTO po_line VALUES (10,1,100),(11,1,50),(12,2,100)')
        db.execute('INSERT INTO invoice_line VALUES (1,10,60),(2,10,50),(3,11,60),(4,12,100)')
        result=db.execute(sql)
        return [dict(zip([c[0] for c in result.description],r)) for r in result.fetchall()]


def test_reference_total_and_parent_label_survive_projection():
    rows=run(candidate(['po_line'],total_alias='total_invoiced',excess_alias='excess'))
    assert len(rows)==2
    assert {r['total_invoiced'] for r in rows}=={Decimal('110'),Decimal('60')}
    assert {r['excess'] for r in rows}=={Decimal('10')}
    assert all('PO-A' in r.values() for r in rows)


def test_parent_entity_list_remains_one_row_per_parent():
    rows=run(candidate(['po_line','po']))
    assert len(rows)==1
    assert 'PO-A' in rows[0].values()
    assert Decimal('110') not in rows[0].values()


def test_reference_measure_cannot_masquerade_as_parent_measure():
    with pytest.raises(ValueError,match='Comparison totals require'):
        run(candidate(['po_line','po'],total_alias='total'))
