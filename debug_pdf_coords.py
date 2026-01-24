import pdfplumber
import re
import os

pdf_path = "c:/Users/EvandroCesarToniolo/Projetos_Antigravity/13_Calculadora_Materiais/PROJETO_DESE_4001770660_F01-01_Rev0 (2).pdf"

def debug_pdf():
    if not os.path.exists(pdf_path):
        print(f"Arquivo não encontrado: {pdf_path}")
        return

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            print(f"--- PÁGINA {i+1} ---")
            words = page.extract_words()
            words.sort(key=lambda w: (w['top'], w['x0']))
            
            for w in words:
                print(f"[{w['top']:>7.2f}, {w['x0']:>7.2f}] {w['text']}")

if __name__ == "__main__":
    debug_pdf()
