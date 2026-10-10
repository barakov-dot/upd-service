"""
Плагин: СЧФ (Счёт-фактура)
Функция=СЧФ — только счёт-фактура, без передаточного акта.
Схема: ON_NSCHFDOPPR v5.03
"""

import uuid
from datetime import datetime
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

DOC_TYPE = "СЧФ"
LABEL    = "Счёт-фактура (СЧФ)"


def DETECT(text: str) -> bool:
    """Счёт-фактура — есть заголовок, но нет признаков УПД/акта."""
    t = text.lower()
    is_invoice = "счет-фактура" in t or "счёт-фактура" in t
    is_upd = "универсальный передаточный" in t or "упд" in t
    is_act = "акт " in t and "выполненных работ" in t
    return is_invoice and not is_upd and not is_act


PROMPT = """Это Счёт-фактура (СЧФ).
Прочитай все поля и верни JSON строго такой структуры:
{
  "document": {
    "number": "номер счёт-фактуры",
    "date": "ДД.ММ.ГГГГ",
    "correction_number": null,
    "correction_date": null,
    "function": "СЧФ"
  },
  "seller": {
    "name": "наименование организации",
    "inn": "только цифры",
    "kpp": "только цифры",
    "address": "полный адрес"
  },
  "buyer": {
    "name": "наименование организации",
    "inn": "только цифры",
    "kpp": "только цифры",
    "address": "полный адрес"
  },
  "payment_doc": {
    "number": "номер платёжно-расчётного документа если есть",
    "date": "ДД.ММ.ГГГГ"
  },
  "basis_doc": {
    "name": "Договор или иной документ",
    "number": "номер",
    "date": "ДД.ММ.ГГГГ"
  },
  "currency": {"code": "643", "name": "Российский рубль"},
  "items": [
    {
      "line_number": 1,
      "name": "наименование товара или услуги",
      "unit_code": "796",
      "unit_name": "шт",
      "quantity": "1.000",
      "price": "0.00",
      "amount_without_vat": "0.00",
      "excise": "без акциза",
      "vat_rate": "20%",
      "vat_amount": "0.00",
      "amount_with_vat": "0.00"
    }
  ],
  "totals": {
    "amount_without_vat": "0.00",
    "vat_amount": "0.00",
    "amount_with_vat": "0.00"
  },
  "meta": {
    "doc_type": "СЧФ",
    "recognition_confidence": "high",
    "uncertain_fields": [],
    "rotation": 0
  }
}

ВАЖНО: у счёт-фактуры нет блока transfer/акта передачи — только данные счёта.
ВАЖНО — ОРИЕНТАЦИЯ ДОКУМЕНТА:
Посмотри на изображение. Если текст читается нормально (горизонтально слева направо) — rotation=0.
Если документ повёрнут набок или вверх ногами — укажи угол поворота по часовой стрелке который нужен чтобы выровнять:
- текст читается снизу вверх (повёрнут на 90° CCW) → rotation=90
- текст вверх ногами → rotation=180
- текст читается сверху вниз (повёрнут на 90° CW) → rotation=270
Запиши результат в meta.rotation (0/90/180/270)."""


# ─── Утилиты (дублируем локально — плагины независимы) ───────────────────────

def _now_date(): return datetime.now().strftime("%d.%m.%Y")
def _now_time(): return datetime.now().strftime("%H.%M.%S")

def _make_file_id(inn, date):
    date_str = (date or "").replace(".", "")
    uid = str(uuid.uuid4()).upper().replace("-", "")
    return f"ON_NSCHFDOPPR_{inn}_{date_str}_{uid}"

def _prettify(element):
    raw = tostring(element, encoding="unicode")
    parsed = minidom.parseString(raw)
    pretty = parsed.toprettyxml(indent="\t", encoding="windows-1251")
    lines = [l for l in pretty.decode("windows-1251").split("\n") if l.strip()]
    return "\n".join(lines)

def _clean_inn(v):
    if not v: return ""
    return "".join(c for c in str(v) if c.isdigit())[:10]

def _clean_kpp(v):
    if not v: return None
    clean = "".join(c for c in str(v).upper() if c.isdigit() or c.isalpha())
    if len(clean) > 9: clean = clean[-9:]
    return clean if len(clean) == 9 else None

def _build_participant(parent, tag, data):
    """СвПрод/СвПокуп с атрибутом СокрНаим (в СЧФ он есть в эталоне)"""
    el = SubElement(parent, tag)
    if data.get("name"):
        el.set("СокрНаим", data["name"])
    id_sv = SubElement(el, "ИдСв")
    sv_yul = SubElement(id_sv, "СвЮЛУч")
    sv_yul.set("НаимОрг", data.get("name", ""))
    sv_yul.set("ИННЮЛ", _clean_inn(data.get("inn", "")))
    kpp = _clean_kpp(data.get("kpp"))
    if kpp: sv_yul.set("КПП", kpp)
    if data.get("address"):
        addr = SubElement(el, "Адрес")
        ai = SubElement(addr, "АдрИнф")
        ai.set("КодСтр", "643")
        ai.set("НаимСтран", "РОССИЯ")
        ai.set("АдрТекст", data["address"])
    return el

def _build_excise(parent, val):
    akc = SubElement(parent, "Акциз")
    v = (val or "").strip().lower()
    if v in ("без акциза", "нет", "", "null"):
        SubElement(akc, "БезАкциз").text = "без акциза"
    else:
        SubElement(akc, "СумАкциз").text = str(val)

def _build_vat(parent, vat_rate, vat_amount, container_tag="СумНал"):
    container = SubElement(parent, container_tag)
    rate = (vat_rate or "").strip().lower()
    if rate in ("без ндс", "без нал", ""):
        SubElement(container, "БезНДС").text = "без НДС"
    else:
        SubElement(container, "СумНал").text = str(vat_amount or "0.00")

def _build_item(parent, item, line_num):
    sv = SubElement(parent, "СведТов")
    sv.set("НомСтр", str(line_num))
    sv.set("НаимТов", item.get("name", ""))
    if item.get("unit_code"): sv.set("ОКЕИ_Тов", str(item["unit_code"]))
    if item.get("unit_name"): sv.set("НаимЕдИзм", item["unit_name"])
    if item.get("quantity"):  sv.set("КолТов",    str(item["quantity"]))
    if item.get("price"):     sv.set("ЦенаТов",   str(item["price"]))
    sv.set("НалСт", str(item.get("vat_rate", "без НДС")))
    if item.get("amount_without_vat"): sv.set("СтТовБезНДС", str(item["amount_without_vat"]))
    if item.get("amount_with_vat"):    sv.set("СтТовУчНал",  str(item["amount_with_vat"]))
    _build_excise(sv, item.get("excise", "без акциза"))
    _build_vat(sv, item.get("vat_rate"), item.get("vat_amount"), "СумНал")

def _build_totals(parent, totals, vat_rate):
    vsego = SubElement(parent, "ВсегоОпл")
    vsego.set("СтТовБезНДСВсего", str(totals.get("amount_without_vat", "0.00")))
    vsego.set("СтТовУчНалВсего",  str(totals.get("amount_with_vat",    "0.00")))
    _build_vat(vsego, vat_rate, totals.get("vat_amount"), "СумНалВсего")


# ─── Главная функция ──────────────────────────────────────────────────────────

def build_xml(data: dict) -> str:
    doc      = data.get("document", {})
    seller   = data.get("seller", {})
    buyer    = data.get("buyer", {})
    items    = data.get("items", [])
    totals   = data.get("totals", {})
    payment  = data.get("payment_doc", {})
    basis    = data.get("basis_doc", {})
    currency = data.get("currency", {"code": "643", "name": "Российский рубль"})

    # ── Файл ──────────────────────────────────────────────────────────────────
    root = Element("Файл")
    root.set("ИдФайл", _make_file_id(seller.get("inn", "0"), doc.get("date", "")))
    root.set("ВерсФорм", "5.03")
    root.set("ВерсПрог", "УПД Сервис 1.0")

    # ── Документ — Функция=СЧФ, без НаимДокОпр и ПоФактХЖ ───────────────────
    document = SubElement(root, "Документ")
    document.set("КНД", "1115131")
    document.set("Функция", "СЧФ")
    document.set("ДатаИнфПр", _now_date())
    document.set("ВремИнфПр", _now_time())
    document.set("НаимЭконСубСост", seller.get("name", ""))

    # ── СвСчФакт ──────────────────────────────────────────────────────────────
    sv_sch = SubElement(document, "СвСчФакт")
    sv_sch.set("НомерДок", doc.get("number", ""))
    sv_sch.set("ДатаДок",  doc.get("date", ""))

    if doc.get("correction_number") and doc.get("correction_date"):
        ispr = SubElement(sv_sch, "ИспрДок")
        ispr.set("НомИспр", str(doc["correction_number"]))
        ispr.set("ДатаИспр", doc["correction_date"])

    _build_participant(sv_sch, "СвПрод", seller)

    # ДокПодтвОтгрНом — ссылка на документ-основание (договор/накладная)
    if basis.get("name") or basis.get("number"):
        dok = SubElement(sv_sch, "ДокПодтвОтгрНом")
        dok.set("РеквНаимДок",  basis.get("name")   or "Договор")
        dok.set("РеквНомерДок", basis.get("number") or "б/н")
        dok.set("РеквДатаДок",  basis.get("date")   or _now_date())

    _build_participant(sv_sch, "СвПокуп", buyer)

    # Платёжный документ (строка 5 счёт-фактуры)
    if payment.get("number"):
        sv_prd = SubElement(sv_sch, "СвПРД")
        sv_prd.set("НомерПРД", payment["number"])
        if payment.get("date"):
            sv_prd.set("ДатаПРД", payment["date"])

    # Валюта
    den = SubElement(sv_sch, "ДенИзм")
    den.set("КодОКВ",  str(currency.get("code", "643")))
    den.set("НаимОКВ", currency.get("name", "Российский рубль"))

    # ── ТаблСчФакт ────────────────────────────────────────────────────────────
    tabl = SubElement(document, "ТаблСчФакт")
    vat_rate = items[0].get("vat_rate", "без НДС") if items else "без НДС"
    for i, item in enumerate(items, start=1):
        _build_item(tabl, item, i)
    _build_totals(tabl, totals, vat_rate)

    # ── Подписант — для СЧФ без атрибута Должн ───────────────────────────────
    podp = SubElement(document, "Подписант")
    podp.set("СпосПодтПолном", "1")
    fio = SubElement(podp, "ФИО")
    fio.set("Фамилия", ".")
    fio.set("Имя", ".")

    return _prettify(root)
