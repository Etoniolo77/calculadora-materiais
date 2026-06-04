from __future__ import annotations

import importlib
import tempfile
from pathlib import Path


def test_vercel_uses_temp_runtime(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")

    import core.project_paths as project_paths

    project_paths = importlib.reload(project_paths)

    expected_prefix = Path(tempfile.gettempdir())
    assert project_paths.RUNTIME_ROOT.is_relative_to(expected_prefix)

    project_paths.ensure_runtime_dirs()
    assert project_paths.STORAGE_DIR.exists()
    assert project_paths.LEGACY_DIR.exists()
