import pytest

from core.extractor import ProjectExtractor


def _extractor() -> ProjectExtractor:
    return ProjectExtractor(pdf_path="dummy.pdf")


def test_parse_copilot_direct_format():
    ext = _extractor()
    raw = '{"postes":[{"id":"P1","tipo":"C12/600","estruturas":["N4F"]}],"cabos":[],"ordem":"1"}'
    parsed = ext._parse_copilot_response(raw)
    assert "postes" in parsed
    assert "cabos" in parsed
    assert parsed["postes"][0]["id"] == "P1"


def test_parse_copilot_result_wrapper():
    ext = _extractor()
    raw = '{"result":{"postes":[{"id":"P2","tipo":"DT11/300","estruturas":[]}],"cabos":[{"tipo":"MT","descricao":"CABO","metros":10}],"ordem":"2"}}'
    parsed = ext._parse_copilot_response(raw)
    assert parsed["postes"][0]["id"] == "P2"
    assert parsed["cabos"][0]["tipo"] == "MT"


def test_parse_copilot_content_json_string():
    ext = _extractor()
    raw = '{"content":"{\\"postes\\":[{\\"id\\":\\"P3\\",\\"tipo\\":\\"C11/300\\",\\"estruturas\\":[]}],\\"cabos\\":[],\\"ordem\\":\\"3\\"}"}'
    parsed = ext._parse_copilot_response(raw)
    assert parsed["postes"][0]["id"] == "P3"
    assert parsed["ordem"] == "3"


def test_parse_copilot_invalid_payload_raises():
    ext = _extractor()
    with pytest.raises(RuntimeError):
        ext._parse_copilot_response('{"foo":"bar"}')
