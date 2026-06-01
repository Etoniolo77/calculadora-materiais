#!/usr/bin/env python3
"""
Script Unificado: Atualizar Materiais do Excel
Faz TUDO automaticamente:
1. Lê exclusivamente a aba "Lista Consolidada" do Excel
2. Atualiza unified_db.json
3. Sincroniza materials.db (SQLite)
4. Gera relatório completo
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Caminhos
SCRIPTS_DIR = Path(__file__).parent
UPDATE_SCRIPT = SCRIPTS_DIR / "update_materiais_from_excel.py"
MIGRATE_SCRIPT = SCRIPTS_DIR / "migrate_to_sqlite.py"


def print_header(title: str):
    """Imprime cabeçalho formatado"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def run_script(script_path: Path, description: str) -> bool:
    """
    Executa um script Python e retorna sucesso/falha.

    Returns:
        True se sucesso, False se erro
    """
    print(f"\n>>> Executando: {description}")
    print(f"    Script: {script_path.name}")

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=script_path.parent.parent,  # Raiz do projeto
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # Mostrar output
        if result.stdout:
            print(result.stdout)

        if result.returncode != 0:
            print(f"\n[ERRO] Script falhou com codigo: {result.returncode}")
            if result.stderr:
                print("Erro:")
                print(result.stderr)
            return False

        print(f"[OK] {description} concluido com sucesso!")
        return True

    except Exception as e:
        print(f"[ERRO] Excecao ao executar script: {e}")
        return False


def main():
    """Execução principal"""
    print_header("ATUALIZACAO COMPLETA DE MATERIAIS")
    print(f"Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nEste script faz:")
    print("  [1] Le exclusivamente a aba 'Lista Consolidada' do Excel")
    print("  [2] Atualiza unified_db.json")
    print("  [3] Sincroniza materials.db (SQLite)")
    print("  [4] Valida consistencia dos dados")

    # Verificar se scripts existem
    if not UPDATE_SCRIPT.exists():
        print(f"\n[ERRO] Script nao encontrado: {UPDATE_SCRIPT}")
        return 1

    if not MIGRATE_SCRIPT.exists():
        print(f"\n[ERRO] Script nao encontrado: {MIGRATE_SCRIPT}")
        return 1

    # === PASSO 1: Atualizar unified_db.json ===
    print_header("PASSO 1/2: Atualizar unified_db.json")

    success = run_script(
        UPDATE_SCRIPT, "Leitura do Excel e atualizacao do unified_db.json"
    )

    if not success:
        print("\n[ERRO] Falha ao atualizar unified_db.json")
        print("Abortando sincronizacao do SQLite.")
        return 1

    # === PASSO 2: Sincronizar materials.db ===
    print_header("PASSO 2/2: Sincronizar materials.db (SQLite)")

    success = run_script(MIGRATE_SCRIPT, "Migracao do JSON para SQLite")

    if not success:
        print("\n[ERRO] Falha ao sincronizar materials.db")
        print("AVISO: unified_db.json foi atualizado, mas SQLite esta desatualizado!")
        print("Execute manualmente: python scripts/migrate_to_sqlite.py")
        return 1

    # === SUCESSO ===
    print_header("CONCLUIDO COM SUCESSO")
    print("\n[OK] Ambos os bancos de dados estao atualizados:")
    print("  - unified_db.json (metadados)")
    print("  - materials.db (fonte principal da aplicacao)")
    print("\nA aplicacao agora esta usando os dados mais recentes!")
    print("\nProximos passos:")
    print("  1. Testar a aplicacao")
    print("  2. Verificar se materiais atualizados aparecem")
    print("  3. Validar descricoes corretas")

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n[INTERROMPIDO] Operacao cancelada pelo usuario.")
        sys.exit(130)
    except Exception as e:
        print(f"\n[ERRO FATAL] {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
