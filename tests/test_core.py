import pytest
from upd_service import llm, registry

def test_parse_json_strips_think_and_markdown():
    raw = '<think>hmm {x}</think>\n```json\n{"a": 1}\n```'
    assert llm.parse_json_safe(raw) == {"a": 1}

def test_parse_json_error_is_llmerror():
    with pytest.raises(llm.LLMError):
        llm.parse_json_safe("нет json")

def test_plugins_loaded():
    assert {"УПД", "СЧФ"} <= {t["type"] for t in registry.list_types()}

DATA = {"meta": {"doc_type": "УПД"}, "document": {"number": "1", "date": "30.11.2025"},
        "seller": {"name": "А", "inn": "7701234567", "kpp": "7701010101", "address": "Москва"},
        "buyer": {"name": "Б", "inn": "7707654321", "kpp": "770701001", "address": "Москва"},
        "currency": {"code": "643", "name": "Российский рубль"},
        "items": [{"line_number": 1, "name": "Услуга", "unit_code": "796", "unit_name": "шт", "quantity": "1",
                   "price": "100", "amount_without_vat": "100.00", "excise": "без акциза", "vat_rate": "20%",
                   "vat_amount": "20.00", "amount_with_vat": "120.00"}],
        "totals": {"amount_without_vat": "100.00", "vat_amount": "20.00", "amount_with_vat": "120.00"},
        "transfer": {"date": "30.11.2025", "basis_doc_name": "Договор", "basis_doc_number": "1", "basis_doc_date": "01.01.2025"}}

def test_upd_xml_rules():
    xml = registry.build_xml("УПД", DATA)
    assert "КНД=\"1115131\"" in xml and "5.03" in xml
    assert "СвПРД" not in xml
    assert xml.index("СвПрод") < xml.index("СвПокуп") < xml.index("ДенИзм")
    assert "КПП=\"701010101\"" in xml  # 10 символов → последние 9
    xml.encode("windows-1251")

def test_schf_xml_builds():
    d = dict(DATA, meta={"doc_type": "СЧФ"})
    registry.build_xml("СЧФ", d).encode("windows-1251")
