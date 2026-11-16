"""
Assembly of the MCP tool server.
`create_tool_server()` only wires given parts together (tests pass a fake backend and verifier);
`build_from_settings()` creates the real parts from the environment (.env).
"""
from __future__ import annotations

from typing import Optional

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from mcp.server.transport_security import TransportSecuritySettings

from ..server import StreamableServer
from ..modules.logging_module import LoggerLevel
from .auth import BearerAuthMiddleware, TokenCache, VerifyFunc
from .backend import Backend
from .tools import SERVER_INSTRUCTIONS, register_tools

SERVER_NAME = 'MCP Tool Server'
MCP_PATH = '/mcp'


def create_tool_server(
    backend: Backend,
    verify: Optional[VerifyFunc],
    host: str = '127.0.0.1',
    port: int = 8097,
    stateless_http: bool = True,
    transport_security: Optional[TransportSecuritySettings] = None,
    token_cache_seconds: float = 60.0,
    log_level: int = logging.INFO,
    logger: Optional[logging.Logger] = None,
) -> StreamableServer:
    """
    Args:
        verify: token -> token info (or None when rejected). None disables authentication (tests / local only).
        stateless_http: no MCP session state between requests (tools need none), so restarts and
            load balancing never produce "session not found" errors.
    """
    logger = logger or logging.getLogger(SERVER_NAME)
    server = StreamableServer(
        name=SERVER_NAME,
        host=host,
        port=port,
        streamable_http_path=MCP_PATH,
        stateless_http=stateless_http,
        transport_security=transport_security,
        instructions=SERVER_INSTRUCTIONS,
        debug=(log_level <= logging.DEBUG),
        log_level=LoggerLevel.to_str(log_level),
    )
    register_tools(server, backend, logger=logger)
    # More tool sets on the same server: call their register functions here (tool names must be unique;
    # a duplicate name is only logged as a warning and the later tool is dropped).

    @server.custom_route('/health', methods=['GET'])
    async def health(request: Request) -> Response:
        """Readiness probe (no token required): 200 when the backend answers, otherwise 503."""
        try:
            ok = bool(await backend.ping())
        except Exception:
            ok = False
        return JSONResponse({'status': 'ok' if ok else 'unavailable', 'checks': {'backend': ok}}, status_code=200 if ok else 503)

    if verify is not None:
        server.add_middleware(
            BearerAuthMiddleware,
            verify=verify,
            protected_prefix=MCP_PATH,
            cache=TokenCache(ttl_seconds=token_cache_seconds),
            logger=logger,
        )
    else:
        logger.warning("MCP tool server runs WITHOUT authentication (verify=None).")
    return server


def build_from_settings() -> StreamableServer:
    """Create the server from the environment (.env)."""
    from .. import env
    from ..modules.logging_module import LoggingModule, LoggingModuleConfig
    from .auth import make_static_token_verifier
    from .backend import MemoryBackend

    log_level = LoggerLevel.to_int(env.get_env('log_level', 'INFO'))
    logger = LoggingModule(LoggingModuleConfig(log_level=log_level)).create_rich_logger(
        name='ToolServer',
        log_file_name='logs/ToolServer.log',
        level=log_level,
    )

    # Replace with your backend (DB pools, models, API clients are created here, not at import time).
    backend = MemoryBackend()

    verify = None
    if env.get_env_bool('require_auth', default=True):
        tokens = env.get_env_list('api_tokens')
        if not tokens:
            raise SystemExit("require_auth is true but api_tokens is empty: set api_tokens in .env (or require_auth=false for local tests).")
        verify = make_static_token_verifier(tokens)

    server = create_tool_server(
        backend=backend,
        verify=verify,
        host=env.get_env('server_host', '127.0.0.1'),
        port=env.get_env_int('server_port', 8097),
        stateless_http=env.get_env_bool('server_stateless_http', default=True),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=env.get_env_bool('enable_dns_rebinding_protection', default=False),
            allowed_hosts=env.get_env_list('allowed_hosts', default=['127.0.0.1:*', 'localhost:*', '[::1]:*']),
            allowed_origins=env.get_env_list('allowed_origins', default=['http://127.0.0.1:*', 'http://localhost:*', 'http://[::1]:*']),
        ),
        token_cache_seconds=env.get_env_float('token_cache_seconds', 60.0),
        log_level=log_level,
        logger=logger,
    )

    @server.on_startup
    async def warm_up() -> None:
        # Open pools / check connections here. A failure is logged and the server still starts.
        logger.info(f"Backend ready: {await backend.ping()}")

    @server.on_shutdown
    async def shutdown() -> None:
        await backend.aclose()

    return server
