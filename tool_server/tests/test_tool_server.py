"""
Tests for the MCP tool server with in-memory parts (no network, no real store).
Tools are called through the MCP SDK in-memory client, the auth middleware through HTTP (Starlette TestClient).
"""
import pytest
from starlette.testclient import TestClient
from mcp.client import Client
from mcp.server.transport_security import TransportSecuritySettings

from src.tool_mcp.auth import make_scope_verifier, make_static_token_verifier
from src.tool_mcp.backend import Item, MemoryBackend
from src.tool_mcp.server import MCP_PATH, create_tool_server

ITEMS = [
    Item('a', 'Alpha', 'alpha bravo ' * 200, ['x']),
    Item('b', 'Bravo', 'bravo only', []),
]


class FailingBackend(MemoryBackend):
    async def search(self, query, top_k):
        raise RuntimeError('store down')

    async def ping(self):
        return False


@pytest.fixture
def server():
    return create_tool_server(backend=MemoryBackend(ITEMS), verify=None)


@pytest.mark.asyncio
async def test_tools_are_listed_read_only_without_token_argument(server):
    async with Client(server) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert set(tools) == {'search_items', 'get_items'}  # also catches tools silently dropped by a duplicate name
    for tool in tools.values():
        assert tool.annotations.read_only_hint is True
        assert 'token' not in tool.input_schema.get('properties', {})
        assert tool.output_schema is not None


@pytest.mark.asyncio
async def test_search_ranks_and_truncates(server):
    async with Client(server) as client:
        result = await client.call_tool('search_items', {'query': 'alpha bravo', 'top_k': 2})
    assert not result.is_error
    hits = result.structured_content['hits']
    assert [hit['id'] for hit in hits] == ['a', 'b']
    assert hits[0]['truncated'] is True and hits[0]['text'].endswith('…')
    assert 'id: `a`' in result.content[0].text


@pytest.mark.asyncio
async def test_schema_rejects_bad_arguments(server):
    async with Client(server) as client:
        empty = await client.call_tool('search_items', {'query': ''})
        too_many = await client.call_tool('search_items', {'query': 'x', 'top_k': 99})
    assert empty.is_error and too_many.is_error


@pytest.mark.asyncio
async def test_get_items_partial_and_missing(server):
    async with Client(server) as client:
        partial = await client.call_tool('get_items', {'ids': ['b', 'nope', 'b']})
        missing = await client.call_tool('get_items', {'ids': ['nope']})
    assert not partial.is_error
    assert [item['id'] for item in partial.structured_content['items']] == ['b']
    assert partial.structured_content['not_found'] == ['nope']
    assert missing.is_error and 'search_items' in missing.content[0].text


@pytest.mark.asyncio
async def test_backend_failure_is_tool_error():
    server = create_tool_server(backend=FailingBackend(ITEMS), verify=None)
    async with Client(server) as client:
        result = await client.call_tool('search_items', {'query': 'alpha'})
    assert result.is_error and 'store down' not in result.content[0].text  # internal details stay in the log


INIT = {
    'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
    'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 't', 'version': '0'}},
}
HEADERS = {'accept': 'application/json, text/event-stream', 'content-type': 'application/json'}


def test_bearer_auth_cache_and_health():
    calls = []
    static = make_static_token_verifier(['good'])

    async def verify(token):
        calls.append(token)
        return await static(token)

    server = create_tool_server(
        backend=MemoryBackend(ITEMS),
        verify=verify,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    server.preprocess_before_run(preprocessing=[])
    with TestClient(server.app) as http:
        assert http.get('/health').status_code == 200  # no token needed
        missing = http.post(MCP_PATH, json=INIT, headers=HEADERS)
        bad = http.post(MCP_PATH, json=INIT, headers={**HEADERS, 'authorization': 'Bearer bad'})
        good1 = http.post(MCP_PATH, json=INIT, headers={**HEADERS, 'authorization': 'Bearer good'})
        good2 = http.post(MCP_PATH, json=INIT, headers={**HEADERS, 'authorization': 'Bearer good'})
    assert missing.status_code == 401 and 'bearer' in missing.headers['www-authenticate'].lower()
    assert bad.status_code == 401
    assert good1.status_code == 200 and good2.status_code == 200
    assert calls.count('good') == 1  # cached
    assert 'Example knowledge base' in good1.text  # SERVER_INSTRUCTIONS in the initialize response


def test_health_reports_unavailable_backend():
    server = create_tool_server(backend=FailingBackend(ITEMS), verify=None)
    server.preprocess_before_run(preprocessing=[])
    with TestClient(server.app) as http:
        response = http.get('/health')
    assert response.status_code == 503 and response.json()['checks'] == {'backend': False}


@pytest.mark.asyncio
async def test_scope_verifier():
    async def store(token):
        return {'user_name': 'u', 'scopes': ['read']} if token == 't' else None

    assert await make_scope_verifier(store, ['read'])('t') == {'user_name': 'u', 'scopes': ['read']}
    assert await make_scope_verifier(store, ['write'])('t') is None
    assert await make_scope_verifier(store, ['read'])('x') is None
