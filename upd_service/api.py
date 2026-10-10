"""FastAPI-роуты. Запуск: uvicorn upd_service.api:app --port 8000"""
import logging
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from . import config, llm, pdf, pipeline, registry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)
app = FastAPI(title="УПД Сервис")

# 1×1 PNG — проверка, что vision-модель вообще принимает картинки
_PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


@app.post("/api/recognize")
async def api_recognize(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Только PDF файлы")
    pdf_bytes = await file.read()
    try:
        data = pipeline.recognize(pdf_bytes)
    except llm.LLMError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        log.exception("Сбой распознавания %s", file.filename)
        raise HTTPException(500, f"Внутренняя ошибка: {type(e).__name__}: {e}")
    meta = data["meta"]
    return JSONResponse({
        "data": data,
        "preview": pdf.preview_b64(pdf_bytes, rotation=meta["rotation"]),
        "filename": file.filename,
        "doc_type": meta["doc_type"],
    })


class GenerateRequest(BaseModel):
    data: dict


def _filename(d: dict) -> str:
    date = ((d.get("document") or {}).get("date") or "").replace(".", "")
    inn = (d.get("seller") or {}).get("inn") or "0000000000"
    return f"ON_NSCHFDOPPR_{inn}_{date}.xml"


def _build(d: dict) -> str:
    try:
        return registry.build_xml((d.get("meta") or {}).get("doc_type", "УПД"), d)
    except Exception as e:
        log.exception("Ошибка генерации XML")
        raise HTTPException(500, f"Ошибка генерации XML: {e}")


@app.post("/api/preview-xml")
async def api_preview_xml(req: GenerateRequest):
    return JSONResponse({"xml": _build(req.data), "filename": _filename(req.data)})


@app.post("/api/generate-xml")
async def api_generate_xml(req: GenerateRequest):
    return Response(
        content=_build(req.data).encode("windows-1251"),
        media_type="application/xml; charset=windows-1251",
        headers={"Content-Disposition": f'attachment; filename="{_filename(req.data)}"'})


class EncodeRequest(BaseModel):
    xml: str


@app.post("/api/encode-xml")
async def api_encode_xml(req: EncodeRequest):
    try:
        encoded = req.xml.encode("windows-1251")
    except UnicodeEncodeError as e:
        raise HTTPException(400, f"Символы вне windows-1251: {e}")
    return Response(content=encoded, media_type="application/xml; charset=windows-1251",
                    headers={"Content-Disposition": 'attachment; filename="edited.xml"'})


@app.get("/api/health")
async def api_health():
    """Проверяет КАЖДУЮ модель обеих цепочек (текст и vision) — как реально работает распознавание."""
    info = {"groq_key_set": bool(config.GROQ_API_KEY), "doc_types": [t["type"] for t in registry.list_types()],
            "text_models": {}, "vision_models": {}}
    msgs_text = [{"role": "user", "content": "Ответь одним словом: ок"}]
    msgs_img = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_PIXEL}"}},
        {"type": "text", "text": "Ответь одним словом: ок"}]}]
    for key, models, msgs in (("text_models", config.TEXT_MODELS, msgs_text),
                              ("vision_models", config.VISION_MODELS, msgs_img)):
        for m in models:
            try:
                llm.chat(msgs, [m], max_tokens=200)
                info[key][m] = "OK"
            except llm.LLMError as e:
                info[key][m] = f"ОШИБКА: {e}"
    info["ok"] = any(v == "OK" for v in info["text_models"].values()) and \
        any(v == "OK" for v in info["vision_models"].values())
    return info


@app.get("/api/doc-types")
async def api_doc_types():
    return registry.list_types()


@app.get("/", response_class=HTMLResponse)
async def index():
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
