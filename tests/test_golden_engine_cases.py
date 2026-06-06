from core.engine import MaterialEngine


GOLDEN_INPUT = {
    "P1": {
        "Pole": "C11/600",
        "Est": ["N1", "B2"],
        "Trafo": "MONO-15kVA",
        "Chave": "FACA",
        "Estai": {"Type": "CC - 14M", "Qtd": 1},
        "ParaRaio": {"Type": "CRUZETA", "Qtd": 1},
        "Aterramento": {"Qtd": 1},
        "Ramal": {"Type": "CABO MULTIPLEX 70MM2", "Qtd": 20.0},
    }
}


def test_golden_case_has_expected_origins():
    engine = MaterialEngine()
    engine.load_databases()
    result = engine.process_form_data(GOLDEN_INPUT)
    origins = {item["Origem"] for item in result}

    # Golden comportamental: esses grupos devem existir independentemente do SAP exato.
    assert any(o.startswith("Poste") for o in origins)
    assert any("Chave" in o for o in origins)
    assert any("Para-Raio" in o for o in origins)
    assert any("Aterramento" in o for o in origins)
