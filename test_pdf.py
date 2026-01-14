from final_report import PDFReport
from io import BytesIO
import pandas as pd

def test_pdf():
    buff = BytesIO()
    report = PDFReport(buff)
    project_info = {'Ordem': '12345', 'Data': '14/01/2026', 'Equipe': 'Alpha', 'Programador': 'Beta'}
    df = pd.DataFrame([
        {'Código SAP': '1000', 'Descrição': 'Material A', 'Quantidade': 10},
        {'Código SAP': '2000', 'Descrição': 'Material B', 'Quantidade': 5.5}
    ])
    try:
        report.generate(project_info, df, "Observações de teste")
        pdf_data = buff.getvalue()
        if len(pdf_data) > 0:
            print(f"PDF gerado com sucesso! Tamanho: {len(pdf_data)} bytes")
            with open("test_output.pdf", "wb") as f:
                f.write(pdf_data)
        else:
            print("PDF gerado está vazio!")
    except Exception as e:
        print(f"Erro ao gerar PDF: {e}")

if __name__ == "__main__":
    test_pdf()
