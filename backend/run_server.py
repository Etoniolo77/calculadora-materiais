from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parents[2]
    return Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculadora Materiais backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8600)
    args = parser.parse_args()

    root = _project_root()
    os.chdir(root)

    for relative in ("backend", "core"):
        path = str(root / relative)
        if path not in sys.path:
            sys.path.insert(0, path)

    from app_fastapi import app

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
