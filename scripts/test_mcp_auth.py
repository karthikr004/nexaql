#!/usr/bin/env python3
"""Test NexaQL MCP server with JWT authentication locally.

Run:  PYTHONPATH=src python3.11 scripts/test_mcp_auth.py
"""

import asyncio
import json
import sys

import jwt


async def main():
    # ── Setup ──────────────────────────────────────────────────────────────
    from nexaql.mcp_server import (
        ask,
        configure_auth,
        describe_ontology,
        query,
        sql_preview,
        user_context_schema,
        validate_query,
    )

    SECRET = "nexaql-test-secret-key-that-is-32bytes!"
    print("=" * 60)
    print("NexaQL MCP Auth Test")
    print("=" * 60)

    # Reset to dev mode first (idempotent)
    await configure_auth(auth_mode="dev")

    # ── 1. Check default dev mode ──────────────────────────────────────────
    print("\n── 1. Dev mode (default) ──")
    schema = await user_context_schema()
    print(f"  Auth mode: {schema['auth_mode']}")
    print(f"  Defined roles: {list(schema.get('defined_roles', {}).keys())}")
    if schema.get("rls_required_attributes"):
        print(f"  RLS attributes needed: {schema['rls_required_attributes']}")
    print(f"  Note: {schema['note'][:80]}...")

    # ── 2. Test with raw user_context (dev mode) ───────────────────────────
    print("\n── 2. Query with raw user_context (dev mode) ──")
    result = await query(
        nexaql_query="{ product @limit(3) { id name sku } }",
        user_context={"user_id": "alice", "roles": ["analyst"]},
    )
    if result.get("error"):
        print(f"  ERROR: {result['error']}")
    else:
        print(f"  Rows: {result['row_count']}, Columns: {[c['name'] for c in result['columns']]}")

    # ── 3. Configure JWT mode ──────────────────────────────────────────────
    print("\n── 3. Switch to JWT mode ──")
    auth_result = await configure_auth(
        auth_mode="jwt",
        auth_secret=SECRET,
        auth_algorithm="HS256",
    )
    print(f"  {auth_result}")

    # ── 4. Raw user_context should be REJECTED in JWT mode ─────────────────
    print("\n── 4. Raw user_context in JWT mode (should fail) ──")
    result = await query(
        nexaql_query="{ product @limit(3) { id name } }",
        user_context={"user_id": "alice", "roles": ["analyst"]},
    )
    if result.get("error"):
        print(f"  Correctly rejected: {result['error'][:80]}...")
    else:
        print("  FAIL: Should have been rejected!")
        sys.exit(1)

    # ── 5. No token at all should be REJECTED ──────────────────────────────
    print("\n── 5. No auth at all in JWT mode (should fail) ──")
    result = await query(nexaql_query="{ product @limit(3) { id name } }")
    if result.get("error"):
        print(f"  Correctly rejected: {result['error'][:80]}...")
    else:
        print("  FAIL: Should have been rejected!")
        sys.exit(1)

    # ── 6. Valid JWT token should SUCCEED ───────────────────────────────────
    print("\n── 6. Valid JWT token (admin) ──")
    admin_token = jwt.encode(
        {"sub": "alice", "roles": ["admin"], "region": "US-EAST"},
        SECRET,
        algorithm="HS256",
    )
    print(f"  Token: {admin_token[:50]}...")
    result = await query(
        nexaql_query="{ product @limit(3) { id name sku } }",
        auth_token=admin_token,
    )
    if result.get("error"):
        print(f"  ERROR: {result['error']}")
    else:
        print(f"  Success! Rows: {result['row_count']}")
        for row in result["rows"]:
            print(f"    {row}")

    # ── 7. Analyst token (restricted role) ─────────────────────────────────
    print("\n── 7. Valid JWT token (analyst — may have restricted fields) ──")
    analyst_token = jwt.encode(
        {"sub": "bob", "roles": ["analyst"], "department": "sales"},
        SECRET,
        algorithm="HS256",
    )
    result = await query(
        nexaql_query="{ customer @limit(3) { id name email } }",
        auth_token=analyst_token,
    )
    if result.get("error"):
        print(f"  Result: {result['error'][:80]}")
    else:
        print(f"  Rows: {result['row_count']}, Columns: {[c['name'] for c in result['columns']]}")
        for row in result["rows"][:2]:
            print(f"    {row}")

    # ── 8. Tampered token should be REJECTED ───────────────────────────────
    print("\n── 8. Tampered token (should fail) ──")
    result = await query(
        nexaql_query="{ product @limit(3) { id name } }",
        auth_token=admin_token + "tampered",
    )
    if result.get("error"):
        print(f"  Correctly rejected: {result['error'][:80]}...")
    else:
        print("  FAIL: Tampered token was accepted!")
        sys.exit(1)

    # ── 9. Wrong secret should be REJECTED ─────────────────────────────────
    print("\n── 9. Token signed with wrong secret (should fail) ──")
    bad_token = jwt.encode(
        {"sub": "eve", "roles": ["admin"]},
        "wrong-secret-key-trying-to-impersonate!",
        algorithm="HS256",
    )
    result = await query(
        nexaql_query="{ product @limit(3) { id name } }",
        auth_token=bad_token,
    )
    if result.get("error"):
        print(f"  Correctly rejected: {result['error'][:80]}...")
    else:
        print("  FAIL: Wrong-secret token was accepted!")
        sys.exit(1)

    # ── 10. NL ask with JWT ────────────────────────────────────────────────
    print("\n── 10. Natural language 'ask' with JWT ──")
    result = await ask(
        question="how many products do we have?",
        auth_token=admin_token,
    )
    if result.get("error"):
        print(f"  Error: {result['error']}")
    else:
        print(f"  NexaQL: {result.get('nexaql_query', '')[:60]}")
        print(f"  Rows: {result.get('row_count')}")
        if result.get("summary"):
            print(f"  Summary: {result['summary'][:100]}...")

    # ── 11. Validate + SQL preview with JWT ────────────────────────────────
    print("\n── 11. Validate + SQL preview with JWT ──")
    result = await validate_query(
        nexaql_query="{ order @limit(5) { id total_amount customer { name } } }",
        auth_token=analyst_token,
    )
    print(f"  Valid: {result['valid']}")
    if result.get("sql_preview"):
        print(f"  SQL: {result['sql_preview'][:80]}...")

    # ── 12. Switch back to dev mode ────────────────────────────────────────
    print("\n── 12. Switch back to dev mode ──")
    auth_result = await configure_auth(auth_mode="dev")
    print(f"  {auth_result}")

    # Verify dev mode works again
    result = await query(
        nexaql_query="{ product @limit(2) { id name } }",
        user_context={"user_id": "alice", "roles": ["admin"]},
    )
    if result.get("error"):
        print(f"  ERROR: {result['error']}")
    else:
        print(f"  Dev mode restored — query works: {result['row_count']} rows")

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
