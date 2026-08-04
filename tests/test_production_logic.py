from backend.app_fastapi import _clean_confidence, _clean_quantity
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


def test_process_form_data_keeps_raw_rows_per_pole_before_aggregation():
    engine = MaterialEngine()

    def fake_resolve_clamps(_pole_type, _structures, p_id=""):
        return [
            {
                "Origem": f"Poste {p_id}",
                "Código SAP": "3001",
                "Descrição": "ITEM X",
                "Quantidade": 1,
                "Confiança": 1.0,
                "pole_id": p_id,
            }
        ]

    engine.resolve_clamps = fake_resolve_clamps
    engine._resolve_structure_code = lambda code, pole_type="", **kwargs: (
        str(code).upper(),
        False,
    )
    engine.get_pole_sap = lambda pole: ("10000000", "POSTE TESTE")
    engine.resolve_transformers_direct = lambda *args, **kwargs: []
    engine.resolve_cables_direct = lambda *args, **kwargs: []
    engine.resolve_ramal_direct = lambda *args, **kwargs: ("VERIFICAR", "")
    engine.db_loader = None
    engine.is_loaded = False

    engine.process_form_data(
        {
            "P1": {
                "Pole": "C12/600",
                "Est": ["N1"],
                "Trafo": None,
                "Chave": None,
                "Estai": {"Qtd": 0},
                "ParaRaio": {"Qtd": 0},
                "Aterramento": {"Qtd": 0},
                "Ramal": {"Qtd": 0},
            },
            "P3": {
                "Pole": "C12/600",
                "Est": ["N1"],
                "Trafo": None,
                "Chave": None,
                "Estai": {"Qtd": 0},
                "ParaRaio": {"Qtd": 0},
                "Aterramento": {"Qtd": 0},
                "Ramal": {"Qtd": 0},
            },
        }
    )

    raw_rows = getattr(engine, "last_raw_results", [])
    assert any(row.get("pole_id") == "P3" for row in raw_rows)
    assert any(row.get("pole_id") == "P1" for row in raw_rows)


def test_quantity_and_confidence_normalization_handles_nan_and_infinity():
    assert _clean_quantity(float("nan")) == 0
    assert _clean_quantity(float("inf")) == 0
    assert _clean_confidence(float("nan")) == 1.0
    assert _clean_confidence(float("inf")) == 1.0
    assert _clean_confidence(float("-inf"), default=0.2) == 0.2


def test_resolve_clamps_tags_pole_id_for_grouping():
    class FakeDbLoader:
        def __init__(self):
            self.conn = True
            self.sap_codes = {"10000001": "ITEM TESTE"}
            self.unified_db = {}

        def get_sap_description(self, code):
            return self.sap_codes.get(str(code), str(code))

        def explode_structure(self, structure_code, pole_type_str=""):
            code = str(structure_code).upper()
            if code == "N1":
                return [{"code": "10000001", "desc": "ITEM TESTE", "qty": 1}]
            return []

        def find_material_by_description(self, search_terms, limit=1, exclude_terms=None):
            return [("10000000", "POSTE TESTE", 1)]

    engine = MaterialEngine()
    engine.db_loader = FakeDbLoader()
    engine.is_loaded = True
    engine._resolve_structure_code = lambda code, pole_type="", **kwargs: (
        str(code).upper(),
        False,
    )

    materials = engine.resolve_clamps("C12/600", ["N1"], p_id="P3")

    assert materials
    assert all(item.get("pole_id") == "P3" for item in materials)


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
    engine._resolve_structure_code = lambda code, pole_type="", **kwargs: (
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
    engine._resolve_structure_code = lambda code, pole_type="", **kwargs: (
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
    engine._resolve_structure_code = lambda code, pole_type="", **kwargs: (
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
    engine._resolve_structure_code = lambda code, pole_type="", **kwargs: (
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
    engine._resolve_structure_code = lambda code, pole_type="", **kwargs: (
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
    engine._resolve_structure_code = lambda code, pole_type="", **kwargs: (
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


def test_structure_audit_ignores_catalog_cintas_when_clamp_lookup_uses_fallback():
    class FakeDbLoader:
        def __init__(self):
            self.conn = True
            self.sap_codes = {}
            self.unified_db = {}

        def explode_structure(self, structure_code, pole_type_str=""):
            return [
                {"code": "30053137", "desc": "CINTA POSTE AC ZC F 200MM B-20", "qty": 2},
                {"code": "30053138", "desc": "CINTA POSTE AC ZC F 220MM B-22", "qty": 2},
                {"code": "30050394", "desc": "ARMACAO SECUNDARIA", "qty": 1},
            ]

        def get_sap_description(self, code):
            return str(code)

        def find_material_by_description(self, search_terms, limit=1, exclude_terms=None):
            return [("10000000", "POSTE TESTE", 1)]

    engine = MaterialEngine()
    engine.db_loader = FakeDbLoader()
    engine.is_loaded = True
    engine.clamp_logic = {("C11/600", "S"): [("30053140", 1)]}
    engine._resolve_structure_code = lambda code, pole_type="", **kwargs: (
        str(code).upper(),
        False,
    )

    def fake_resolve_clamps(_pole_type, _structures, p_id=""):
        return [
            {
                "Origem": f"Ferragem S2 em {p_id}",
                "Código SAP": "30053140",
                "Descrição": "CINTA POSTE AC ZC F 240MM B-24",
                "Quantidade": 1,
            },
            {
                "Origem": f"Estrutura S2 em {p_id}",
                "Código SAP": "30050394",
                "Descrição": "ARMACAO SECUNDARIA",
                "Quantidade": 1,
            },
        ]

    engine.resolve_clamps = fake_resolve_clamps
    audit = engine.audit_structure_coverage({"P2": {"Pole": "C09/600", "Est": ["S2"]}})

    assert audit["ok"] is True
    assert audit["mismatch_count"] == 0


def test_detect_smtr_variant_maps_3x70_signature_to_4c_variant():
    engine = MaterialEngine()
    engine.detected_cables = {"MT": None, "BT": None}

    variant = engine._detect_smtr_variant(
        [{"Tipo": "BT", "Desc": "BT 1X3X70(70)AXNI", "Qtd": 10}]
    )

    assert variant == "SMTR - CABO AL 4C 3X70MM2+70MM2 1KV"


def test_mt_cable_sparrow_multiplier_follows_phase_count():
    """Regressão OV 4001739539: cabo MT NX2ANA fatura N vias de SPARROW
    (fases) + 1 via de ROSE (neutro). Antes era fixo em 3x, inflando o
    SPARROW em derivações monofásicas/bifásicas."""

    class FakeDbLoader:
        def get_sap_description(self, code):
            return {
                "10050897": "CABO NU ALUMINIO 4AWG 7F ROSE",
                "10050898": "CABO NU CAA AL 2AWG SPARROW",
            }.get(str(code), str(code))

        def find_material_by_description(self, search_terms, limit=1, exclude_terms=None):
            return []

    def _sparrow_rose(desc, qtd):
        engine = MaterialEngine()
        engine.db_loader = FakeDbLoader()
        engine.is_loaded = True
        engine.detected_cables = {"MT": None, "BT": None}
        mats = engine.resolve_cables_direct([{"Tipo": "MT", "Desc": desc, "Qtd": qtd}])
        by_sap = {m["Código SAP"]: float(m["Quantidade"]) for m in mats}
        return by_sap.get("10050898"), by_sap.get("10050897")

    # Monofásico (1X) — caso reportado: SPARROW = metragem, não 3x.
    sparrow, rose = _sparrow_rose("MT 1X2ANA(4ANA)", 101.46)
    assert sparrow == 101.46
    assert rose == 101.46

    # Sem prefixo NX também é tratado como 1 via.
    sparrow, rose = _sparrow_rose("MT 2ANA(4ANA)", 101.46)
    assert sparrow == 101.46
    assert rose == 101.46

    # Bifásico (2X) — 2 vias de SPARROW.
    sparrow, rose = _sparrow_rose("MT 2X2ANA(4ANA)", 100.0)
    assert sparrow == 200.0
    assert rose == 100.0

    # Trifásico (3X) — comportamento original preservado (3 vias).
    sparrow, rose = _sparrow_rose("MT 3X2ANA(4ANA)", 100.0)
    assert sparrow == 300.0
    assert rose == 100.0


def test_trafo_pole_uses_supabase_structure_not_legacy_kit():
    """Regressão OV 4001739539: poste com estrutura ET de trafo deve usar a
    estrutura do Supabase (códigos novos) e NÃO o kit legado do unified_db
    (códigos velhos). Também valida que o M16 por cinta não é mais injetado e
    que a cordoalha de aterramento vira metragem (15 m)."""
    engine = MaterialEngine()
    engine.load_databases()
    if not engine.is_loaded:
        import pytest

        pytest.skip("Supabase indisponível para teste de integração")

    pole_map = {
        "P4": {
            "Pole": "C12/600",
            "Est": ["ET1T"],
            "Trafo": "MONO-15KVA",
            "Chave": None,
            "Estai": {"Qtd": 0},
            "ParaRaio": {"Qtd": 0},
            "Aterramento": {"Qtd": 1},
            "Ramal": {"Qtd": 0},
            "EtCodes": ["ET123456"],
        }
    }
    res = engine.process_form_data(pole_map)
    by_code = {str(r["Código SAP"]): r for r in res}

    # Códigos VELHOS do kit legado não podem aparecer.
    for old in ("10002581", "10004254", "10010733", "10011197", "10012874"):
        assert old not in by_code, f"código velho {old} não deveria aparecer"

    # Trafo deve ser o código novo, sem duplicar.
    trafos = [r for r in res if "TRAFO" in str(r["Descrição"]).upper()]
    assert len(trafos) == 1
    assert str(trafos[0]["Código SAP"]) == "10057259"

    # M16 por cinta (30058226) não deve ser injetado pela regra removida.
    m16 = [r for r in res if str(r["Código SAP"]) == "30058226"
           and str(r.get("Origem", "")).startswith("Fixacao cinta")]
    assert not m16

    # Cordoalha de aterramento vira metragem (15 m por descida).
    cord = by_code.get("30054511")
    assert cord is not None and float(cord["Quantidade"]) == 15.0
