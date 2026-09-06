"""CLI composition root; stdout is reserved for MCP while serving."""

import argparse
import json
import sys
from pathlib import Path

from .config import Settings
from .data import DataStore
from .ontology import SemanticLayer
from .server import create_server


def main() -> int:
    parser = argparse.ArgumentParser(prog="data-mcp")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--check", action="store_true", help="Validate and list sources"
    )
    args = parser.parse_args()
    try:
        settings = Settings.load(args.config)
        if args.check:
            if settings.ontology_file is not None:
                SemanticLayer(settings)
            print(json.dumps(DataStore(settings).sources(), indent=2))
            return 0
        server = create_server(settings)
    except (OSError, ValueError):
        print("Cannot load configuration; check TOML and file access.", file=sys.stderr)
        return 2
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
