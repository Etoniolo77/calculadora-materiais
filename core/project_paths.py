from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parents[2]
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = PROJECT_ROOT / "core"
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = PROJECT_ROOT / "docs"


def _resolve_runtime_root() -> Path:
    # Em Vercel/Lambda, /var/task é read-only. Persistência temporária deve ir para /tmp.
    if os.environ.get("VERCEL"):
        return Path(tempfile.gettempdir()) / "prj13-runtime"
    return PROJECT_ROOT


RUNTIME_ROOT = _resolve_runtime_root()
STORAGE_DIR = RUNTIME_ROOT / "storage"
LEGACY_DIR = RUNTIME_ROOT / "legacy"

OFFICIAL_DB_PATH = DATA_DIR / "materials.db"
OFFICIAL_UNIFIED_DB_PATH = DATA_DIR / "unified_db.json"
OFFICIAL_VOCAB_PATH = DATA_DIR / "vocabulary.json"
OFFICIAL_MANUAL_CORRECTIONS_PATH = STORAGE_DIR / "manual_corrections.json"
OFFICIAL_STRUCTURES_XLSX_PATH = (
    DOCS_DIR / "Referencia_Tecnica" / "ESTRUTURAS PARA CALCULADORA MATERIAS.xlsx"
)


def ensure_runtime_dirs() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    LEGACY_DIR.mkdir(parents=True, exist_ok=True)
