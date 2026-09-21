"""Bounded query repair shared by NexaQL execution entry points."""

import re


def recoverable_query_error(error: str | None) -> bool:
    """Only query-shape failures are repairable by changing an intent."""
    if not error:
        return False
    text = error.lower()
    if any(
        token in text
        for token in (
            "access denied",
            "permission denied",
            "not authorized",
            "timeout",
            "timed out",
            "connection",
            "authentication",
            "password",
            "cancelled",
        )
    ):
        return False
    return text.startswith(("parse error:", "validation failed:", "generation failed:")) or bool(
        re.search(
            r"column .+ does not exist|unknown (column|field)|ambiguous (column|reference)|"
            r"must appear in the group by|aggregate function|window function|"
            r"syntax error|binder error|undefined column",
            text,
        )
    )


def correction_message(query: str, error: str) -> dict[str, str]:
    return {
        "role": "user",
        "content": (
            f"Query attempt failed. Query:\n{query}\nError:\n{error}\n"
            "Correct the intent/query using the ontology and supplied business context. "
            "Preserve the requested measures, result grain, relationship paths and scope. "
            "Do not remove a condition or add a limit merely to make execution succeed. "
            "Computed output aliases are not physical database columns. "
            "Return the complete corrected output in the required format."
        ),
    }


async def execute_repair_loop(query, payload, response, history, execute, generate):
    """Three total attempts; never execute an unchanged failed candidate again."""
    turns = list(history)
    seen = set()
    error = None
    for attempt in range(3):
        if query:
            if query in seen:
                error = (
                    "Validation failed: repair repeated the same failed query. Change the invalid expression; use declared fields, not aggregation aliases. Previous error: "
                    + (error or "")
                )
            else:
                seen.add(query)
                result, error = await execute(query)
                if error is None and result is not None:
                    return result, None, query, payload
        else:
            error = "Generation failed: no valid query was produced"
        if attempt == 2 or not recoverable_query_error(error):
            break
        turns.extend([{"role": "assistant", "content": response or ""}, correction_message(query or "", error)])
        query, response, payload = await generate(turns)
    return None, error, query, payload
