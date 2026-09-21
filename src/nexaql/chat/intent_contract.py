"""Structural invariants that query repair may not silently discard."""


def repair_contract_errors(original, candidate):
    if not original:
        return []
    if not candidate:
        return ["Repair did not produce structured intent"]
    errors = []
    if original.get("missing_relationship") != candidate.get("missing_relationship"):
        errors.append("Repair changed the absence condition")
    if original.get("cumulative_comparison") != candidate.get("cumulative_comparison"):
        errors.append("Repair changed the typed measure, grouping relationship, threshold or comparison")
    for key in ("calc_filters",):
        required = original.get(key) or []
        actual = candidate.get(key) or []
        # Identifiers and expressions can be repaired; predicate operators remain.
        required_ops = sorted(item.get("op", "eq") for item in required)
        actual_ops = sorted(item.get("op", "eq") for item in actual)
        if required_ops != actual_ops:
            errors.append(f"Repair changed required {key} comparison operators or count")
    if original.get("output_grain") != candidate.get("output_grain"):
        errors.append("Repair changed requested output grain")
    if original.get("limit") is None and candidate.get("limit") is not None:
        errors.append("Repair added a result limit")
    return errors
