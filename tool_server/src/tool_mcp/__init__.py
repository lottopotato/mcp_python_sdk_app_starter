"""
MCP tool server for LLM agents (Claude Desktop / Code, your own agent host).

Unlike the app server template (../app_server, called by your own programs), this server:
- exposes small, read-only tools and does not generate answers,
- authenticates with the HTTP `Authorization: Bearer <token>` header (no token argument),
- returns compact Markdown for the model plus `structuredContent` for programs,
- reports failures as MCP tool errors (`isError: true`).

Files: backend.py (data access, purpose-specific), tools.py (tools, purpose-specific),
       server.py (assembly), auth.py (Bearer middleware, reusable).
Run:  python -m src.tool_mcp
"""
