"""Shared discovery, generation, semantic review and bounded repair pipeline."""

import asyncio

from nexaql.chat.repair import recoverable_query_error, correction_message


async def plan_query(question, history, ontology, llm_config, *, business_context, discover, execute=None):
    from nexaql.chat.agent import generate_query_via_intent
    from nexaql.chat.query_review import review_query
    from nexaql.engine.execution import prepare_query

    context = business_context
    scoped = await discover(question, ontology, context, llm_config)
    turns = list(history)
    trace = []
    query, intent, error = "", None, None
    for attempt in range(3):

        async def generate():
            return await generate_query_via_intent(
                question=question, history=turns, ontology=scoped, llm_config=llm_config, business_context=context
            )

        candidate, response, intent = await asyncio.to_thread(lambda: asyncio.run(generate()))
        query = candidate or ""
        try:
            if not candidate:
                raise ValueError(response if "Generation validation failed:" in response else "Could not generate a query")
            prepare_query(query, ontology)
            review = await asyncio.to_thread(review_query, question, query, intent, scoped, context, llm_config)
            trace.append({"attempt": attempt + 1, "review": review})
            if not review["approved"]:
                raise ValueError("; ".join(review["issues"]) or "Semantic review did not approve the query")
            if execute is None:
                return None, None, query, {**(intent or {}), "query_review": trace}
            result, error = await execute(query)
            if error:
                raise ValueError(error)
            return result, None, query, {**(intent or {}), "query_review": trace}
        except Exception as exc:
            error = str(exc)
            trace.append({"attempt": attempt + 1, "error": error})
            if isinstance(exc, PermissionError) or not (isinstance(exc, ValueError) or recoverable_query_error(error)):
                break
            turns.extend(
                [
                    {"role": "assistant", "content": response},
                    correction_message(query, error),
                ]
            )
    return None, error, query, {**(intent or {}), "query_review": trace}
