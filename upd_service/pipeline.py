"""PDF → тип документа → LLM → dict."""
import logging

from . import config, llm, pdf, registry

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты — эксперт по распознаванию российских бухгалтерских документов.
Твоя задача — извлечь данные из документа и вернуть их строго в формате JSON.
ПРАВИЛА:
1. Возвращай ТОЛЬКО валидный JSON, без пояснений, без markdown, без комментариев.
2. Если поле не найдено — ставь null.
3. Суммы пиши с точкой: "285714.29"
4. Даты строго ДД.ММ.ГГГГ: "30.11.2025"
5. ИНН/КПП — только цифры, без пробелов.
6. Налоговую ставку точно как в документе: "5%", "20%", "22%", "10%", "без НДС"
"""


def recognize(pdf_bytes: bytes) -> dict:
    text = pdf.extract_text(pdf_bytes)
    doc_type = registry.detect_doc_type(text)
    prompt = registry.get_prompt(doc_type)
    if not prompt:
        raise llm.LLMError(f"Нет промпта для типа: {doc_type}")

    if pdf.is_text_pdf(text):
        user = prompt + f"\n\nТЕКСТ ДОКУМЕНТА:\n{text}"
        models = config.TEXT_MODELS
    else:
        images = pdf.render_pages_b64(pdf_bytes, max_pages=config.MAX_PAGES)
        user = [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}} for b in images]
        user.append({"type": "text", "text": prompt})
        models = config.VISION_MODELS

    raw, model = llm.chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}], models)
    log.info("Распознано моделью %s, тип %s", model, doc_type)

    data = llm.parse_json_safe(raw)
    meta = data.setdefault("meta", {})
    meta["doc_type"] = doc_type
    meta["model"] = model
    try:
        meta["rotation"] = int(meta.get("rotation") or 0)
    except (TypeError, ValueError):
        meta["rotation"] = 0
    return data
