from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from io import BytesIO
from datetime import datetime
import os
import pandas as pd

# ── Brand Identity — Eletromarquez / Evandro Toniolo ─────────────────────────
_BRAND   = colors.HexColor("#01458e")
_SHELL   = colors.HexColor("#1D2D3E")
_NEUTRAL = colors.HexColor("#EFF1F2")
_BORDER  = colors.HexColor("#D9DBDD")
_TEXT    = colors.HexColor("#1D2D3E")
_TEXTSEC = colors.HexColor("#556B82")
_SHELL_LIGHT = colors.HexColor("#8FAFCA")

_PAGE_W, _PAGE_H = A4
_BAND_H   = 38   # header band height
_MARGIN_L = 30
_MARGIN_R = 30
_MARGIN_T = _BAND_H + 18   # espaço abaixo da banda
_MARGIN_B = 44             # espaço para o rodapé


def _draw_page(canvas, doc):
    """Banda de cabeçalho + rodapé desenhados em todas as páginas."""
    canvas.saveState()
    year = datetime.now().year

    # ── Banda superior (fundo branco — baixo consumo de tinta) ─────
    # Apenas acento fino à esquerda + linha inferior, sem preenchimento escuro.
    canvas.setFillColor(_BRAND)
    canvas.rect(0, _PAGE_H - _BAND_H, 5, _BAND_H, fill=1, stroke=0)

    canvas.setStrokeColor(_BRAND)
    canvas.setLineWidth(1.2)
    canvas.line(0, _PAGE_H - _BAND_H, _PAGE_W, _PAGE_H - _BAND_H)

    # Título do documento (texto na cor da marca)
    canvas.setFillColor(_BRAND)
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(18, _PAGE_H - _BAND_H + 13, "LISTA DE MATERIAIS — PROJETO")

    # Label direita
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(_TEXTSEC)
    canvas.drawRightString(_PAGE_W - 16, _PAGE_H - _BAND_H + 14, f"ELETROMARQUEZ · {year}")

    # ── Rodapé ─────────────────────────────────────────────────────
    footer_y = 20
    canvas.setStrokeColor(_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(_MARGIN_L, footer_y + 12, _PAGE_W - _MARGIN_R, footer_y + 12)

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_TEXTSEC)
    canvas.drawString(_MARGIN_L, footer_y, "Gerado automaticamente · Uso interno · Eletromarquez")

    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(_TEXTSEC)
    canvas.drawRightString(_PAGE_W - _MARGIN_R, footer_y, f"Evandro César Toniolo · Eletromarquez · © {year}")

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_TEXTSEC)
    canvas.drawCentredString(_PAGE_W / 2, footer_y, f"Pág. {canvas.getPageNumber()}")

    canvas.restoreState()


class PDFReport:
    def __init__(self, buffer):
        self.buffer = buffer
        self.doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=_MARGIN_R,
            leftMargin=_MARGIN_L,
            topMargin=_MARGIN_T,
            bottomMargin=_MARGIN_B,
            title="Lista de Materiais",
        )
        self.elements = []
        self.styles = getSampleStyleSheet()

    def generate(self, project_info, df_materials, observacoes=""):
        self._create_info_block(project_info)
        self._create_material_table(df_materials)
        if observacoes and str(observacoes).strip():
            self._create_observacoes(observacoes)
        self.doc.build(self.elements, onFirstPage=_draw_page, onLaterPages=_draw_page)

    # ── Bloco de dados do projeto ──────────────────────────────────
    def _create_info_block(self, info):
        data_str = str(info.get("Data", ""))
        if not data_str or data_str == "None":
            data_str = datetime.now().strftime("%d/%m/%Y")

        label_style = ParagraphStyle(
            "InfoLabel",
            parent=self.styles["Normal"],
            fontSize=7,
            textColor=_TEXTSEC,
            fontName="Helvetica-Bold",
        )
        value_style = ParagraphStyle(
            "InfoValue",
            parent=self.styles["Normal"],
            fontSize=8,
            textColor=_TEXT,
            fontName="Helvetica",
        )

        def lbl(t): return Paragraph(t, label_style)
        def val(t): return Paragraph(str(t) if t else "—", value_style)

        rows = [
            [lbl("ORDEM"), val(info.get("Ordem")), lbl("DATA"), val(data_str)],
            [lbl("EQUIPE"), val(info.get("Equipe")), lbl("PROGRAMADOR"), val(info.get("Programador"))],
        ]
        usable_w = _PAGE_W - _MARGIN_L - _MARGIN_R
        lbl_w = 88
        val_w = (usable_w - lbl_w * 2) / 2
        t = Table(rows, colWidths=[lbl_w, val_w, lbl_w, val_w])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX",        (0, 0), (-1, -1), 0.5, _BORDER),
            ("INNERGRID",  (0, 0), (-1, -1), 0.5, _BORDER),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            # Fundo levemente neutro nas células de label
            ("BACKGROUND", (0, 0), (0, -1), _NEUTRAL),
            ("BACKGROUND", (2, 0), (2, -1), _NEUTRAL),
        ]))
        self.elements.append(t)
        self.elements.append(Spacer(1, 14))

    # ── Tabela de Materiais ────────────────────────────────────────
    def _create_material_table(self, df):
        if df.empty:
            self.elements.append(
                Paragraph("Nenhum material gerado para este projeto.", self.styles["Normal"])
            )
            return

        desc_style = ParagraphStyle(
            "DescStyle",
            parent=self.styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=_TEXT,
        )
        hdr_style = ParagraphStyle(
            "HdrStyle",
            parent=self.styles["Normal"],
            fontSize=9,
            fontName="Helvetica-Bold",
            textColor=_BRAND,
            alignment=TA_CENTER,
        )

        headers = [
            Paragraph("CÓDIGO SAP",  hdr_style),
            Paragraph("DESCRIÇÃO",   hdr_style),
            Paragraph("QTD",         hdr_style),
        ]
        table_data = [headers]

        for i, row in enumerate(df.itertuples(), start=1):
            try:
                sap  = str(row[1]) if row[1] is not None else "—"
                desc = str(row[2]) if row[2] is not None else "Material não localizado"

                raw_qtd = row[3]
                if raw_qtd is None or (isinstance(raw_qtd, float) and pd.isna(raw_qtd)):
                    qtd = 0.0
                else:
                    try:
                        qtd = float(raw_qtd)
                    except (ValueError, TypeError):
                        qtd = 0.0

                qtd_str = "0" if qtd == 0 else (f"{int(qtd)}" if qtd == int(qtd) else f"{qtd:.2f}")
                table_data.append([sap, Paragraph(desc, desc_style), qtd_str])
            except Exception:
                continue

        usable_w = _PAGE_W - _MARGIN_L - _MARGIN_R
        t = Table(table_data, colWidths=[80, usable_w - 80 - 56, 56], repeatRows=1)

        style_cmds = [
            # Cabeçalho (fundo claro, texto azul — baixo consumo de tinta)
            ("BACKGROUND",     (0, 0), (-1, 0), _NEUTRAL),
            ("TEXTCOLOR",      (0, 0), (-1, 0), _BRAND),
            ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",       (0, 0), (-1, 0), 9),
            ("TOPPADDING",     (0, 0), (-1, 0), 5),
            ("BOTTOMPADDING",  (0, 0), (-1, 0), 5),
            ("LINEBELOW",      (0, 0), (-1, 0), 1, _BRAND),
            # Grade
            ("GRID",           (0, 0), (-1, -1), 0.5, _BORDER),
            # Corpo — fonte e alinhamentos
            ("FONTNAME",       (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",       (0, 1), (-1, -1), 8),
            ("VALIGN",         (0, 1), (-1, -1), "MIDDLE"),
            ("TOPPADDING",     (0, 1), (-1, -1), 3),
            ("BOTTOMPADDING",  (0, 1), (-1, -1), 3),
            ("ALIGN",          (0, 1), (0, -1), "CENTER"),   # CÓDIGO SAP
            ("ALIGN",          (1, 1), (1, -1), "LEFT"),     # DESCRIÇÃO
            ("ALIGN",          (2, 1), (2, -1), "RIGHT"),    # QTD
            ("RIGHTPADDING",   (2, 1), (2, -1), 6),
            ("TEXTCOLOR",      (0, 1), (-1, -1), _TEXT),
        ]
        # Linhas alternadas: branco / neutro
        for row_i in range(1, len(table_data)):
            bg = colors.white if row_i % 2 == 1 else _NEUTRAL
            style_cmds.append(("BACKGROUND", (0, row_i), (-1, row_i), bg))

        t.setStyle(TableStyle(style_cmds))
        self.elements.append(t)

    # ── Bloco de Observações ───────────────────────────────────────
    def _create_observacoes(self, observacoes):
        self.elements.append(Spacer(1, 18))
        obs_title = ParagraphStyle(
            "ObsTitle",
            parent=self.styles["Normal"],
            fontSize=10,
            fontName="Helvetica-Bold",
            textColor=_SHELL,
            spaceAfter=6,
        )
        self.elements.append(Paragraph("OBSERVAÇÕES", obs_title))
        obs_body = ParagraphStyle(
            "ObsBody",
            parent=self.styles["Normal"],
            fontSize=9,
            leading=13,
            textColor=_TEXT,
        )
        self.elements.append(
            Paragraph(str(observacoes or "").replace("\n", "<br/>"), obs_body)
        )
