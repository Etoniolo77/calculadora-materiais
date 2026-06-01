from __future__ import annotations

from pathlib import Path
import sys

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parents[2]
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = PROJECT_ROOT / "core"
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DATA_DIR = PROJECT_ROOT / "data"
STORAGE_DIR = PROJECT_ROOT / "storage"
DOCS_DIR = PROJECT_ROOT / "docs"
LEGACY_DIR = PROJECT_ROOT / "legacy"

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
