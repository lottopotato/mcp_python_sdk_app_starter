"""
Data access used by the tools. The tools depend only on the `Backend` interface, so tests can swap in a fake
and the real store (DB, search engine, external API) can change without touching tools.py.

Replace `MemoryBackend` with your own implementation of `Backend`. Rules of thumb inside a backend:
- async client (asyncpg, httpx.AsyncClient, ...): just `await` it;
- blocking call that takes time (model inference, requests, boto3, big files): `await asyncio.to_thread(fn, ...)`;
- one shared resource (a GPU model): also guard it with an `asyncio.Lock()` (or `asyncio.Semaphore(n)` for "n at a time").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass(frozen=True)
class Item:
    """One record as the tools see it. Keep store-specific column names inside the backend."""
    id: str
    title: str
    text: str
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Hit:
    item: Item
    score: float


class Backend(Protocol):
    async def search(self, query: str, top_k: int) -> list[Hit]: ...
    async def get(self, ids: list[str]) -> dict[str, Item]: ...
    async def ping(self) -> bool: ...
    async def aclose(self) -> None: ...


SAMPLE_ITEMS = [
    Item('note-001', 'Streamable HTTP', 'The MCP endpoint speaks JSON-RPC over HTTP POST; responses may stream as SSE.', ['mcp', 'transport']),
    Item('note-002', 'Bearer token', 'Clients send "Authorization: Bearer <token>"; tools never take the token as an argument.', ['auth']),
    Item('note-003', 'Tool errors', 'Raise ToolError for failures the model can act on; the client receives isError: true.', ['mcp', 'errors']),
    Item('note-004', 'Structured content', 'Return Markdown for the model and structuredContent (validated schema) for programs.', ['mcp', 'output']),
]


class MemoryBackend:
    """Example backend: keyword scoring over an in-memory list."""

    def __init__(self, items: Optional[list[Item]] = None):
        self.items = {item.id: item for item in (items if items is not None else SAMPLE_ITEMS)}

    async def search(self, query: str, top_k: int) -> list[Hit]:
        words = [word for word in query.casefold().split() if word]
        hits = []
        for item in self.items.values():
            haystack = ' '.join([item.title, item.text, *item.tags]).casefold()
            matched = sum(1 for word in words if word in haystack)
            if matched:
                hits.append(Hit(item=item, score=round(matched / len(words), 4)))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]

    async def get(self, ids: list[str]) -> dict[str, Item]:
        return {item_id: self.items[item_id] for item_id in ids if item_id in self.items}

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None
