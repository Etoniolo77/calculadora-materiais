#!/usr/bin/env python3
"""
Snapshot per-poste do extrator para regressao.

Gera/compara um JSON com a saida de ProjectExtractor.extract_with_metadata()
para todos os PDFs de teste. Captura, por poste: tipo (Pole), estruturas (Est
ordenadas) e trafo. Permite detectar drops de poste, duplicacao de estrutura e
mudancas de tipologia entre versoes do extrator.

Uso:
  python scripts/extractor_snapshot.py --save baseline.json
  python scripts/extractor_snapshot.py --compare baseline.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.extractor import ProjectExtractor  # noqa: E402

PDF_DIR = (
    PROJECT_ROOT
    / "docs"
    / "Diagramas de Testes"
    / "Diagramas para iniciar os trabalhos de revisão da calculadora"
)


def _pnum(pid: str) -> int:
    m = re.search(r"\d+", str(pid))
    return int(m.group()) if m else 9999


def snapshot() -> dict:
    out: dict = {}
    for pdf in sorted(PDF_DIR.glob("*.pdf")):
        try:
            ext = ProjectExtractor(str(pdf))
            data = ext.extract_with_metadata()
            pm = data.get("pole_map", {}) or {}
            poles = {}
            for pid in sorted(pm.keys(), key=_pnum):
                d = pm[pid]
                poles[pid] = {
                    "Pole": d.get("Pole"),
                    "Est": sorted([str(e) for e in (d.get("Est") or [])]),
                    "Trafo": d.get("Trafo"),
                }
            out[pdf.name] = {
                "pole_ids": sorted(pm.keys(), key=_pnum),
                "poles": poles,
            }
        except Exception as exc:  # noqa: BLE001
            out[pdf.name] = {"error": str(exc)}
    return out


def _diff(base: dict, curr: dict) -> list[str]:
    msgs: list[str] = []
    for name in sorted(set(base) | set(curr)):
        b = base.get(name)
        c = curr.get(name)
        if b is None:
            msgs.append(f"[NOVO PDF] {name}")
            continue
        if c is None:
            msgs.append(f"[PDF SUMIU] {name}")
            continue
        if "error" in b or "error" in c:
            if b.get("error") != c.get("error"):
                msgs.append(f"[ERRO mudou] {name}: {b.get('error')} -> {c.get('error')}")
            continue
        b_ids, c_ids = set(b["pole_ids"]), set(c["pole_ids"])
        if b_ids != c_ids:
            dropped = sorted(b_ids - c_ids, key=_pnum)
            added = sorted(c_ids - b_ids, key=_pnum)
            if dropped:
                msgs.append(f"[POSTE DROP] {name}: -{dropped}")
            if added:
                msgs.append(f"[POSTE NOVO] {name}: +{added}")
        for pid in sorted(b_ids & c_ids, key=_pnum):
            bp, cp = b["poles"][pid], c["poles"][pid]
            if bp != cp:
                msgs.append(f"[MUDOU] {name} {pid}: {bp} -> {cp}")
    return msgs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", type=Path)
    ap.add_argument("--compare", type=Path)
    args = ap.parse_args()

    curr = snapshot()

    if args.save:
        args.save.write_text(json.dumps(curr, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] Snapshot salvo: {args.save} ({len(curr)} PDFs)")

    if args.compare:
        base = json.loads(args.compare.read_text(encoding="utf-8"))
        diffs = _diff(base, curr)
        if not diffs:
            print("[OK] Sem diferencas em relacao ao baseline.")
        else:
            print(f"[DIFF] {len(diffs)} diferenca(s):")
            for m in diffs:
                print("  " + m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
