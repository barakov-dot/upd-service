"""FastAPI-роуты. Запуск: uvicorn upd_service.api:app --port 8000"""
import logging
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from . import auth, config, llm, registry
from .jobs import queue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_):
    queue.start()
    if not auth.enabled():
        log.warning("AUTH_USERS не задан — сервис открыт без пароля!")
    yield


app = FastAPI(title="УПД Сервис", lifespan=lifespan)
STATIC = Path(__file__).parent / "static"
User = Depends(auth.current_user)

# 1×1 PNG — проверка, что vision-модель вообще принимает картинки
_PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


@app.post("/api/recognize")
async def api_recognize(file: UploadFile = File(...), user: str = User):
    """Ставит файл в очередь, возвращает job_id. Результат — GET /api/jobs/{id}."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Только PDF файлы")
    pdf_bytes = await file.read()
    if len(pdf_bytes) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Файл больше {config.MAX_UPLOAD_MB} МБ")
    job = queue.submit(user, file.filename, pdf_bytes)
    return queue.view(job)


@app.get("/api/jobs/{job_id}")
async def api_job(job_id: str, user: str = User):
    job = queue.jobs.get(job_id)
    if not job or job.user != user:
        raise HTTPException(404, "Задача не найдена (возможно, истёк срок хранения)")
    return JSONResponse(queue.view(job))


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
async def api_preview_xml(req: GenerateRequest, user: str = User):
    return JSONResponse({"xml": _build(req.data), "filename": _filename(req.data)})


@app.post("/api/generate-xml")
async def api_generate_xml(req: GenerateRequest, user: str = User):
    return Response(
        content=_build(req.data).encode("windows-1251"),
        media_type="application/xml; charset=windows-1251",
        headers={"Content-Disposition": f'attachment; filename="{_filename(req.data)}"'})


class EncodeRequest(BaseModel):
    xml: str


@app.post("/api/encode-xml")
async def api_encode_xml(req: EncodeRequest, user: str = User):
    try:
        encoded = req.xml.encode("windows-1251")
    except UnicodeEncodeError as e:
        raise HTTPException(400, f"Символы вне windows-1251: {e}")
    return Response(content=encoded, media_type="application/xml; charset=windows-1251",
                    headers={"Content-Disposition": 'attachment; filename="edited.xml"'})


@app.get("/api/health")
async def api_health(user: str = User):
    """Каждый ключ × каждая модель (текст и vision). Тратит несколько мелких запросов."""
    info = {"keys_count": len(config.GROQ_API_KEYS), "doc_types": [t["type"] for t in registry.list_types()],
            "queue": {"running": sum(j.status == "running" for j in queue.jobs.values()),
                      "waiting": len(queue.waiting), "max_concurrent": config.MAX_CONCURRENT},
            "auth": auth.enabled(), "keys": {}}
    msgs_text = [{"role": "user", "content": "Ответь одним словом: ок"}]
    msgs_img = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_PIXEL}"}},
        {"type": "text", "text": "Ответь одним словом: ок"}]}]
    ok_text = ok_vision = False
    for key in config.GROQ_API_KEYS:
        res = {"text": {}, "vision": {}}
        for kind, models, msgs in (("text", config.TEXT_MODELS, msgs_text), ("vision", config.VISION_MODELS, msgs_img)):
            for m in models:
                try:
                    llm.chat(msgs, [m], max_tokens=200, only_key=key)
                    res[kind][m] = "OK"
                    ok_text |= kind == "text"
                    ok_vision |= kind == "vision"
                except llm.LLMError as e:
                    res[kind][m] = f"ОШИБКА: {e}"
        info["keys"][config.mask_key(key)] = res
    info["ok"] = ok_text and ok_vision
    return info


@app.get("/api/doc-types")
async def api_doc_types(user: str = User):
    return registry.list_types()


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/login")
async def api_login(req: LoginRequest, request: Request):
    if not auth.enabled():
        return {"ok": True}
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    if not auth.check_password(ip, req.username.strip(), req.password):
        raise HTTPException(401, "Неверный логин или пароль")
    resp = JSONResponse({"ok": True, "user": req.username.strip()})
    resp.set_cookie(auth.COOKIE, auth.make_token(req.username.strip()), httponly=True, samesite="lax",
                    max_age=config.SESSION_HOURS * 3600)
    return resp


@app.post("/api/logout")
async def api_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE)
    return resp


@app.get("/api/me")
async def api_me(user: str = User):
    return {"user": user, "auth": auth.enabled()}


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return (STATIC / "login.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if auth.enabled() and not auth.read_token(request.cookies.get(auth.COOKIE, "")):
        return RedirectResponse("/login")
    return (STATIC / "index.html").read_text(encoding="utf-8")
