"""Testes da seleção por Aplicação (coluna do Excel mestre 'Lista Consolidada')."""

from core.aplicacao import aplicacao_matches, parse_qty_text, pole_signature


def test_parse_qty_text_handles_text_quantities():
    assert parse_qty_text("2") == 2.0
    assert parse_qty_text("4,5MTS") == 4.5
    assert parse_qty_text("3.5 MTS") == 3.5
    assert parse_qty_text("2,4KG (15MTS)") == 15.0
    assert parse_qty_text("0,040KG") == 0.04
    assert parse_qty_text("") == 0.0
    assert parse_qty_text(None) == 0.0


def test_pole_signature():
    assert pole_signature("C12/600") == (12, 600, "CIRCULAR")
    assert pole_signature("DT11/300") == (11, 300, "DT")
    assert pole_signature("C9/300") == (9, 300, "CIRCULAR")
    assert pole_signature("lixo") is None


def test_aplicacao_all_and_empty():
    assert aplicacao_matches("ALL", "C12/600") is True
    # Aplicação vazia = lacuna de cadastro -> não fatura (chamador audita).
    assert aplicacao_matches("", "C12/600") is False


def test_aplicacao_p4_caso_12x600_circular():
    """P4 do OV 4001739539: poste C12/600 circular."""
    pole = "C12/600"
    # Suporte 255mm aplica (12X600 CIRCULAR); suporte 240mm é só FIBRA -> não.
    assert aplicacao_matches("12X600 CIRCULAR", pole) is True
    assert aplicacao_matches("12X600 FIBRA", pole) is False
    # Lista com o porte certo entre opções.
    assert aplicacao_matches("12X600 FIBRA; 12X600 CIRCULAR", pole) is True
    # Cintas de outros portes não aplicam.
    assert aplicacao_matches("12X300 FIBRA; 12X300 CIRCULAR", pole) is False
    assert aplicacao_matches("12X1000 FIBRA", pole) is False
    # "TODOS EXETO" inclui o 12X600.
    assert aplicacao_matches("TODOS EXETO 11X300DT E 11X300 MADEIRA", pole) is True


def test_aplicacao_todos_exeto_exclui_listados():
    assert aplicacao_matches("TODOS EXETO 11X300DT E 11X300 MADEIRA", "DT11/300") is False
    assert aplicacao_matches("TODOS EXETO 11X300DT E 11X300 MADEIRA", "C12/600") is True


def test_aplicacao_tolera_entradas_malformadas():
    # Separador ausente: "9X600 CIRCULAR12X300 FIBRA; 12X300 CIRCULAR"
    assert aplicacao_matches("9X600 CIRCULAR12X300 FIBRA; 12X300 CIRCULAR", "C9/600") is True
    assert aplicacao_matches("9X600 CIRCULAR12X300 FIBRA; 12X300 CIRCULAR", "C12/300") is True
    # ":" no lugar de ";" e falta de espaço antes do subtipo.
    assert aplicacao_matches("13X1500 CIRCULAR: 14X1500CIRCULAR", "C14/1500") is True
    assert aplicacao_matches("13X1500 CIRCULAR: 14X1500CIRCULAR", "C12/600") is False


def test_aplicacao_no_cabo_nao_filtra_por_poste():
    # Variante por cabo (SMTR/SMFL) não é filtrada por tipo de poste aqui.
    assert aplicacao_matches("NO CABO AL 4C 3X70MM2+70MM2 1KV", "C12/600") is True
