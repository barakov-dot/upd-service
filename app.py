"""
УПД Сервис — FastAPI бэкенд
Архитектура: плагины в doc_types/, реестр в doc_registry.py

Установка:
    pip install fastapi uvicorn pymupdf groq python-multipart

Запуск:
    GROQ_API_KEY=gsk_xxx uvicorn app:app --host 0.0.0.0 --port 8000
"""

import json, base64, os, sys
from pathlib import Path

import fitz
from groq import Groq
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

# Добавляем текущую папку в путь чтобы находить doc_types/
sys.path.insert(0, str(Path(__file__).parent))
import doc_registry as registry

app = FastAPI(title="УПД Сервис")
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
TEXT_MODEL   = "llama-3.3-70b-versatile"

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

# ─── PDF утилиты ──────────────────────────────────────────────────────────────

def extract_text(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = "".join(p.get_text() for p in doc)
    doc.close()
    return text

def is_text_pdf(pdf_bytes):
    return len(extract_text(pdf_bytes).strip()) > 100

def pdf_to_image_b64(pdf_bytes, dpi=200):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
    img = pix.tobytes("jpeg")
    doc.close()
    return base64.b64encode(img).decode()

def pdf_to_preview_b64(pdf_bytes):
    # Весь PDF для PDF.js в браузере
    return base64.b64encode(pdf_bytes).decode()

def parse_json_safe(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.split("\n") if not l.startswith("```"))
    return json.loads(raw)

# ─── Распознавание ────────────────────────────────────────────────────────────

def recognize(pdf_bytes: bytes) -> dict:
    # 1. Определяем тип документа по тексту
    text = extract_text(pdf_bytes)
    doc_type = registry.detect_doc_type(text)

    # 2. Берём промпт из плагина
    user_prompt = registry.get_prompt(doc_type)
    if not user_prompt:
        raise ValueError(f"Нет промпта для типа: {doc_type}")

    # 3. Распознаём
    if is_text_pdf(pdf_bytes):
        full_prompt = user_prompt + f"\n\nТЕКСТ ДОКУМЕНТА:\n{text}"
        resp = client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": full_prompt}
            ],
            temperature=0.0, max_tokens=4096,
        )
    else:
        img_b64 = pdf_to_image_b64(pdf_bytes)
        resp = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    {"type": "text",      "text": user_prompt}
                ]}
            ],
            temperature=0.0, max_tokens=4096,
        )

    data = parse_json_safe(resp.choices[0].message.content)

    # Гарантируем что doc_type записан в meta
    data.setdefault("meta", {})["doc_type"] = doc_type

    return data

# ─── API ─────────────────────────────────────────────────────────────────────

@app.post("/api/recognize")
async def api_recognize(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Только PDF файлы")
    pdf_bytes = await file.read()
    try:
        data = recognize(pdf_bytes)
    except Exception as e:
        raise HTTPException(500, f"Ошибка распознавания: {e}")
    return JSONResponse({
        "data": data,
        "preview": pdf_to_preview_b64(pdf_bytes),
        "filename": file.filename,
        "doc_type": data.get("meta", {}).get("doc_type", "УПД"),
    })


class GenerateRequest(BaseModel):
    data: dict

def _make_filename(req_data):
    doc    = req_data.get("document", {})
    seller = req_data.get("seller", {})
    date_str = (doc.get("date") or "").replace(".", "")
    inn      = seller.get("inn", "0000000000")
    return f"ON_NSCHFDOPPR_{inn}_{date_str}.xml"

@app.post("/api/preview-xml")
async def api_preview_xml(req: GenerateRequest):
    """Превью XML для браузера — возвращает UTF-8 строку"""
    doc_type = req.data.get("meta", {}).get("doc_type", "УПД")
    try:
        xml_content = registry.build_xml(doc_type, req.data)
    except Exception as e:
        raise HTTPException(500, f"Ошибка генерации XML: {e}")
    # Отдаём как JSON со строкой — браузер покажет без проблем с кодировкой
    return JSONResponse({"xml": xml_content, "filename": _make_filename(req.data)})

@app.post("/api/generate-xml")
async def api_generate_xml(req: GenerateRequest):
    """Скачивание XML для 1С — windows-1251 как требует ФНС"""
    doc_type = req.data.get("meta", {}).get("doc_type", "УПД")
    try:
        xml_content = registry.build_xml(doc_type, req.data)
    except Exception as e:
        raise HTTPException(500, f"Ошибка генерации XML: {e}")
    filename = _make_filename(req.data)
    return Response(
        content=xml_content.encode("windows-1251"),
        media_type="application/xml; charset=windows-1251",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

class EncodeRequest(BaseModel):
    xml: str

@app.post("/api/encode-xml")
async def api_encode_xml(req: EncodeRequest):
    """Перекодировать отредактированный XML из UTF-8 в windows-1251 для скачивания"""
    try:
        encoded = req.xml.encode("windows-1251")
    except UnicodeEncodeError as e:
        raise HTTPException(400, f"Символы вне windows-1251: {e}")
    return Response(
        content=encoded,
        media_type="application/xml; charset=windows-1251",
        headers={"Content-Disposition": 'attachment; filename="edited.xml"'},
    )

@app.get("/api/doc-types")
async def api_doc_types():
    """Список поддерживаемых типов документов"""
    return registry.list_types()

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("index.html", encoding="utf-8") as f:
        return f.read()
