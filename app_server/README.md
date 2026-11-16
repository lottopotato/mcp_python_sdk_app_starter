# Python MCP App Server Starter

A Python starter pack that you can clone and customize for projects that need an MCP server. It provides a Streamable HTTP server setup, example tools and resources, and a REST API route.

## Features

- MCP Streamable HTTP endpoint (`/mcp`)
- Example MCP tool: `Do_something`
- MCP resource that returns the project README: `file://README.md`
- REST API endpoint: `POST /api/v1/do_something`
- Server configuration through environment variables and a `.env` file

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/)

## Installation

Install the project dependencies from this folder (`app_server/`):

```bash
uv sync
```

## Running the Server

The server can be started in one of three ways. From this folder (`app_server/`), configure the environment first:

```bash
cp .env_example .env
```

### 1. Built-in Uvicorn server

Use the project runner for local development. It calls `SERVER.run()` and reads `server_host` and `server_port` from `.env`.

```bash
uv run --env-file .env python -m src.mcp_run
```

### 2. Uvicorn CLI

The ASGI app is exposed as `app` by `src.mcp_run_via_gunicorn`. Set the bind address and port with Uvicorn options; keep them consistent with the server settings in `.env`.

```bash
uv run --env-file .env uvicorn src.mcp_run_via_gunicorn:app \
  --host 127.0.0.1 \
  --port 8096
```

### 3. Gunicorn with Uvicorn workers

Install the optional Gunicorn dependency and start the server using the repository configuration:

```bash
uv sync --extra gunicorn
uv run gunicorn -c gunicorn.conf.py
```

Gunicorn reads `gunicorn_bind`, `gunicorn_workers`, and `gunicorn_timeout` from `.env`. `gunicorn_bind` controls Gunicorn's listener; make sure its host is compatible with `server_host` and the allowed-host configuration.

All three methods expose the MCP endpoint at `/mcp` and the REST route at `/api/v1/do_something`.

## Configuration

Copy `.env_example` to `.env` as described in [Running the Server](#running-the-server), then update the values as needed. `.env` is excluded from Git because it may contain sensitive information, while `.env_example` is committed as a shareable configuration template. If a setting is omitted, its default value from the table below is used.

| Environment variable | Default | Description |
|---|---|---|
| `server_host` | `127.0.0.1` | Host used by the built-in runner and MCP transport configuration |
| `server_port` | `8096` | Port used by the built-in runner |
| `server_stateless_http` | `false` | Whether to use stateless mode for HTTP transport |
| `log_level` | `INFO` | Logging level |
| `enable_dns_rebinding_protection` | `false` | Enable DNS rebinding protection |
| `allowed_hosts` | `127.0.0.1:*,localhost:*,[::1]:*` | Comma-separated list of allowed hosts for DNS rebinding protection |
| `allowed_origins` | `http://127.0.0.1:*,http://localhost:*,http://[::1]:*` | Comma-separated list of allowed origins for DNS rebinding protection |
| `allow_test_kwargs` | `false` | Allow test-only retrieval arguments |
| `gunicorn_bind` | `127.0.0.1:8000` | Gunicorn bind address and port (Gunicorn runner only) |
| `gunicorn_workers` | `1` | Number of Gunicorn worker processes |
| `gunicorn_timeout` | `600` | Gunicorn worker timeout in seconds |

`allowed_hosts` and `allowed_origins` are passed to the DNS rebinding protection settings. The current CORS middleware allows all origins, methods, and headers for development convenience. Restrict these settings before deploying to production.

## Note: Available Interfaces Form

### MCP Tool

| Name | Description | Return value |
|---|---|---|
| `Do_something` | Performs an example action | `something` |

### MCP Resource

| URI | Description |
|---|---|
| `file://README.md` | Reads and returns `README.md` from the current working directory at runtime |

### REST API

`POST /api/v1/do_something` parses a JSON or form request body. The current example implementation returns the JSON string `"Do something independently"`.

```bash
curl -X POST http://127.0.0.1:8096/api/v1/do_something \
  -H 'Content-Type: application/json' \
  -d '{}'
```

## Project Structure

```text
src/
├── configuration/  # Server configuration
├── modules/        # Shared modules and logging
├── tasks/          # MCP tools and resources, and REST API
├── utils/          # Utilities
├── mcp.py          # Server and interface configuration; exports SERVER
├── mcp_run.py      # Built-in server runner
├── mcp_run_via_gunicorn.py  # ASGI app setup for Uvicorn/Gunicorn
└── server.py       # Streamable HTTP server wrapper
```

This folder also contains `gunicorn.conf.py`, which configures the optional Gunicorn runner.

## Development Notes

- Project metadata and dependencies are managed in `pyproject.toml`.
- The `.env` file is loaded automatically.
- The default server address and port are intended for development. Review the bind address, allowed hosts, and CORS policy before exposing the server externally.
