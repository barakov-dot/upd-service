"""Groq: вызов с retry на лимиты и fallback по цепочке моделей."""
import json
import logging
import re
import time

import groq
import httpx
from groq import Groq

from . import config

log = logging.getLogger(__name__)


class LLMError(Exception):
    """Ошибка с понятным пользователю текстом."""


_client = None


def client() -> Groq:
    global _client
    if _client is None:
        if not config.GROQ_API_KEY:
            raise LLMError("GROQ_API_KEY не задан. Впишите ключ в .env и перезапустите сервис.")
        try:
            config.GROQ_API_KEY.encode("ascii")
        except UnicodeEncodeError:
            raise LLMError("GROQ_API_KEY содержит не-ASCII символы (похоже на заглушку). Впишите настоящий ключ gsk_…")
        http = httpx.Client(proxy=config.GROQ_PROXY, timeout=config.TIMEOUT) if config.GROQ_PROXY else None
        _client = Groq(api_key=config.GROQ_API_KEY, timeout=config.TIMEOUT, max_retries=0, http_client=http)
    return _client


def _explain(model: str, e: Exception) -> str:
    if isinstance(e, groq.AuthenticationError):
        return "Groq отклонил ключ (401). Проверьте GROQ_API_KEY."
    if isinstance(e, groq.PermissionDeniedError):
        return (f"403 Forbidden от Groq ({model}). Причины: (1) Groq блокирует IP/страну сервера — "
                "задайте GROQ_PROXY в .env; (2) модель отключена в console.groq.com → Settings → Limits "
                "(Model permissions) — включите её или смените модель.")
    if isinstance(e, groq.RateLimitError):
        return f"Лимит Groq исчерпан для {model} (429). Подождите минуту или смените модель."
    if isinstance(e, groq.NotFoundError):
        return f"Модель {model} не найдена или снята с поддержки Groq."
    if isinstance(e, (groq.APITimeoutError, groq.APIConnectionError)):
        return f"Нет связи с Groq ({type(e).__name__}). Проверьте сеть/прокси сервера."
    return f"{model}: {type(e).__name__}: {e}"


def chat(messages: list, models: list, max_tokens: int = 8192) -> tuple:
    """Возвращает (текст, модель). Пробует модели по очереди; 429 — одна пауза и повтор."""
    problems = []
    for model in models:
        for attempt in (1, 2):
            try:
                r = client().chat.completions.create(
                    model=model, messages=messages, temperature=0.0, max_tokens=max_tokens)
                return r.choices[0].message.content or "", model
            except LLMError:
                raise
            except groq.AuthenticationError as e:
                raise LLMError(_explain(model, e))
            except groq.RateLimitError as e:
                log.warning("429 на %s (попытка %d)", model, attempt)
                if attempt == 1:
                    time.sleep(min(float(getattr(e.response, "headers", {}).get("retry-after", 5)), 20))
                    continue
                problems.append(_explain(model, e))
            except (groq.PermissionDeniedError, groq.NotFoundError, groq.BadRequestError, groq.APIStatusError,
                    groq.APITimeoutError, groq.APIConnectionError) as e:
                log.exception("Ошибка Groq на %s", model)
                problems.append(_explain(model, e))
            break
    raise LLMError("Распознавание не удалось. " + " | ".join(problems))


def parse_json_safe(raw: str) -> dict:
    """Вырезает <think>…</think>, markdown и берёт JSON от первой { до последней }."""
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < 0:
        raise LLMError(f"Модель не вернула JSON: {raw[:300]!r}")
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"Модель вернула битый JSON ({e}): {raw[:300]!r}")
