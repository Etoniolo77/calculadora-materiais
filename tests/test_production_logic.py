from core.engine import MaterialEngine


def _sample_pole_map():
    return {
        "P1": {
            "Pole": "C12/1000",
            "Est": ["ET4A", "M2M(R)", "S2(R)", "S1(R)"],
            "Trafo": None,
            "Chave": "FUSIVEL",
            "Estai": {"Type": "CC - 14M", "Qtd": 1},
            "ParaRaio": {"Type": "CRUZETA", "Qtd": 1},
            "Aterramento": {"Qtd": 1},
            "Ramal": {"Type": "CABO MULTIPLEX 35MM2", "Qtd": 15.0},
        },
        "P2": {
            "Pole": "C12/1000",
            "Est": ["ET1T", "B2F"],
            "Trafo": "TRI-112.5kVA",
            "Chave": "SECC",
            "Estai": {"Type": "CC - 14M", "Qtd": 0},
            "ParaRaio": {"Type": "CRUZETA", "Qtd": 0},
            "Aterramento": {"Qtd": 0},
            "Ramal": {"Type": None, "Qtd": 0.0},
        },
    }


def test_process_form_data_returns_materials_and_confidence():
    engine = MaterialEngine()
    engine.load_databases()
    results = engine.process_form_data(_sample_pole_map())

    assert isinstance(results, list)
    assert len(results) > 0
    assert all("Código SAP" in item for item in results)
    assert all("Quantidade" in item for item in results)
    assert all("Confiança" in item for item in results)
    assert all(float(item["Confiança"]) >= 0 for item in results)
    assert all(not str(item["Código SAP"]).startswith("9") for item in results)


def test_aggregation_merges_same_sap():
    engine = MaterialEngine()
    materials = [
        {"Origem": "A", "Código SAP": "3001", "Descrição": "ITEM X", "Quantidade": 1, "Confiança": 0.9},
        {"Origem": "B", "Código SAP": "3001", "Descrição": "ITEM X", "Quantidade": 2, "Confiança": 0.7},
    ]
    aggregated = engine.aggregate_materials(materials)
    assert len(aggregated) == 1
    assert aggregated[0]["Quantidade"] == 3
    assert float(aggregated[0]["Confiança"]) == 0.7
