"""Filter window calculations after evaluation, before output pagination."""


def wrap_window_filter(inner, selects, order_bys, count, limit, offset, distinct=False):
    from nexaql.engine.translator import TranslateError

    projections = [select.rsplit(" AS ", 1) for select in selects]
    aliases = [alias for _, alias in projections]
    if len(set(aliases)) != len(aliases):
        raise TranslateError("Window-filtered output requires unique column aliases")
    mapping = {expr: alias for expr, alias in projections}
    lines = [
        ("SELECT DISTINCT " if distinct else "SELECT ") + ", ".join(aliases),
        "FROM (",
        inner,
        ") AS nexaql_windowed",
        "WHERE " + " AND ".join(f"__nexaql_window_filter_{i}" for i in range(count)),
    ]
    order = []
    for item in order_bys:
        expr, direction = item.rsplit(" ", 1)
        alias = mapping.get(expr, expr)
        if alias not in aliases:
            raise TranslateError("Select the ordering field when using a window filter")
        order.append(f"{alias} {direction}")
    if order:
        lines.append("ORDER BY " + ", ".join(order))
    if limit is not None:
        lines.append(f"LIMIT {limit}")
    if offset is not None:
        lines.append(f"OFFSET {offset}")
    return "\n".join(lines)
