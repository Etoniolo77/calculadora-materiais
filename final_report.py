from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from io import BytesIO
from datetime import datetime
import pandas as pd

class PDFReport:
    def __init__(self, buffer):
        self.buffer = buffer
        self.doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=30, leftMargin=30,
            topMargin=30, bottomMargin=30,
            title="Lista de Materiais"
        )
        self.elements = []
        self.styles = getSampleStyleSheet()

    def generate(self, project_info, df_materials, observacoes=""):
        """Gera o PDF com os dados fornecidos"""
        
        # 1. Cabeçalho
        self._create_header(project_info)
        
        # 2. Tabela de Materiais
        self._create_material_table(df_materials)
        
        # 3. Observações (se houver)
        if observacoes and str(observacoes).strip():
            self._create_observacoes(observacoes)
        
        # 4. Construir
        self.doc.build(self.elements)

    def _create_header(self, info):
        from reportlab.platypus import Image
        import os

        # Caminhos dos logos
        logo_em = "assets/logo_eletromarquez.png"

        # Elementos do Topo
        logo_em_obj = Paragraph("", self.styles['Normal'])
        if os.path.exists(logo_em):
            logo_em_obj = Image(logo_em, width=80, height=40)
            logo_em_obj.hAlign = 'LEFT'

        # Título
        title_style = ParagraphStyle(
            'TitleStr',
            parent=self.styles['Heading1'],
            fontSize=14,
            alignment=1, # Center
            textColor=colors.HexColor('#1f77b4'),
            spaceAfter=5
        )
        title_obj = Paragraph("LISTA DE MATERIAIS<br/>PROJETO", title_style)
        
        spacer_obj = Paragraph("", self.styles['Normal'])
        top_data = [[logo_em_obj, title_obj, spacer_obj]]
        
        top_table = Table(top_data, colWidths=[100, 335, 100])
        top_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (0,0), 'LEFT'),
            ('ALIGN', (1,0), (1,0), 'CENTER'),
            ('ALIGN', (2,0), (2,0), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        self.elements.append(top_table)
        self.elements.append(Spacer(1, 15))
        
        data_str = str(info.get('Data', ''))
        if not data_str or data_str == 'None':
            data_str = datetime.now().strftime('%d/%m/%Y')
        
        data = [
            ["ORDEM:", str(info.get('Ordem', '')) or "-", "DATA:", data_str],
            ["EQUIPE:", str(info.get('Equipe', '')) or "-", "PROGRAMADOR:", str(info.get('Programador', '')) or "-"]
        ]
        
        t = Table(data, colWidths=[60, 200, 80, 150])
        t.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('TEXTCOLOR', (0,0), (-1,-1), colors.darkblue),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('TEXTCOLOR', (0,0), (0,-1), colors.gray),
            ('TEXTCOLOR', (2,0), (2,-1), colors.gray),
        ]))
        self.elements.append(t)
        self.elements.append(Spacer(1, 15))

    def _create_material_table(self, df):
        if df.empty:
            self.elements.append(Paragraph("Nenhum material gerado para este projeto.", self.styles['Normal']))
            return

        headers = ['ITEM', 'CÓDIGO SAP', 'DESCRIÇÃO', 'QTD']
        table_data = [headers]
        
        desc_style = ParagraphStyle(
            'DescStyle',
            parent=self.styles['Normal'],
            fontSize=9,
            leading=10
        )
        
        for i, row in enumerate(df.itertuples(), start=1):
            try:
                sap = str(row[1]) if row[1] is not None else "-"
                desc_text = str(row[2]) if row[2] is not None else "Material não localizado"
                
                raw_qtd = row[3]
                if raw_qtd is None or (isinstance(raw_qtd, float) and pd.isna(raw_qtd)):
                    qtd = 0.0
                else:
                    try:
                        qtd = float(raw_qtd)
                    except (ValueError, TypeError):
                        qtd = 0.0
                
                if qtd == 0:
                    qtd_str = "0"
                elif qtd.is_integer():
                    qtd_str = f"{int(qtd)}"
                else:
                    qtd_str = f"{qtd:.2f}"
                
                p_desc = Paragraph(desc_text, desc_style)
                
                table_data.append([str(i), sap, p_desc, qtd_str])
            except Exception:
                continue
            
        t = Table(table_data, colWidths=[35, 75, 365, 60], repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1f77b4')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('TOPPADDING', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), colors.white),
            ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,1), (-1,-1), 9),
            ('VALIGN', (0,1), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,1), (0,-1), 'CENTER'),
            ('ALIGN', (1,1), (1,-1), 'CENTER'),
            ('ALIGN', (2,1), (2,-1), 'LEFT'),
            ('ALIGN', (3,1), (3,-1), 'RIGHT'),
            ('RIGHTPADDING', (3,1), (3,-1), 5),
        ]))
        self.elements.append(t)

    def _create_observacoes(self, observacoes):
        self.elements.append(Spacer(1, 20))
        obs_title_style = ParagraphStyle(
            'ObsTitle',
            parent=self.styles['Heading2'],
            fontSize=11,
            textColor=colors.HexColor('#1f77b4'),
            spaceAfter=8
        )
        self.elements.append(Paragraph("OBSERVAÇÕES", obs_title_style))
        obs_style = ParagraphStyle(
            'ObsContent',
            parent=self.styles['Normal'],
            fontSize=9,
            leading=12,
            textColor=colors.black
        )
        obs_text = str(observacoes or "").replace('\n', '<br/>')
        self.elements.append(Paragraph(obs_text, obs_style))
