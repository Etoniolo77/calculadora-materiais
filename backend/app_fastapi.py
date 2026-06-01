from __future__ import annotations

import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

def _resolve_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parents[2]
    return Path(__file__).resolve().parents[1]


PROJECT_ROOT = _resolve_project_root()
CORE_DIR = PROJECT_ROOT / "core"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from engine import MaterialEngine  # noqa: E402
from extractor import ProjectExtractor  # noqa: E402
from final_report import PDFReport  # noqa: E402
from validators import TechnicalValidator  # noqa: E402

app = FastAPI(title="Calculadora Materiais API", version="1.0.0")
app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")

_engine_lock = threading.Lock()
_engine: MaterialEngine | None = None

UPDATE_CONFIG_PATH = PROJECT_ROOT / "update" / "update_config.json"
APP_VERSION_PATH = PROJECT_ROOT / "app_version.json"
AUTH_CONFIG_PATH = PROJECT_ROOT / "auth" / "auth_config.json"
AUTH_SESSION_COOKIE = "calc_local_auth"
AUTH_SECRET = os.environ.get("CALC_AUTH_SECRET", "calc-local-auth-secret")


def _load_auth_config() -> dict[str, str]:
    defaults = {
        "allowed_email_domain": "eletromarquez.com.br",
        "pin_code": "Eletro2026",
    }
    if not AUTH_CONFIG_PATH.exists():
        return defaults
    data = json.loads(AUTH_CONFIG_PATH.read_text(encoding="utf-8"))
    return {
        "allowed_email_domain": str(
            data.get("allowed_email_domain", defaults["allowed_email_domain"])
        )
        .strip()
        .lower(),
        "pin_code": str(data.get("pin_code", defaults["pin_code"])).strip(),
    }


def _sign_session(email: str) -> str:
    sig = hmac.new(
        AUTH_SECRET.encode("utf-8"), email.encode("utf-8"), digestmod="sha256"
    ).hexdigest()
    return f"{email}|{sig}"


def _verify_session(token: str | None) -> str | None:
    if not token or "|" not in token:
        return None
    email, sig = token.rsplit("|", 1)
    expected = hmac.new(
        AUTH_SECRET.encode("utf-8"), email.encode("utf-8"), digestmod="sha256"
    ).hexdigest()
    if hmac.compare_digest(sig, expected):
        return email
    return None


class LocalAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        public_paths = (
            "/login",
            "/auth/local-login",
            "/auth/logout",
            "/health",
            "/api/version",
            "/api/structures",
            "/frontend/",
        )
        if any(path == p or path.startswith(p) for p in public_paths):
            return await call_next(request)
        session = _verify_session(request.cookies.get(AUTH_SESSION_COOKIE))
        if not session:
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Sessao expirada. Faca login novamente."},
                )
            return RedirectResponse(url="/login")
        return await call_next(request)


app.add_middleware(LocalAuthMiddleware)


def _parse_version(value: str) -> tuple[int, ...]:
    clean = str(value or "").strip().lstrip("vV")
    parts = re.findall(r"\d+", clean)
    if not parts:
        return (0,)
    return tuple(int(p) for p in parts)


def _load_local_version() -> str:
    if not APP_VERSION_PATH.exists():
        return "0.0.0"
    data = json.loads(APP_VERSION_PATH.read_text(encoding="utf-8"))
    return str(data.get("version", "0.0.0"))


def _load_update_config() -> dict[str, Any]:
    if not UPDATE_CONFIG_PATH.exists():
        raise HTTPException(
            status_code=500, detail="Arquivo update/update_config.json nao encontrado."
        )
    return json.loads(UPDATE_CONFIG_PATH.read_text(encoding="utf-8"))


def _resolve_remote_release() -> dict[str, str]:
    config = _load_update_config()
    manifest_url = str(config.get("manifest_url", "")).strip()
    if not manifest_url:
        raise HTTPException(
            status_code=400,
            detail="Configure manifest_url em update/update_config.json.",
        )
    if "SEU_SHAREPOINT" in manifest_url.upper() or "SEU-ENDPOINT" in manifest_url.upper():
        raise HTTPException(
            status_code=400,
            detail="Atualizacao ainda nao configurada. Informe um manifesto privado real em update_config.json.",
        )

    import urllib.request
    from urllib.parse import urljoin

    manifest_is_remote = bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", manifest_url))

    try:
        manifest_path = Path(manifest_url)
        if manifest_path.exists():
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            req = urllib.request.Request(
                manifest_url,
                headers={"User-Agent": "calculadora-materiais-updater"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha ao consultar manifesto privado: {exc}"
        ) from exc

    remote_version = str(payload.get("version", "")).strip().lstrip("vV")
    package_url = str(payload.get("package_url", "")).strip()
    if not remote_version or not package_url:
        raise HTTPException(
            status_code=400,
            detail="Manifesto invalido: campos version e package_url sao obrigatorios.",
        )
    package_is_remote = bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", package_url))
    if not package_is_remote and not Path(package_url).is_absolute():
        if manifest_is_remote:
            package_url = urljoin(manifest_url, package_url)
        else:
            package_url = str((Path(manifest_url).parent / package_url).resolve())

    return {"remote_version": remote_version, "package_url": package_url}


def _clean_quantity(value: Any) -> float | int:
    """Normaliza quantidade para evitar artefatos como 36.260000000000005."""
    try:
        q = float(value)
    except (TypeError, ValueError):
        return 0
    if abs(q) < 1e-9:
        return 0
    if abs(q - round(q)) < 1e-9:
        return int(round(q))
    return round(q, 3)


def _get_engine() -> MaterialEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = MaterialEngine()
            _engine.load_databases()
    return _engine


def _normalize_pole_label(value: Any) -> str:
    raw = str(value or "").upper().strip()
    if not raw:
        return "Desconhecido"
    m = re.search(
        r"(DT\d{1,2}/\d{3,4}|DI\d{1,2}/\d{3,4}|D\d{1,2}/\d{3,4}|C\d{1,2}/\d{3,4}|M\d{1,2}/\d{3,4}|\d{1,2}/\d{3,4})",
        raw,
    )
    if not m:
        return raw
    norm = m.group(1).replace("X", "/").replace(" ", "")
    if norm.startswith("DI"):
        norm = "DT" + norm[2:]
    elif norm.startswith("M"):
        norm = "C" + norm[1:]
    elif re.match(r"^\d{1,2}/\d{3,4}$", norm):
        norm = f"C{norm}"
    return norm


def _normalize_structure_list(structures: Any) -> list[str]:
    if isinstance(structures, list):
        raw_items = structures
    elif isinstance(structures, str):
        raw_items = re.split(r"[,+;]", structures)
    else:
        raw_items = []
    normalized: list[str] = []
    for item in raw_items:
        token = str(item).upper().strip()
        token = re.sub(r"\s+", "", token)
        token = token.replace("(E)", "").replace("(R)", "")
        if not token or re.match(r"^P\d+$", token):
            continue
        parts = re.split(r"(?<=[A-Z0-9])[\-+/](?=[A-Z0-9])", token)
        for part in parts:
            part = part.strip()
            if not part or re.match(r"^P\d+$", part):
                continue
            if part not in normalized:
                normalized.append(part)
    return normalized


def _normalize_id_codes(prefix: str, raw_codes: Any) -> list[str]:
    prefix_up = str(prefix or "").upper().strip()
    if not prefix_up:
        return []
    if isinstance(raw_codes, list):
        items = raw_codes
    elif isinstance(raw_codes, str):
        items = re.split(r"[;,]+", raw_codes)
    else:
        items = []
    out: list[str] = []
    for item in items:
        raw = str(item or "").upper().strip()
        if not raw:
            continue
        cleaned = re.sub(r"\s+", "", raw)
        m = re.match(rf"^{prefix_up}[\-:]*([0-9]{{6}})$", cleaned)
        if not m:
            continue
        code = f"{prefix_up}{m.group(1)}"
        if code not in out:
            out.append(code)
    return out


def _build_extract_recommendations(
    poles: list[dict[str, Any]],
    cables: list[dict[str, Any]],
    validation: dict[str, Any],
) -> list[dict[str, str]]:
    recs: list[dict[str, str]] = []
    unknown = [
        p.get("id", "")
        for p in poles
        if str(p.get("Pole", "")).upper() in {"", "DESCONHECIDO"}
    ]
    if unknown:
        recs.append(
            {
                "level": "alta",
                "title": "Postes sem tipologia",
                "message": f"Postes {', '.join(unknown[:6])} ficaram sem tipo; revisar OCR do diagrama para evitar erro de ferragens.",
            }
        )
    empty_struct = [p.get("id", "") for p in poles if not p.get("Est")]
    if empty_struct:
        recs.append(
            {
                "level": "media",
                "title": "Postes sem estruturas",
                "message": f"Postes {', '.join(empty_struct[:6])} sem estrutura; validar antes do cálculo para reduzir VERIFICAR.",
            }
        )
    suspicious = []
    for p in poles:
        for est in p.get("Est", []):
            tk = str(est).upper()
            if re.match(r"^(X\d+AX|P0?\d+)$", tk):
                suspicious.append(f"{p.get('id')}: {tk}")
    if suspicious:
        recs.append(
            {
                "level": "alta",
                "title": "Estruturas suspeitas",
                "message": f"Detectado ruído de OCR em estruturas ({'; '.join(suspicious[:5])}).",
            }
        )
    if not cables:
        recs.append(
            {
                "level": "baixa",
                "title": "Sem cabos extraídos",
                "message": "Nenhum cabo encontrado automaticamente; confirme se o diagrama possui legenda de cabos.",
            }
        )
    return recs


def _build_calculation_recommendations(
    pole_map: dict[str, Any],
    bom_rows: list[dict[str, Any]],
    validation: dict[str, Any] | None = None,
    structure_audit: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    recs: list[dict[str, str]] = []
    total_poles = max(1, len(pole_map))
    verificar = [
        r
        for r in bom_rows
        if str(r.get("Código SAP", "")).upper().startswith("VERIFICAR")
    ]
    if verificar:
        recs.append(
            {
                "level": "alta",
                "title": "Itens pendentes de SAP",
                "message": f"A BOM gerou {len(verificar)} item(ns) VERIFICAR; revisar estruturas e aliases para fechar o de-para.",
            }
        )
    cinta_qty = 0.0
    for row in bom_rows:
        desc = str(row.get("Descrição", "")).upper()
        if "CINTA" in desc or "BRACADEIRA" in desc or "BRAÇADEIRA" in desc:
            cinta_qty += float(row.get("Quantidade", 0) or 0)
    if cinta_qty > total_poles * 8:
        recs.append(
            {
                "level": "media",
                "title": "Possível excesso de cintas",
                "message": f"Quantidade total de cintas/bracadeiras ({_clean_quantity(cinta_qty)}) está alta para {total_poles} poste(s); validar estruturas por poste.",
            }
        )
    parafuso_qty = 0.0
    for row in bom_rows:
        desc = str(row.get("Descrição", "")).upper()
        if "PARAFUSO" in desc and "16" in desc:
            parafuso_qty += float(row.get("Quantidade", 0) or 0)
    if parafuso_qty == 0 and cinta_qty > 0:
        recs.append(
            {
                "level": "media",
                "title": "Parafuso de fixação ausente",
                "message": "Há cintas na BOM sem parafuso M16 correspondente; verificar regra de fixação por tipologia de poste.",
            }
        )
    if validation and int(validation.get("errors", 0) or 0) > 0:
        issues = validation.get("issues", [])
        error_msgs = "; ".join(
            i.get("message", "") for i in issues if i.get("severity") == "error"
        )
        detail = f" ({error_msgs})" if error_msgs else ""
        recs.append(
            {
                "level": "media",
                "title": "Avisos técnicos na BOM",
                "message": f"A validação apontou {validation['errors']} inconsistência(s) técnica(s){detail}. A BOM foi gerada normalmente; revise os itens sinalizados.",
            }
        )
    if structure_audit and not bool(structure_audit.get("ok", True)):
        recs.append(
            {
                "level": "alta",
                "title": "Divergência estrutura × cálculo",
                "message": (
                    "Foram encontradas divergências entre as estruturas extraídas "
                    "e os materiais/quantidades calculados. "
                    f"Ocorrências: {int(structure_audit.get('mismatch_count', 0) or 0)}."
                ),
            }
        )
    return recs


def _build_quality_gate(
    bom_rows: list[dict[str, Any]],
    validation: dict[str, Any] | None = None,
    override_enabled: bool = False,
    override_reason: str = "",
    low_conf_review_confirmed: bool = False,
) -> dict[str, Any]:
    validation = validation or {}
    errors = int(validation.get("errors", 0) or 0)
    warnings = int(validation.get("warnings", 0) or 0)
    verificar_count = sum(
        1
        for row in bom_rows
        if str(row.get("Código SAP", "")).upper().startswith("VERIFICAR")
    )
    low_conf_count = sum(
        1 for row in bom_rows if float(row.get("Confiança", 1.0) or 1.0) < 0.70
    )
    override_reason = str(override_reason or "").strip()
    override_valid = bool(override_enabled and len(override_reason) >= 10)

    blocked_reasons: list[str] = []
    if errors > 0 and not override_valid:
        blocked_reasons.append("erros_criticos")
    if low_conf_count > 0 and not low_conf_review_confirmed:
        blocked_reasons.append("baixa_confianca_sem_confirmacao")

    return {
        "errors": errors,
        "warnings": warnings,
        "verificar_count": verificar_count,
        "low_confidence_count": low_conf_count,
        "override_enabled": bool(override_enabled),
        "override_reason": override_reason,
        "override_valid": override_valid,
        "low_conf_review_confirmed": bool(low_conf_review_confirmed),
        "blocked": len(blocked_reasons) > 0,
        "blocked_reasons": blocked_reasons,
    }


def _group_bom_rows(material_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not material_rows:
        return []
    df = pd.DataFrame(material_rows)
    if df.empty:
        return []
    if "Confiança" not in df.columns:
        df["Confiança"] = 1.0
    grouped = (
        df.groupby(["Código SAP", "Descrição"], as_index=False)
        .agg({"Quantidade": "sum", "Confiança": "min"})
        .sort_values(by=["Código SAP", "Descrição"], ascending=[True, True])
    )
    rows = grouped.to_dict(orient="records")
    for row in rows:
        row["Quantidade"] = _clean_quantity(row.get("Quantidade", 0))
        row["Confiança"] = round(float(row.get("Confiança", 1.0) or 1.0), 2)
    return rows


def _default_pole_payload(pole: dict[str, Any]) -> dict[str, Any]:
    estai_val = pole.get("Estai", 0)
    if isinstance(estai_val, dict):
        estai = {
            "Type": str(estai_val.get("Type", "CC - 14M")),
            "Qtd": int(estai_val.get("Qtd", 0) or 0),
        }
    else:
        estai = {"Type": "CC - 14M", "Qtd": int(estai_val or 0)}

    para_raio_val = pole.get("ParaRaio", {"Type": "CRUZETA", "Qtd": 0})
    if isinstance(para_raio_val, dict):
        para_raio = {
            "Type": str(para_raio_val.get("Type", "CRUZETA")),
            "Qtd": int(para_raio_val.get("Qtd", 0) or 0),
        }
    else:
        para_raio = {"Type": "CRUZETA", "Qtd": int(para_raio_val or 0)}

    aterr_val = pole.get("Aterramento", {"Qtd": 0})
    if isinstance(aterr_val, dict):
        aterramento = {"Qtd": int(aterr_val.get("Qtd", 0) or 0)}
    else:
        aterramento = {"Qtd": int(aterr_val or 0)}

    ramal_val = pole.get("Ramal", {"Type": None, "Qtd": 0.0})
    if isinstance(ramal_val, dict):
        ramal = {
            "Type": ramal_val.get("Type"),
            "Qtd": float(ramal_val.get("Qtd", 0) or 0),
        }
    else:
        ramal = {"Type": None, "Qtd": float(ramal_val or 0)}

    structures = _normalize_structure_list(pole.get("Est", []))
    estf_codes = _normalize_id_codes("ESTF", pole.get("EstfCodes", []))
    et_codes = _normalize_id_codes("ET", pole.get("EtCodes", []))

    return {
        "Pole": _normalize_pole_label(pole.get("Pole", "Desconhecido")),
        "Est": structures,
        "Trafo": pole.get("Trafo"),
        "EstfCodes": estf_codes,
        "EtCodes": et_codes,
        "Chave": pole.get("Chave"),
        "Estai": estai,
        "ParaRaio": para_raio,
        "Aterramento": aterramento,
        "Ramal": ramal,
    }


def _normalize_poles_from_map(pole_map: dict[str, Any]) -> list[dict[str, Any]]:
    poles: list[dict[str, Any]] = []
    for p_id, data in sorted(pole_map.items(), key=lambda kv: kv[0]):
        row = {"id": p_id}
        row.update(_default_pole_payload(data))
        poles.append(row)
    return poles


def _normalize_poles_to_map(poles: list[dict[str, Any]]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for idx, item in enumerate(poles, start=1):
        p_id = str(item.get("id", f"P{idx}")).upper().strip() or f"P{idx}"
        mapped[p_id] = _default_pole_payload(item)
    return mapped


def _normalize_cables(cables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for cable in cables:
        desc = str(cable.get("Desc", "")).strip()
        if not desc:
            continue
        try:
            qty = float(str(cable.get("Qtd", 0)).replace(",", "."))
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0:
            continue
        normalized.append(
            {
                "Tipo": str(cable.get("Tipo", "BT")).upper().strip() or "BT",
                "Desc": desc,
                "Qtd": qty,
            }
        )
    return normalized


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/version")
def app_version() -> dict[str, str]:
    return {"version": _load_local_version()}


@app.get("/api/structures")
def list_structures() -> dict[str, list[str]]:
    engine = _get_engine()
    codes: list[str] = []
    if engine.db_loader and engine.db_loader.conn:
        cursor = engine.db_loader.conn.execute(
            "SELECT DISTINCT codigo FROM estruturas WHERE codigo IS NOT NULL ORDER BY codigo"
        )
        for row in cursor.fetchall():
            code = str(row[0] or "").upper().strip()
            if not code:
                continue
            # Exclui ruídos do catálogo (kVA, numéricos puros, metragem, etc.)
            if re.match(r"^\d+(?:[.,]\d+)?(?:KVA)?$", code):
                continue
            if re.match(r"^\d+M$", code):
                continue
            if re.match(r"^(?:[A-Z]{1,3}\d+[A-Z0-9]*|[1-4]S\d|1HASTE|ESTAI)$", code):
                codes.append(code)
    return {"structures": codes}


@app.get("/login")
def login_page(error: str = "") -> HTMLResponse:
    html_path = FRONTEND_DIR / "login.html"
    html = html_path.read_text(encoding="utf-8")
    version = _load_local_version()
    html = html.replace("__APP_VERSION__", version)
    if error:
        html = html.replace(
            'const err = params.get("error");', f"const err = '{error}';"
        )
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})


@app.post("/auth/local-login")
def auth_local_login(email: str = Form(""), pin: str = Form("")):
    cfg = _load_auth_config()
    email_norm = str(email or "").strip().lower()
    pin_norm = str(pin or "").strip()
    if "@" not in email_norm:
        return RedirectResponse(
            url="/login?error=Informe+um+e-mail+valido.", status_code=303
        )
    domain = email_norm.split("@", 1)[1]
    if domain != cfg["allowed_email_domain"]:
        return RedirectResponse(
            url="/login?error=Acesso+restrito+ao+dominio+corporativo.", status_code=303
        )
    if pin_norm != cfg["pin_code"]:
        return RedirectResponse(url="/login?error=PIN+invalido.", status_code=303)

    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(
        AUTH_SESSION_COOKIE, _sign_session(email_norm), httponly=True, samesite="lax"
    )
    return resp


@app.get("/auth/logout")
def auth_logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(AUTH_SESSION_COOKIE)
    return resp


@app.get("/")
def index() -> HTMLResponse:
    html_path = FRONTEND_DIR / "index.html"
    html = html_path.read_text(encoding="utf-8")
    version = _load_local_version()
    html = html.replace("__APP_VERSION__", version)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})


@app.get("/as-built")
def as_built() -> HTMLResponse:
    html_path = FRONTEND_DIR / "asbuilt.html"
    html = html_path.read_text(encoding="utf-8")
    version = _load_local_version()
    html = html.replace("__APP_VERSION__", version)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})


@app.post("/api/extract")
async def extract_pdf(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Arquivo invalido. Envie um PDF.")

    temp_path: str | None = None
    try:
        pdf_bytes = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp:
            temp.write(pdf_bytes)
            temp_path = temp.name

        extractor = ProjectExtractor(temp_path)
        extracted = extractor.extract_with_metadata()
        project_info = extractor.extract_project_info()
        pole_map = extracted.get("pole_map", {}) or {}
        cables = extracted.get("cables", []) or []

        poles = _normalize_poles_from_map(pole_map)
        et_codes_by_pole = {
            str(pid): list((pdata or {}).get("EtCodes", []) or [])
            for pid, pdata in pole_map.items()
            if (pdata or {}).get("EtCodes")
        }
        val = TechnicalValidator()
        val.validate({"pole_map": pole_map, "cables": cables})
        summary = val.get_summary()

        return JSONResponse(
            {
                "project_info": project_info,
                "poles": poles,
                "cables": cables,
                "et_codes_by_pole": et_codes_by_pole,
                "validation": summary,
                "recommendations": _build_extract_recommendations(
                    poles, cables, summary
                ),
                "file_name": file.filename,
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Falha na extracao: {exc}"
        ) from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@app.post("/api/calculate")
async def calculate(payload: dict[str, Any]) -> JSONResponse:
    try:
        poles = payload.get("poles", [])
        cables = payload.get("cables", [])
        if not isinstance(poles, list):
            raise HTTPException(
                status_code=400, detail="Campo 'poles' deve ser uma lista."
            )
        if not isinstance(cables, list):
            raise HTTPException(
                status_code=400, detail="Campo 'cables' deve ser uma lista."
            )

        pole_map = _normalize_poles_to_map(poles)
        cable_rows = _normalize_cables(cables)
        et_debug_by_pole = {}
        for pid, pdata in sorted(pole_map.items(), key=lambda kv: kv[0]):
            et_debug_by_pole[str(pid)] = {
                "trafo": pdata.get("Trafo"),
                "et_codes": list(pdata.get("EtCodes", []) or []),
                "estf_codes": list(pdata.get("EstfCodes", []) or []),
            }

        engine = _get_engine()
        materials = engine.process_form_data(pole_map, cable_rows)
        cable_materials = engine.process_cables(cable_rows)
        all_materials = materials + cable_materials

        bom_rows = _group_bom_rows(all_materials)
        bom_by_pole: dict[str, list[dict[str, Any]]] = {}
        for pole_id, pole_data in sorted(pole_map.items(), key=lambda kv: kv[0]):
            pole_rows = engine.process_form_data({pole_id: pole_data}, cable_rows)
            bom_by_pole[pole_id] = _group_bom_rows(pole_rows)
        bom_by_pole["CABOS_GERAIS"] = _group_bom_rows(cable_materials)

        validator = TechnicalValidator()
        validator.validate({"pole_map": pole_map, "cables": cable_rows})
        validation = validator.get_summary()
        structure_audit = engine.audit_structure_coverage(pole_map)

        recommendations = _build_calculation_recommendations(
            pole_map, bom_rows, validation, structure_audit
        )
        quality_gate = _build_quality_gate(bom_rows, validation)
        return JSONResponse(
            {
                "bom": bom_rows,
                "bom_by_pole": bom_by_pole,
                "validation": validation,
                "structure_audit": structure_audit,
                "recommendations": recommendations,
                "quality_gate": quality_gate,
                "et_debug_by_pole": et_debug_by_pole,
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha no calculo: {exc}") from exc


@app.post("/api/export/csv")
async def export_csv(payload: dict[str, Any]) -> Response:
    bom = payload.get("bom", [])
    if not isinstance(bom, list):
        raise HTTPException(status_code=400, detail="Campo 'bom' deve ser uma lista.")
    validation = payload.get("validation", {}) or {}
    quality_gate = _build_quality_gate(
        bom,
        validation,
        override_enabled=bool(payload.get("override_enabled", False)),
        override_reason=str(payload.get("override_reason", "") or ""),
        low_conf_review_confirmed=bool(payload.get("low_conf_review_confirmed", False)),
    )
    if quality_gate["blocked"]:
        raise HTTPException(
            status_code=400, detail="Exportação bloqueada pelo gate de qualidade."
        )

    df = pd.DataFrame(bom)
    if df.empty:
        df = pd.DataFrame(columns=["Código SAP", "Descrição", "Quantidade"])
    csv_content = df.to_csv(index=False, sep=";", encoding="utf-8-sig")
    headers = {"Content-Disposition": 'attachment; filename="lista_materiais.csv"'}
    return Response(
        content=csv_content.encode("utf-8-sig"), media_type="text/csv", headers=headers
    )


@app.post("/api/export/pdf")
async def export_pdf(payload: dict[str, Any]) -> Response:
    project_info = payload.get("project_info", {}) or {}
    observacoes = str(payload.get("observacoes", "") or "")
    bom = payload.get("bom", [])
    if not isinstance(bom, list):
        raise HTTPException(status_code=400, detail="Campo 'bom' deve ser uma lista.")
    validation = payload.get("validation", {}) or {}
    quality_gate = _build_quality_gate(
        bom,
        validation,
        override_enabled=bool(payload.get("override_enabled", False)),
        override_reason=str(payload.get("override_reason", "") or ""),
        low_conf_review_confirmed=bool(payload.get("low_conf_review_confirmed", False)),
    )
    if quality_gate["blocked"]:
        raise HTTPException(
            status_code=400, detail="Exportação bloqueada pelo gate de qualidade."
        )

    df = pd.DataFrame(bom)
    if df.empty:
        df = pd.DataFrame(columns=["Código SAP", "Descrição", "Quantidade"])
    else:
        expected_cols = ["Código SAP", "Descrição", "Quantidade"]
        for col in expected_cols:
            if col not in df.columns:
                df[col] = ""
        df = df[expected_cols]

    buffer = BytesIO()
    pdf = PDFReport(buffer)
    pdf.generate(project_info, df, observacoes)
    pdf_bytes = buffer.getvalue()

    headers = {"Content-Disposition": 'attachment; filename="lista_materiais.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@app.post("/api/parse/json")
async def parse_json(payload: dict[str, Any]) -> JSONResponse:
    content = str(payload.get("content", "") or "")
    if not content.strip():
        raise HTTPException(status_code=400, detail="Conteudo vazio.")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"JSON invalido: {exc}") from exc
    return JSONResponse({"data": data})


@app.get("/api/update/check")
async def check_update() -> JSONResponse:
    local_version = _load_local_version()
    remote = _resolve_remote_release()
    remote_version = remote["remote_version"]
    update_available = _parse_version(remote_version) > _parse_version(local_version)
    return JSONResponse(
        {
            "local_version": local_version,
            "remote_version": remote_version,
            "package_url": remote["package_url"],
            "update_available": update_available,
        }
    )


@app.post("/api/update/apply")
async def apply_update(payload: dict[str, Any]) -> JSONResponse:
    target_version = str(payload.get("target_version", "")).strip()
    package_url = str(payload.get("package_url", "")).strip()
    if not target_version or not package_url:
        raise HTTPException(
            status_code=400, detail="target_version e package_url sao obrigatorios."
        )

    ps_script = PROJECT_ROOT / "scripts" / "update_app.ps1"
    if not ps_script.exists():
        raise HTTPException(status_code=500, detail="Script de update nao encontrado.")

    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ps_script),
        "-TargetVersion",
        target_version,
        "-PackageUrl",
        package_url,
    ]
    try:
        subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Falha ao iniciar processo de update: {exc}"
        ) from exc

    return JSONResponse(
        {
            "ok": True,
            "message": "Atualizacao iniciada. Aguarde 20-40 segundos e abra novamente a aplicacao.",
        }
    )
