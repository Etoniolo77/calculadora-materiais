"""
Seleção de materiais por aplicabilidade de poste (coluna "Aplicação" da aba
"Lista Consolidada" do Excel mestre).

A fonte de verdade das estruturas é o Excel. Cada material de uma estrutura tem
uma "Aplicação" que define para quais postes ele vale, por exemplo:

    "ALL"                                  -> todos os postes
    "12X600 CIRCULAR"                      -> só poste circular 12m/600daN
    "12X600 FIBRA; 12X600 CIRCULAR"        -> qualquer um dos dois
    "TODOS EXETO 11X300DT E 11X300 MADEIRA"-> todos, menos os listados
    "NO CABO AL 4C 3X70MM2+70MM2 1KV"      -> depende do cabo (variante SMTR/SMFL)

Este módulo expõe:
- parse_qty_text(): converte quantidades em texto ("4,5MTS", "2,4KG (15MTS)") em float.
- pole_signature(): normaliza o tipo de poste do engine em (altura, esforço, subtipo).
- aplicacao_matches(): decide se uma "Aplicação" vale para o poste informado.
"""

from __future__ import annotations

import re

# Subtipos de poste reconhecidos na coluna Aplicação.
_SUBTYPES = ("CIRCULAR", "FIBRA", "MADEIRA", "DT")

# Captura specs de poste tipo "12X600 CIRCULAR", "11X300DT", "14X1500CIRCULAR"
# (tolerante a separadores ausentes/errados e a falta de espaço antes do subtipo).
_POLE_SPEC_RE = re.compile(
    r"(\d{1,2})\s*[X/]\s*(\d{3,4})\s*(CIRCULAR|FIBRA|MADEIRA|DT)?",
    re.IGNORECASE,
)


def parse_qty_text(value: object) -> float:
    """Converte uma quantidade que pode vir como texto em float.

    Exemplos: "2" -> 2.0; "4,5MTS" -> 4.5; "2,4KG (15MTS)" -> 15.0 (usa a
    metragem entre parênteses quando presente); "0,040KG" -> 0.04.
    Retorna 0.0 quando não há número reconhecível.
    """
    if value is None:
        return 0.0
    text = str(value).strip().upper()
    if not text or text == "NAN":
        return 0.0

    # Caso "X KG (Y MTS)": a metragem entre parênteses é a quantidade faturável.
    paren = re.search(r"\(([^)]*?)(\d+(?:[.,]\d+)?)\s*M(?:TS|ETROS)?\s*\)", text)
    if paren:
        return float(paren.group(2).replace(",", "."))

    # Caso "4,5MTS" / "3.5 MTS": metragem direta.
    mts = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*M(?:TS|ETROS)?\b", text)
    if mts:
        return float(mts.group(1).replace(",", "."))

    # Número simples (com unidade colada como KG): pega o primeiro número.
    num = re.search(r"\d+(?:[.,]\d+)?", text)
    if num:
        return float(num.group(0).replace(",", "."))
    return 0.0


def pole_signature(pole_type: str) -> tuple[int, int, str] | None:
    """Normaliza o tipo de poste do engine em (altura, esforço, subtipo).

    Ex.: "C12/600" -> (12, 600, "CIRCULAR"); "DT11/300" -> (11, 300, "DT").
    Subtipo FIBRA/MADEIRA não é distinguível do tipo do engine; assume CIRCULAR
    quando não é DT/RT. Retorna None se não conseguir extrair altura/esforço.
    """
    p = str(pole_type or "").upper().strip()
    if not p:
        return None
    m = re.search(r"(\d{1,2})\s*[X/]\s*(\d{3,4})", p)
    if not m:
        return None
    altura, esforco = int(m.group(1)), int(m.group(2))
    if "DT" in p or "RT" in p or "DUPLO T" in p:
        subtipo = "DT"
    elif "FIBRA" in p:
        subtipo = "FIBRA"
    elif "MADEIRA" in p:
        subtipo = "MADEIRA"
    else:
        subtipo = "CIRCULAR"
    return altura, esforco, subtipo


def _spec_matches(spec: tuple[int, int, str | None], sig: tuple[int, int, str]) -> bool:
    h, e, sub = spec
    if (h, e) != (sig[0], sig[1]):
        return False
    # Subtipo ausente na spec = vale para qualquer subtipo daquele porte.
    return not sub or sub.upper() == sig[2]


def _extract_specs(text: str) -> list[tuple[int, int, str | None]]:
    specs = []
    for h, e, sub in _POLE_SPEC_RE.findall(text):
        specs.append((int(h), int(e), (sub or "").upper() or None))
    return specs


def aplicacao_matches(aplicacao: str, pole_type: str) -> bool:
    """Decide se um material com a dada "Aplicação" vale para o poste.

    Regras:
    - "" (vazia): retorna False (lacuna de cadastro; o chamador deve auditar).
    - "ALL": sempre True.
    - "TODOS EXETO <lista>": True, exceto se o poste estiver na lista.
    - "NO CABO ...": variante por cabo (SMTR/SMFL) — não filtra por poste (True).
    - lista de specs ("12X600 CIRCULAR; ..."): True se o poste casar com alguma.
    """
    a = str(aplicacao or "").strip().upper()
    if not a:
        return False
    if a == "ALL" or a == "TODOS" or a == "TODOS OS POSTES":
        return True
    if a.startswith("NO CABO") or a.startswith("N0 CABO"):
        # Aplicabilidade por cabo (variantes SMTR/SMFL), resolvida fora daqui.
        return True

    sig = pole_signature(pole_type)
    if sig is None:
        return False

    # "TODOS EXETO/EXCETO <lista>" -> vale para todos menos os listados.
    if "EXETO" in a or "EXCETO" in a:
        idx = a.find("EXETO")
        if idx < 0:
            idx = a.find("EXCETO")
        exc_text = a[idx:]
        exc_specs = _extract_specs(exc_text)
        return not any(_spec_matches(s, sig) for s in exc_specs)

    specs = _extract_specs(a)
    if not specs:
        return False
    return any(_spec_matches(s, sig) for s in specs)
