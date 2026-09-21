"""Keep mixed-currency result summaries dimensionally valid."""


def mixed_currency_summary(rows, row_count):
    if not rows:
        return None
    keys = [key for key in rows[0] if key.split("__")[-1] == "currency_code"]
    if len(keys) != 1:
        return None
    key = keys[0]
    currencies = {row.get(key) for row in rows if row.get(key) is not None}
    if len(currencies) < 2:
        return None
    values = [name for name in rows[0] if name != key]
    if len(values) == 1 and len(rows) == row_count and len(currencies) == row_count:
        value = values[0]
        lines = [
            f"Returned {row_count} currency groups. Values are in each currency; no cross-currency total or ranking is calculated."
        ]
        lines.extend(f"- {row[key]}: {row[value]} ({value})" for row in rows)
        return "\n".join(lines)
    return (
        f"Returned {row_count} rows. The preview contains multiple currencies. "
        "Monetary values are reported in their own currencies and must not be combined or ranked without conversion."
    )
