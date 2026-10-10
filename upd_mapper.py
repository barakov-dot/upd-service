"""
Маппер JSON → XML по схеме ON_NSCHFDOPPR v5.03
Структура выверена по рабочему эталонному XML из 1С.
"""

import json, sys, uuid
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


def make_file_id(seller_inn, doc_date):
    date_str = (doc_date or "").replace(".", "")
    uid = str(uuid.uuid4()).upper()
    return f"ON_NSCHFDOPPR_{seller_inn}_{date_str}_{uid}"

def now_date(): return datetime.now().strftime("%d.%m.%Y")
def now_time(): return datetime.now().strftime("%H.%M.%S")

def prettify(element):
    raw = tostring(element, encoding="unicode")
    parsed = minidom.parseString(raw)
    pretty = parsed.toprettyxml(indent="\t", encoding="windows-1251")
    lines = [l for l in pretty.decode("windows-1251").split("\n") if l.strip()]
    return "\n".join(lines)


def clean_inn(v):
    """ИНН юрлица — ровно 10 цифр"""
    if not v: return ""
    digits = "".join(c for c in str(v) if c.isdigit())
    return digits[:10]

def clean_kpp(v):
    """КПП — ровно 9 символов (цифры + A-Z на 5-6 позиции)"""
    if not v: return None
    # Оставляем только цифры и буквы верхнего регистра
    clean = "".join(c for c in str(v).upper() if c.isdigit() or c.isalpha())
    # КПП всегда 9 символов — берём последние 9 если длиннее
    if len(clean) > 9:
        clean = clean[-9:]
    return clean if len(clean) == 9 else None

def build_participant(parent, tag, data):
    """
    УчастникТип: ИдСв/СвЮЛУч + Адрес/АдрИнф
    АдрИнф: КодСтр(req), НаимСтран(req), АдрТекст(opt)
    """
    el = SubElement(parent, tag)
    id_sv = SubElement(el, "ИдСв")
    sv_yul = SubElement(id_sv, "СвЮЛУч")
    sv_yul.set("НаимОрг", data.get("name", ""))
    sv_yul.set("ИННЮЛ", clean_inn(data.get("inn", "")))
    kpp = clean_kpp(data.get("kpp"))
    if kpp:
        sv_yul.set("КПП", kpp)
    if data.get("address"):
        addr = SubElement(el, "Адрес")
        ai = SubElement(addr, "АдрИнф")
        ai.set("КодСтр", "643")
        ai.set("НаимСтран", "РОССИЯ")
        ai.set("АдрТекст", data["address"])
    return el


def build_excise(parent, val):
    """СумАкцизТип: <Акциз><БезАкциз>без акциза</БезАкциз></Акциз>"""
    akc = SubElement(parent, "Акциз")
    v = (val or "").strip().lower()
    if v in ("без акциза", "нет", "", "null"):
        SubElement(akc, "БезАкциз").text = "без акциза"
    else:
        SubElement(akc, "СумАкциз").text = str(val)


def build_vat(parent, vat_rate, vat_amount, container_tag="СумНал"):
    """
    СумНДСТип: xs:choice <СумНал>decimal</СумНал> | <БезНДС>без НДС</БезНДС>
    container_tag = "СумНал"      — для строки СведТов
    container_tag = "СумНалВсего" — для ВсегоОпл
    """
    container = SubElement(parent, container_tag)
    rate = (vat_rate or "").strip().lower()
    if rate in ("без ндс", "без нал", ""):
        SubElement(container, "БезНДС").text = "без НДС"
    else:
        SubElement(container, "СумНал").text = str(vat_amount or "0.00")


def build_item(parent, item, line_num):
    """
    СведТов атрибуты: НомСтр(req), НаимТов, ОКЕИ_Тов, НаимЕдИзм,
                      КолТов, ЦенаТов, НалСт(req), СтТовБезНДС, СтТовУчНал
    Дочерние: [ДопСведТов], Акциз, СумНал
    """
    sv = SubElement(parent, "СведТов")
    sv.set("НомСтр", str(line_num))
    sv.set("НаимТов", item.get("name", ""))
    if item.get("unit_code"):
        sv.set("ОКЕИ_Тов", str(item["unit_code"]))
    if item.get("unit_name"):
        sv.set("НаимЕдИзм", item["unit_name"])
    if item.get("quantity"):
        sv.set("КолТов", str(item["quantity"]))
    if item.get("price"):
        sv.set("ЦенаТов", str(item["price"]))
    sv.set("НалСт", str(item.get("vat_rate", "без НДС")))
    if item.get("amount_without_vat"):
        sv.set("СтТовБезНДС", str(item["amount_without_vat"]))
    if item.get("amount_with_vat"):
        sv.set("СтТовУчНал", str(item["amount_with_vat"]))
    build_excise(sv, item.get("excise", "без акциза"))
    build_vat(sv, item.get("vat_rate"), item.get("vat_amount"),
              container_tag="СумНал")


def build_totals(parent, totals, vat_rate):
    """
    ВсегоОпл: СтТовБезНДСВсего, СтТовУчНалВсего + дочерний СумНалВсего
    """
    vsego = SubElement(parent, "ВсегоОпл")
    vsego.set("СтТовБезНДСВсего", str(totals.get("amount_without_vat", "0.00")))
    vsego.set("СтТовУчНалВсего", str(totals.get("amount_with_vat", "0.00")))
    build_vat(vsego, vat_rate, totals.get("vat_amount"),
              container_tag="СумНалВсего")


def build_xml(data):
    doc      = data.get("document", {})
    seller   = data.get("seller", {})
    buyer    = data.get("buyer", {})
    items    = data.get("items", [])
    totals   = data.get("totals", {})
    transfer = data.get("transfer", {})
    payment  = data.get("payment_doc", {})
    currency = data.get("currency", {"code": "643", "name": "Российский рубль"})

    # ── Файл
    root = Element("Файл")
    root.set("ИдФайл", make_file_id(seller.get("inn","0"), doc.get("date","")))
    root.set("ВерсФорм", "5.03")
    root.set("ВерсПрог", "УПД Сервис 1.0")

    # ── Документ
    # Порядок атрибутов как в эталоне: КНД, ВремИнфПр, ДатаИнфПр,
    # ПоФактХЖ, НаимДокОпр, НаимЭконСубСост, Функция
    document = SubElement(root, "Документ")
    document.set("КНД", "1115131")
    document.set("ВремИнфПр", now_time())
    document.set("ДатаИнфПр", now_date())
    document.set("ПоФактХЖ",
        "Документ об отгрузке товаров (выполнении работ), передаче имущественных прав "
        "(документ об оказании услуг)")
    document.set("НаимДокОпр", "Универсальный передаточный документ")
    # НаимЭконСубСост — как в эталоне: "НаимОрг, ИНН/КПП ИНН/КПП"
    inn_kpp = f"{seller.get('inn','')}/{seller.get('kpp','')}" if seller.get('kpp') else seller.get('inn','')
    document.set("НаимЭконСубСост", f"{seller.get('name','')}, ИНН/КПП {inn_kpp}")
    document.set("Функция", doc.get("function", "СЧФДОП"))

    # ── СвСчФакт
    sv_sch = SubElement(document, "СвСчФакт")
    sv_sch.set("НомерДок", doc.get("number", ""))
    sv_sch.set("ДатаДок", doc.get("date", ""))

    if doc.get("correction_number") and doc.get("correction_date"):
        ispr = SubElement(sv_sch, "ИспрДок")
        ispr.set("НомИспр", str(doc["correction_number"]))
        ispr.set("ДатаИспр", doc["correction_date"])

    # Порядок дочерних элементов СвСчФакт строго по эталону:
    # СвПрод → ГрузПолуч(opt) → ДокПодтвОтгрНом(opt) → СвПокуп → ДенИзм → ДопСвФХЖ1

    build_participant(sv_sch, "СвПрод", seller)

    # ДокПодтвОтгрНом — тип РеквДокТип: РеквНаимДок(req), РеквНомерДок(req), РеквДатаДок(req)
    # Ссылается на сам этот документ (УПД является одновременно документом-основанием)
    dok_podtv = SubElement(sv_sch, "ДокПодтвОтгрНом")
    dok_podtv.set("РеквНаимДок", "Универсальный передаточный документ")
    dok_podtv.set("РеквНомерДок", doc.get("number", ""))
    dok_podtv.set("РеквДатаДок", doc.get("date", ""))

    build_participant(sv_sch, "СвПокуп", buyer)

    # ДенИзм: КодОКВ(req), НаимОКВ(req)
    den = SubElement(sv_sch, "ДенИзм")
    den.set("НаимОКВ", currency.get("name", "Российский рубль"))
    den.set("КодОКВ", str(currency.get("code", "643")))

    # ДопСвФХЖ1 — пустой элемент, обязателен в эталоне
    SubElement(sv_sch, "ДопСвФХЖ1")

    # ── ТаблСчФакт
    tabl = SubElement(document, "ТаблСчФакт")
    vat_rate = items[0].get("vat_rate", "без НДС") if items else "без НДС"
    for i, item in enumerate(items, start=1):
        build_item(tabl, item, i)
    build_totals(tabl, totals, vat_rate)

    # ── СвПродПер
    # СвПер: @СодОпер(opt), @ДатаПер(req)
    # ОснПер тип РеквДокТип: @РеквНаимДок(req), @РеквНомерДок(req), @РеквДатаДок(req)
    sv_prod_per = SubElement(document, "СвПродПер")
    sv_per = SubElement(sv_prod_per, "СвПер")
    sv_per.set("СодОпер", "Товары переданы, работы сданы, услуги оказаны")
    if transfer.get("date"):
        sv_per.set("ДатаПер", transfer["date"])

    has_basis = any(transfer.get(k) for k in
                    ("basis_doc_name", "basis_doc_number", "basis_doc_date"))
    if has_basis:
        osn = SubElement(sv_per, "ОснПер")
        osn.set("РеквНаимДок", transfer.get("basis_doc_name") or "Договор")
        osn.set("РеквНомерДок", transfer.get("basis_doc_number") or "б/н")
        osn.set("РеквДатаДок", transfer.get("basis_doc_date") or now_date())
    else:
        SubElement(sv_per, "БезДокОснПер").text = "1"

    # ── Подписант — обязателен в схеме 5.03
    # В эталоне: <Подписант СпосПодтПолном="1" Должн="..."><ФИО .../></Подписант>
    # СпосПодтПолном: 1=должностное лицо, 2=уполномоченный представитель
    # Поскольку подписанты в 1С подставляются отдельно,
    # ставим заглушку которую 1С примет и перезапишет
    podp = SubElement(document, "Подписант")
    podp.set("СпосПодтПолном", "1")
    podp.set("Должн", "Руководитель")
    fio = SubElement(podp, "ФИО")
    fio.set("Фамилия", ".")
    fio.set("Имя", ".")

    return prettify(root)


def main():
    if len(sys.argv) < 2:
        print("Использование: python3 upd_mapper.py упд_result.json")
        sys.exit(1)
    json_path = Path(sys.argv[1])
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    print(f"📥 {json_path.name} | № {data['document']['number']} от {data['document']['date']}")
    xml_content = build_xml(data)
    date_str = data["document"]["date"].replace(".", "")
    inn = data["seller"]["inn"]
    out = json_path.parent / f"ON_NSCHFDOPPR_{inn}_{date_str}.xml"
    with open(out, "w", encoding="windows-1251") as f:
        f.write(xml_content)
    print(f"✅ XML: {out}\n")
    print(xml_content)

if __name__ == "__main__":
    main()
