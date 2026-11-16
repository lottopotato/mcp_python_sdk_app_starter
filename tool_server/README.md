# Python MCP Tool Server Starter

A starter for an MCP server whose tools are called by **LLM agents** (Claude Desktop / Code, your own agent host).
The model reads the tool descriptions, chooses the tools and writes their arguments, so the server is designed
for a model as its reader. If your own programs (a web client, internal services) call the server, use
[`../app_server`](../app_server) instead.

## Features

- Streamable HTTP endpoint (`/mcp`), stateless by default
- `Authorization: Bearer <token>` check in a pure ASGI middleware (SSE streaming stays intact); tools never take a token
- Tools with input limits in the schema (`Annotated` + `Field`) and an output schema
- Two results per call: Markdown for the model (`content`) and validated JSON for programs (`structuredContent`)
- Failures as MCP tool errors (`ToolError` → `isError: true`) with a message that tells the model what to do next
- `create_tool_server()` factory with dependency injection; tests run with in-memory parts
- Async startup/shutdown hooks (`on_startup` / `on_shutdown`) for pools and clients
- `/health` readiness probe (no token)

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/)

## Quick Start

From this folder (`tool_server/`):

```bash
uv sync
cp .env_example .env          # then set api_tokens (comma-separated), or require_auth=false for local tests
uv run python -m src.tool_mcp # http://127.0.0.1:8097/mcp
uv run pytest -q              # tests (no network, no store)
```

Check it:

```bash
curl -s http://127.0.0.1:8097/health                       # {"status":"ok",...}
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8097/mcp \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' -d '{}'   # 401
```

Claude Code: `claude mcp add --transport http my-tools http://127.0.0.1:8097/mcp --header "Authorization: Bearer <token>"`

## Project Structure

```text
src/
├── server.py           # StreamableServer: transport, uvicorn, lifespan hooks, middleware   (shared, keep as is)
├── env.py              # typed .env readers                                                  (shared)
├── modules/            # logging                                                             (shared)
└── tool_mcp/
    ├── auth.py         # Bearer middleware, token cache, verifiers                           (shared)
    ├── backend.py      # Backend interface + example MemoryBackend                           (purpose-specific)
    ├── tools.py        # register_tools(), SERVER_INSTRUCTIONS, output models                (purpose-specific)
    ├── server.py       # create_tool_server() (assembly) + build_from_settings() (.env)
    └── __main__.py     # python -m src.tool_mcp
tests/
└── test_tool_server.py # in-memory client for tools, TestClient for auth/health
```

## Making It Yours

1. **Backend** (`backend.py`): implement `Backend` for your store. Return typed records (`Item`, `Hit`) and keep
   store-specific column names inside the backend.
   - async client → `await`; blocking call that takes time → `await asyncio.to_thread(...)`;
     one shared resource (GPU model) → also an `asyncio.Lock()`.
2. **Tools** (`tools.py`): rename/replace `search_items` and `get_items`.
   - Write `description` and every argument `description` for the model; put limits in `Field(...)`.
   - Return `CallToolResult(content=[Markdown], structured_content=Model.model_dump())`.
   - Raise `ToolError("what went wrong and what to do")`; log internal details instead of returning them.
   - Update `SERVER_INSTRUCTIONS` (sent in `initialize`): workflow and how to cite.
3. **Settings** (`server.py` `build_from_settings`): create the backend, pools and clients here (not at import time);
   open/close them in `on_startup` / `on_shutdown`; add `.env` keys to `.env_example`.
4. **Auth**: `make_static_token_verifier` reads `api_tokens`; replace it with your token store and wrap it with
   `make_scope_verifier(verify, ['your:scope'])` to require a scope.
5. **Tests**: keep the tool-name check in `test_tools_are_listed_read_only_without_token_argument`; a duplicate tool
   name is only a warning in the SDK and the later tool is silently dropped.

One server per trust/resource boundary: tools that share a store or a model belong together; tools with a different
trust level (external internet access, write operations) belong in a separate server with its own port and token scope.

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `server_host` | `127.0.0.1` | Bind host |
| `server_port` | `8097` | Bind port |
| `server_stateless_http` | `true` | Stateless Streamable HTTP (no `mcp-session-id`) |
| `log_level` | `INFO` | Logging level |
| `require_auth` | `true` | Check `Authorization: Bearer` on `/mcp` |
| `api_tokens` | (empty) | Comma-separated tokens for the example static verifier |
| `token_cache_seconds` | `60` | How long an accepted token is cached (a revoked token works up to this long) |
| `enable_dns_rebinding_protection` | `false` | DNS rebinding protection (then `allowed_hosts` must include the public host) |
| `allowed_hosts` | `127.0.0.1:*,localhost:*,[::1]:*` | Allowed `Host` headers |
| `allowed_origins` | `http://127.0.0.1:*,http://localhost:*,http://[::1]:*` | Allowed `Origin` headers |

Serve it over HTTPS (reverse proxy) when it leaves the internal network: the Bearer token is a plain header.
Behind a proxy, disable response buffering (`proxy_buffering off`) so SSE streams are not held back.

## Interfaces

| Kind | Name | Description |
|---|---|---|
| MCP tool | `search_items(query, top_k=5)` | Keyword search; returns `id`, title, score, start of text |
| MCP tool | `get_items(ids)` | Full text by id (up to 5); unknown ids listed in `not_found` |
| HTTP | `GET /health` | `200 {"status":"ok"}` or `503` when the backend does not answer |
