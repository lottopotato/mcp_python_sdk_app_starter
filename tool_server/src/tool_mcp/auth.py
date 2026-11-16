"""
`Authorization: Bearer <token>` check for the MCP endpoint.

Agents must not see or pass the token as a tool argument; the host (Claude Desktop / Code, your agent)
sends it with every HTTP request instead. Verification is a plain async function (`VerifyFunc`), so any
token store can be plugged in; its result is cached briefly (keyed by a hash, never the token itself).
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Iterable, Optional

import hashlib
import hmac
import json
import logging
import time

from starlette.types import ASGIApp, Receive, Scope, Send

# token -> token info ({'user_name': ..., 'scopes': [...]}) or None / False when rejected
VerifyFunc = Callable[[str], Awaitable[Optional[dict[str, Any]] | bool]]


class TokenCache:
    def __init__(self, ttl_seconds: float = 60.0, max_entries: int = 1024):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[str, tuple[float, dict[str, Any]]] = {}

    @staticmethod
    def key(token: str) -> str:
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    def get(self, token: str) -> Optional[dict[str, Any]]:
        entry = self._entries.get(self.key(token))
        if entry is None:
            return None
        if time.monotonic() - entry[0] > self.ttl_seconds:
            self._entries.pop(self.key(token), None)
            return None
        return entry[1]

    def put(self, token: str, info: dict[str, Any]) -> None:
        if len(self._entries) >= self.max_entries:
            # Drop the oldest entries; the cache is only an optimisation.
            for key, _ in sorted(self._entries.items(), key=lambda item: item[1][0])[: self.max_entries // 4 or 1]:
                self._entries.pop(key, None)
        self._entries[self.key(token)] = (time.monotonic(), info)


def make_static_token_verifier(tokens: Iterable[str], user_name: str = 'static') -> VerifyFunc:
    """Accept a fixed set of tokens (e.g. `api_tokens` in .env). Enough for a start; replace with a real store."""
    allowed = [token for token in tokens if token]

    async def verify(token: str) -> Optional[dict[str, Any]]:
        matched = False
        for candidate in allowed:  # constant-time compare against every token
            matched |= hmac.compare_digest(candidate.encode('utf-8'), token.encode('utf-8'))
        return {'user_name': user_name, 'scopes': []} if matched else None

    return verify


def make_scope_verifier(verify_token: VerifyFunc, required_scopes: Optional[Iterable[str]]) -> VerifyFunc:
    """Wrap a verifier whose info carries `scopes`: the token must hold at least one of `required_scopes`."""
    scopes_needed = list(required_scopes or [])

    async def verify(token: str) -> Optional[dict[str, Any]]:
        info = await verify_token(token)
        if not info:
            return None
        info = info if isinstance(info, dict) else {}
        if scopes_needed and not any(scope in (info.get('scopes') or []) for scope in scopes_needed):
            return None
        return {'user_name': info.get('user_name'), 'scopes': list(info.get('scopes') or [])}

    return verify


class BearerAuthMiddleware:
    """Pure ASGI middleware (keeps SSE streaming intact). Only paths under `protected_prefix` are checked."""

    def __init__(
        self,
        app: ASGIApp,
        verify: VerifyFunc,
        protected_prefix: str = '/mcp',
        cache: Optional[TokenCache] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.app = app
        self.verify = verify
        self.protected_prefix = protected_prefix.rstrip('/') or '/'
        self.cache = cache or TokenCache()
        self.logger = logger or logging.getLogger(__name__)

    def _protected(self, path: str) -> bool:
        return path == self.protected_prefix or path.startswith(self.protected_prefix + '/')

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or not self._protected(scope.get('path', '')) or scope.get('method') == 'OPTIONS':
            await self.app(scope, receive, send)
            return

        token = None
        for name, value in scope.get('headers', []):
            if name == b'authorization':
                scheme, _, credentials = value.decode('latin-1').partition(' ')
                if scheme.lower() == 'bearer' and credentials.strip():
                    token = credentials.strip()
                break

        if token is None:
            await self._reject(send, 'missing_token', 'Send the token as "Authorization: Bearer <token>".')
            return

        info = self.cache.get(token)
        if info is None:
            try:
                info = await self.verify(token)
            except Exception as e:
                self.logger.error(f"Token verification error: {e}")
                await self._reject(send, 'verification_failed', 'Token verification is temporarily unavailable.', status=503)
                return
            if not info:
                self.logger.warning("Rejected request with an invalid or insufficient token.")
                await self._reject(send, 'invalid_token', 'The token is invalid, expired, revoked or lacks the required scope.')
                return
            self.cache.put(token, info)

        scope.setdefault('state', {})['auth'] = info
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send: Send, error: str, description: str, status: int = 401) -> None:
        body = json.dumps({'error': error, 'error_description': description}).encode('utf-8')
        headers = [
            (b'content-type', b'application/json'),
            (b'content-length', str(len(body)).encode('ascii')),
        ]
        if status == 401:
            headers.append((b'www-authenticate', f'Bearer error="{error}"'.encode('ascii')))
        await send({'type': 'http.response.start', 'status': status, 'headers': headers})
        await send({'type': 'http.response.body', 'body': body})
