"""
MCP tools for LLM agents. Conventions:
- small, read-only tools; descriptions and argument descriptions are written for the model (they are its manual),
- argument limits live in the input schema (Annotated + Field), so invalid calls never reach the function,
- the model reads compact Markdown (`content`); programs read `structuredContent` (validated output schema),
- anticipated failures raise ToolError -> `isError: true` with a message that says what to do next.
"""
from __future__ import annotations

from typing import Annotated, Optional

import logging
import time

from pydantic import BaseModel, Field
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, TextContent, ToolAnnotations

from .backend import Backend


# ======== Limits ========
SEARCH_TOP_K_DEFAULT = 5
SEARCH_TOP_K_MAX = 10
GET_MAX_IDS = 5
TEXT_MAX_CHARS = 2000

READ_ONLY = dict(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

# Sent to clients in the `initialize` response (field `instructions`): how to use the tools together.
SERVER_INSTRUCTIONS = """\
Example knowledge base of short notes.
These tools only retrieve; write the answer yourself and cite the `id` of every note you used.

Workflow:
1. search_items - keyword search; returns ids, titles and the start of each note.
2. get_items - full text of notes by id.
"""


# ======== Output models (structuredContent) ========
class SearchHit(BaseModel):
    rank: int
    id: str = Field(description="Pass to get_items; cite it in the answer.")
    title: str
    score: float
    text: str
    truncated: bool


class SearchResult(BaseModel):
    query: str
    hits: list[SearchHit]


class ItemEntry(BaseModel):
    id: str
    title: str
    tags: list[str]
    text: str


class ItemsResult(BaseModel):
    items: list[ItemEntry]
    not_found: list[str] = Field(default_factory=list)


def _clip(text: str, limit: int) -> tuple[str, bool]:
    text = (text or '').strip()
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip() + ' …', True


def register_tools(server: MCPServer, backend: Backend, logger: Optional[logging.Logger] = None) -> None:
    logger = logger or logging.getLogger(__name__)

    # ----- 1. search_items -----
    @server.tool(
        name='search_items',
        title='Search items',
        description=(
            "Keyword search over the notes. Returns the best matches with an `id`, title, score and the start "
            "of the text. Fetch full text with get_items. Rephrase and search again when the hits look off-topic."
        ),
        annotations=ToolAnnotations(title='Search items', **READ_ONLY),
    )
    async def search_items(
        query: Annotated[str, Field(min_length=1, max_length=500, description="Words to look for, e.g. 'bearer token'.")],
        top_k: Annotated[int, Field(ge=1, le=SEARCH_TOP_K_MAX, description="Number of notes to return.")] = SEARCH_TOP_K_DEFAULT,
    ) -> Annotated[CallToolResult, SearchResult]:
        started = time.monotonic()
        query = query.strip()
        if not query:
            raise ToolError("`query` is empty.")
        try:
            found = await backend.search(query, top_k)
        except Exception as e:
            logger.error(f"search_items: backend failed: {e}")
            raise ToolError("Search is temporarily unavailable. Try again later.") from None

        hits: list[SearchHit] = []
        lines = [f"# Search: {query}", ""]
        for rank, hit in enumerate(found, start=1):
            text, truncated = _clip(hit.item.text, 300)
            hits.append(SearchHit(rank=rank, id=hit.item.id, title=hit.item.title, score=hit.score, text=text, truncated=truncated))
            lines += [f"## [{rank}] {hit.item.title} (score {hit.score:.2f})", f"id: `{hit.item.id}`", '', text, '']
        if not hits:
            lines.append("No matching notes. Try other words.")

        logger.info(f"search_items: {len(hits)} hits in {time.monotonic() - started:.2f}s")
        result = SearchResult(query=query, hits=hits)
        return CallToolResult(content=[TextContent(type='text', text='\n'.join(lines).rstrip())], structured_content=result.model_dump())

    # ----- 2. get_items -----
    @server.tool(
        name='get_items',
        title='Get items by id',
        description=f"Fetch the full text of notes by the `id` values returned by search_items (up to {GET_MAX_IDS} at once).",
        annotations=ToolAnnotations(title='Get items by id', **READ_ONLY),
    )
    async def get_items(
        ids: Annotated[list[str], Field(min_length=1, max_length=GET_MAX_IDS, description="`id` values from search_items, e.g. 'note-001'.")],
    ) -> Annotated[CallToolResult, ItemsResult]:
        wanted = list(dict.fromkeys(item_id.strip() for item_id in ids if item_id.strip()))  # dedupe, keep order
        try:
            found = await backend.get(wanted)
        except Exception as e:
            logger.error(f"get_items: backend failed: {e}")
            raise ToolError("Reading the notes failed. Try again later.") from None

        not_found = [item_id for item_id in wanted if item_id not in found]
        if not found:
            raise ToolError(f"No note found for: {', '.join(not_found) or '(empty ids)'}. Use the `id` values returned by search_items.")

        entries: list[ItemEntry] = []
        lines: list[str] = []
        for item_id in wanted:
            item = found.get(item_id)
            if item is None:
                continue
            text, _ = _clip(item.text, TEXT_MAX_CHARS)
            entries.append(ItemEntry(id=item.id, title=item.title, tags=list(item.tags), text=text))
            lines += [f"## {item.title}", f"id: `{item.id}`" + (f" · tags: {', '.join(item.tags)}" if item.tags else ''), '', text, '']
        if not_found:
            lines.append(f"Not found: {', '.join(not_found)}")

        result = ItemsResult(items=entries, not_found=not_found)
        return CallToolResult(content=[TextContent(type='text', text='\n'.join(lines).rstrip())], structured_content=result.model_dump())
