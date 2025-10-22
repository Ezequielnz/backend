import os
from pathlib import Path


def main() -> None:
    # Run from home so Supabase MCP ignores project-specific .env values
    os.chdir(Path.home())
    from supabase_mcp.main import run_server

    run_server()


if __name__ == "__main__":
    main()
