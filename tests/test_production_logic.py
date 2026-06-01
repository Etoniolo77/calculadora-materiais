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
        {
            "Origem": "A",
            "Código SAP": "3001",
            "Descrição": "ITEM X",
            "Quantidade": 1,
            "Confiança": 0.9,
        },
        {
            "Origem": "B",
            "Código SAP": "3001",
            "Descrição": "ITEM X",
            "Quantidade": 2,
            "Confiança": 0.7,
        },
    ]
    aggregated = engine.aggregate_materials(materials)
    assert len(aggregated) == 1
    assert aggregated[0]["Quantidade"] == 3
    assert float(aggregated[0]["Confiança"]) == 0.7


def test_composite_structure_u4_1s4_expands_and_sums_materials():
    class FakeDbLoader:
        def __init__(self):
            self.conn = True
            self.sap_codes = {}
            self.unified_db = {}
            self.calls = []

        def explode_structure(self, structure_code, pole_type_str=""):
            self.calls.append(str(structure_code).upper())
            code = str(structure_code).upper()
            if code == "U4":
                return [{"code": "30000001", "desc": "ITEM U4", "qty": 2}]
            if code == "S4":
                return [{"code": "30000002", "desc": "ITEM S4", "qty": 3}]
            return [
                {"code": "VERIFICAR", "desc": f"VERIFICAR ESTRUTURA {code}", "qty": 1}
            ]

        def get_sap_description(self, code):
            return str(code)

        def find_material_by_description(
            self, search_terms, limit=1, exclude_terms=None
        ):
            return [("10000000", "POSTE TESTE", 1)]

    engine = MaterialEngine()
    fake_loader = FakeDbLoader()
    engine.db_loader = fake_loader
    engine.is_loaded = True
    engine._resolve_structure_code = lambda code, pole_type="": (
        str(code).upper(),
        False,
    )

    mats = engine.resolve_clamps("C12/600", ["U4-1S4"], p_id="P1")
    aggregated = engine.aggregate_materials(mats)

    exploded_set = set(fake_loader.calls)
    assert "U4" in exploded_set
    assert "S4" in exploded_set

    by_sap = {row["Código SAP"]: row for row in aggregated}
    assert "30000001" in by_sap
    assert "30000002" in by_sap
    assert float(by_sap["30000001"]["Quantidade"]) >= 2
    assert float(by_sap["30000002"]["Quantidade"]) >= 3


def test_composite_structure_with_plus_is_expanded():
    class FakeDbLoader:
        def __init__(self):
            self.conn = True
            self.sap_codes = {}
            self.unified_db = {}
            self.calls = []

        def explode_structure(self, structure_code, pole_type_str=""):
            self.calls.append(str(structure_code).upper())
            code = str(structure_code).upper()
            if code == "U4":
                return [{"code": "30000001", "desc": "ITEM U4", "qty": 1}]
            if code == "S4":
                return [{"code": "30000002", "desc": "ITEM S4", "qty": 1}]
            return [{"code": "VERIFICAR", "desc": f"VERIFICAR {code}", "qty": 1}]

        def get_sap_description(self, code):
            return str(code)

        def find_material_by_description(
            self, search_terms, limit=1, exclude_terms=None
        ):
            return [("10000000", "POSTE TESTE", 1)]

    engine = MaterialEngine()
    fake_loader = FakeDbLoader()
    engine.db_loader = fake_loader
    engine.is_loaded = True
    engine._resolve_structure_code = lambda code, pole_type="": (
        str(code).upper(),
        False,
    )

    mats = engine.resolve_clamps("C12/600", ["U4 + S4"], p_id="P2")
    aggregated = engine.aggregate_materials(mats)

    exploded_set = set(fake_loader.calls)
    assert "U4" in exploded_set
    assert "S4" in exploded_set

    by_sap = {row["Código SAP"]: row for row in aggregated}
    assert "30000001" in by_sap
    assert "30000002" in by_sap


def test_structure_numeric_prefix_is_multiplier():
    class FakeDbLoader:
        def __init__(self):
            self.conn = True
            self.sap_codes = {}
            self.unified_db = {}
            self.calls = []

        def explode_structure(self, structure_code, pole_type_str=""):
            self.calls.append(str(structure_code).upper())
            code = str(structure_code).upper()
            if code == "S2":
                return [{"code": "30000022", "desc": "ITEM S2", "qty": 1}]
            return [{"code": "VERIFICAR", "desc": f"VERIFICAR {code}", "qty": 1}]

        def get_sap_description(self, code):
            return str(code)

        def find_material_by_description(
            self, search_terms, limit=1, exclude_terms=None
        ):
            return [("10000000", "POSTE TESTE", 1)]

    engine = MaterialEngine()
    fake_loader = FakeDbLoader()
    engine.db_loader = fake_loader
    engine.is_loaded = True
    engine._resolve_structure_code = lambda code, pole_type="": (
        str(code).upper(),
        False,
    )

    mats = engine.resolve_clamps("C12/600", ["2S2"], p_id="P3")
    aggregated = engine.aggregate_materials(mats)
    by_sap = {row["Código SAP"]: row for row in aggregated}

    # 2S2 precisa virar 2 ocorrências de S2.
    assert fake_loader.calls.count("S2") >= 2
    assert float(by_sap["30000022"]["Quantidade"]) >= 2


def test_numeric_prefix_multiplier_applies_to_any_structure_code():
    engine = MaterialEngine()

    expanded = engine._expand_composite_structures(
        [
            "2CE2",
            "3SMTR",
            "1S4",
            "U4",
        ]
    )

    assert expanded.count("CE2") == 2
    assert expanded.count("SMTR") == 3
    assert expanded.count("S4") == 1
    assert expanded.count("U4") == 1


def test_structure_audit_detects_missing_materials_and_qty():
    class FakeDbLoader:
        def __init__(self):
            self.conn = True
            self.sap_codes = {}
            self.unified_db = {}

        def explode_structure(self, structure_code, pole_type_str=""):
            code = str(structure_code).upper()
            if code == "N1":
                return [
                    {"code": "30000010", "desc": "ITEM A", "qty": 2},
                    {"code": "30000020", "desc": "ITEM B", "qty": 1},
                ]
            return []

        def get_sap_description(self, code):
            return self.sap_codes.get(str(code), str(code))

        def find_material_by_description(
            self, search_terms, limit=1, exclude_terms=None
        ):
            return [("10000000", "POSTE TESTE", 1)]

    engine = MaterialEngine()
    engine.db_loader = FakeDbLoader()
    engine.is_loaded = True
    engine._resolve_structure_code = lambda code, pole_type="": (
        str(code).upper(),
        False,
    )

    def fake_resolve_clamps(_pole_type, _structures, p_id=""):
        # ITEM B veio com quantidade menor do que esperado
        return [
            {
                "Origem": f"Estrutura N1 em {p_id}",
                "Código SAP": "30000010",
                "Descrição": "ITEM A",
                "Quantidade": 2,
            },
            {
                "Origem": f"Estrutura N1 em {p_id}",
                "Código SAP": "30000020",
                "Descrição": "ITEM B",
                "Quantidade": 0.5,
            },
        ]

    engine.resolve_clamps = fake_resolve_clamps
    audit = engine.audit_structure_coverage({"P2": {"Pole": "C12/600", "Est": ["N1"]}})

    assert audit["ok"] is False
    assert audit["mismatch_count"] == 1
    detail = audit["poles"][0]["details"][0]
    assert detail["structure"] == "N1"
    assert detail["ok"] is False
    assert any(m["sap"] == "30000020" for m in detail["missing"])


def test_structure_audit_passes_when_structure_materials_match():
    class FakeDbLoader:
        def __init__(self):
            self.conn = True
            self.sap_codes = {}
            self.unified_db = {}

        def explode_structure(self, structure_code, pole_type_str=""):
            code = str(structure_code).upper()
            if code == "U4":
                return [
                    {"code": "30001000", "desc": "ITEM X", "qty": 1},
                    {"code": "30002000", "desc": "ITEM Y", "qty": 3},
                ]
            return []

        def get_sap_description(self, code):
            return str(code)

        def find_material_by_description(
            self, search_terms, limit=1, exclude_terms=None
        ):
            return [("10000000", "POSTE TESTE", 1)]

    engine = MaterialEngine()
    engine.db_loader = FakeDbLoader()
    engine.is_loaded = True
    engine._resolve_structure_code = lambda code, pole_type="": (
        str(code).upper(),
        False,
    )

    def fake_resolve_clamps(_pole_type, _structures, p_id=""):
        return [
            {
                "Origem": f"Estrutura U4 em {p_id}",
                "Código SAP": "30001000",
                "Descrição": "ITEM X",
                "Quantidade": 1,
            },
            {
                "Origem": f"Estrutura U4 em {p_id}",
                "Código SAP": "30002000",
                "Descrição": "ITEM Y",
                "Quantidade": 3,
            },
        ]

    engine.resolve_clamps = fake_resolve_clamps
    audit = engine.audit_structure_coverage({"P3": {"Pole": "DT12/300", "Est": ["U4"]}})

    assert audit["ok"] is True
    assert audit["mismatch_count"] == 0


def test_structure_audit_is_origin_label_agnostic():
    class FakeDbLoader:
        def __init__(self):
            self.conn = True
            self.sap_codes = {}
            self.unified_db = {}

        def explode_structure(self, structure_code, pole_type_str=""):
            code = str(structure_code).upper()
            if code == "N1":
                return [{"code": "30001010", "desc": "ITEM FERRAGEM", "qty": 2}]
            return []

        def get_sap_description(self, code):
            return str(code)

        def find_material_by_description(
            self, search_terms, limit=1, exclude_terms=None
        ):
            return [("10000000", "POSTE TESTE", 1)]

    engine = MaterialEngine()
    engine.db_loader = FakeDbLoader()
    engine.is_loaded = True
    engine._resolve_structure_code = lambda code, pole_type="": (
        str(code).upper(),
        False,
    )

    def fake_resolve_clamps(_pole_type, _structures, p_id=""):
        return [
            {
                # Origem com rótulo arbitrário (não deve afetar auditoria)
                "Origem": f"Composicao N1 em {p_id}",
                "Código SAP": "30001010",
                "Descrição": "ITEM FERRAGEM",
                "Quantidade": 2,
            }
        ]

    engine.resolve_clamps = fake_resolve_clamps
    audit = engine.audit_structure_coverage({"P1": {"Pole": "C12/600", "Est": ["N1"]}})

    assert audit["ok"] is True
    assert audit["mismatch_count"] == 0
