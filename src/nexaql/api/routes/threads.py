# Copyright (c) 2026-present NexaQL Contributors
"""Chat thread management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from nexaql import bootstrap as bs
from nexaql.api.middleware import get_user_context

router = APIRouter(prefix="/chat", tags=["chat"])


class CreateThreadRequest(BaseModel):
    title: str | None = None
    domain: str | None = None


class UpdateThreadRequest(BaseModel):
    title: str | None = None
    is_archived: bool | None = None


class ThreadResponse(BaseModel):
    id: int
    user_id: int
    title: str | None
    domain: str | None
    is_archived: bool
    created_at: str | None
    updated_at: str | None
    message_count: int = 0
    last_message: str | None = None


class MessageResponse(BaseModel):
    id: int
    thread_id: int
    role: str
    content: str
    metadata: dict[str, Any] = {}
    created_at: str | None


class ThreadDetailResponse(BaseModel):
    thread: ThreadResponse
    messages: list[MessageResponse]


async def _get_user_id(request: Request) -> int:
    user = await get_user_context(request)
    return int(user.user_id)


def _enrich_thread(thread: dict) -> dict:
    messages = bs.get_messages(thread["id"], limit=1000)
    thread["message_count"] = len(messages)
    user_msgs = [m for m in messages if m["role"] == "user"]
    thread["last_message"] = user_msgs[-1]["content"] if user_msgs else None
    if not thread["title"] and user_msgs:
        thread["title"] = user_msgs[0]["content"][:80]
    return thread


@router.get("/threads")
async def list_threads(request: Request) -> list[ThreadResponse]:
    user_id = await _get_user_id(request)
    threads = bs.list_threads(user_id)
    return [ThreadResponse(**_enrich_thread(t)) for t in threads]


@router.post("/threads")
async def create_thread(request: Request, body: CreateThreadRequest) -> ThreadResponse:
    user_id = await _get_user_id(request)
    thread = bs.create_thread(user_id, title=body.title, domain=body.domain)
    thread["message_count"] = 0
    thread["last_message"] = None
    return ThreadResponse(**thread)


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: int, request: Request) -> ThreadDetailResponse:
    user_id = await _get_user_id(request)
    thread = bs.get_thread(thread_id, user_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    messages = bs.get_messages(thread_id)
    thread["message_count"] = len(messages)
    user_msgs = [m for m in messages if m["role"] == "user"]
    thread["last_message"] = user_msgs[-1]["content"] if user_msgs else None
    return ThreadDetailResponse(
        thread=ThreadResponse(**thread),
        messages=[MessageResponse(**m) for m in messages],
    )


@router.patch("/threads/{thread_id}")
async def update_thread(thread_id: int, request: Request, body: UpdateThreadRequest) -> ThreadResponse:
    user_id = await _get_user_id(request)
    updates = body.model_dump(exclude_none=True)
    thread = bs.update_thread(thread_id, user_id, **updates)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return ThreadResponse(**_enrich_thread(thread))


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: int, request: Request) -> dict:
    user_id = await _get_user_id(request)
    deleted = bs.delete_thread(thread_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"ok": True}
