"""
Run the MCP tool server:

    python -m src.tool_mcp            # serves http://<server_host>:<server_port>/mcp
"""
import argparse

from .server import build_from_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP tool server for LLM agents")
    parser.parse_args()

    server = build_from_settings()
    # Blocking, synchronous preparation (e.g. loading a model) goes here: preprocessing=[model.load]
    server.preprocess_before_run(preprocessing=[])
    server.run()


if __name__ == '__main__':
    main()
