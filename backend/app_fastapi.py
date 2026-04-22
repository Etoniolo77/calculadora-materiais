from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles


PROJECT_ROOT = Path(__file__).resolve().parents[1]
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


def _get_engine() -> MaterialEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = MaterialEngine()
            _engine.load_databases()
    return _engine


def _default_pole_payload(pole: dict[str, Any]) -> dict[str, Any]:
    estai_val = pole.get("Estai", 0)
    if isinstance(estai_val, dict):
        estai = {"Type": str(estai_val.get("Type", "CC - 14M")), "Qtd": int(estai_val.get("Qtd", 0) or 0)}
    else:
        estai = {"Type": "CC - 14M", "Qtd": int(estai_val or 0)}

    para_raio_val = pole.get("ParaRaio", {"Type": "CRUZETA", "Qtd": 0})
    if isinstance(para_raio_val, dict):
        para_raio = {"Type": str(para_raio_val.get("Type", "CRUZETA")), "Qtd": int(para_raio_val.get("Qtd", 0) or 0)}
    else:
        para_raio = {"Type": "CRUZETA", "Qtd": int(para_raio_val or 0)}

    aterr_val = pole.get("Aterramento", {"Qtd": 0})
    if isinstance(aterr_val, dict):
        aterramento = {"Qtd": int(aterr_val.get("Qtd", 0) or 0)}
    else:
        aterramento = {"Qtd": int(aterr_val or 0)}

    ramal_val = pole.get("Ramal", {"Type": None, "Qtd": 0.0})
    if isinstance(ramal_val, dict):
        ramal = {"Type": ramal_val.get("Type"), "Qtd": float(ramal_val.get("Qtd", 0) or 0)}
    else:
        ramal = {"Type": None, "Qtd": float(ramal_val or 0)}

    structures = pole.get("Est", [])
    if not isinstance(structures, list):
        structures = []

    return {
        "Pole": str(pole.get("Pole", "Desconhecido")),
        "Est": [str(item).upper().strip() for item in structures if str(item).strip()],
        "Trafo": pole.get("Trafo"),
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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "index.html"))


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
        extractor.extract_text()
        project_info = extractor.extract_project_info()
        pole_map = extractor.find_structures_per_pole()
        cables = extractor.find_cables()

        poles = _normalize_poles_from_map(pole_map)
        val = TechnicalValidator()
        val.validate({"pole_map": pole_map, "cables": cables})
        summary = val.get_summary()

        return JSONResponse(
            {
                "project_info": project_info,
                "poles": poles,
                "cables": cables,
                "validation": summary,
                "file_name": file.filename,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha na extracao: {exc}") from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


@app.post("/api/calculate")
async def calculate(payload: dict[str, Any]) -> JSONResponse:
    try:
        poles = payload.get("poles", [])
        cables = payload.get("cables", [])
        if not isinstance(poles, list):
            raise HTTPException(status_code=400, detail="Campo 'poles' deve ser uma lista.")
        if not isinstance(cables, list):
            raise HTTPException(status_code=400, detail="Campo 'cables' deve ser uma lista.")

        pole_map = _normalize_poles_to_map(poles)
        cable_rows = _normalize_cables(cables)

        engine = _get_engine()
        materials = engine.process_form_data(pole_map)
        cable_materials = engine.process_cables(cable_rows)
        all_materials = materials + cable_materials

        if all_materials:
            df = pd.DataFrame(all_materials)
            grouped = (
                df.groupby(["Código SAP", "Descrição"], as_index=False)["Quantidade"]
                .sum()
                .sort_values(by=["Código SAP", "Descrição"], ascending=[True, True])
            )
            bom_rows = grouped.to_dict(orient="records")
        else:
            bom_rows = []

        validator = TechnicalValidator()
        validator.validate({"pole_map": pole_map, "cables": cable_rows})
        validation = validator.get_summary()

        return JSONResponse({"bom": bom_rows, "validation": validation})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha no calculo: {exc}") from exc


@app.post("/api/export/csv")
async def export_csv(payload: dict[str, Any]) -> Response:
    bom = payload.get("bom", [])
    if not isinstance(bom, list):
        raise HTTPException(status_code=400, detail="Campo 'bom' deve ser uma lista.")

    df = pd.DataFrame(bom)
    if df.empty:
        df = pd.DataFrame(columns=["Código SAP", "Descrição", "Quantidade"])
    csv_content = df.to_csv(index=False, sep=";", encoding="utf-8-sig")
    headers = {"Content-Disposition": 'attachment; filename="lista_materiais.csv"'}
    return Response(content=csv_content.encode("utf-8-sig"), media_type="text/csv", headers=headers)


@app.post("/api/export/pdf")
async def export_pdf(payload: dict[str, Any]) -> Response:
    project_info = payload.get("project_info", {}) or {}
    observacoes = str(payload.get("observacoes", "") or "")
    bom = payload.get("bom", [])
    if not isinstance(bom, list):
        raise HTTPException(status_code=400, detail="Campo 'bom' deve ser uma lista.")

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
