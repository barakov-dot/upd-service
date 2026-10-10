"""Groq: пул ключей (при лимите берётся следующий), fallback по цепочке моделей, понятные ошибки."""
import json
import logging
import re
import threading
import time

import groq
import httpx
from groq import Groq

from . import config

log = logging.getLogger(__name__)


class LLMError(Exception):
    """Ошибка с понятным пользователю текстом."""


_clients: dict = {}
_cooldown: dict = {}   # (ключ, модель) -> unix-время, до которого ключ на лимите
_dead: set = set()     # ключи, которые Groq отверг (401)
_lock = threading.Lock()


def _client(key: str) -> Groq:
    with _lock:
        if key not in _clients:
            http = httpx.Client(proxy=config.GROQ_PROXY, timeout=config.TIMEOUT) if config.GROQ_PROXY else None
            _clients[key] = Groq(api_key=key, timeout=config.TIMEOUT, max_retries=0, http_client=http)
        return _clients[key]


def _explain(model: str, e: Exception) -> str:
    if isinstance(e, groq.AuthenticationError):
        return "Groq отклонил ключ (401)."
    if isinstance(e, groq.PermissionDeniedError):
        return (f"403 Forbidden ({model}): Groq блокирует IP/страну сервера (нужен GROQ_PROXY) "
                "или модель выключена в console.groq.com → Settings → Limits.")
    if isinstance(e, groq.RateLimitError):
        return f"лимит {model} исчерпан (429)."
    if isinstance(e, groq.NotFoundError):
        return f"модель {model} не найдена или снята с поддержки."
    if isinstance(e, (groq.APITimeoutError, groq.APIConnectionError)):
        return f"нет связи с Groq ({type(e).__name__})."
    return f"{model}: {type(e).__name__}: {e}"


def _retry_after(e) -> float:
    try:
        return float(e.response.headers.get("retry-after", 60))
    except Exception:
        return 60.0


def chat(messages: list, models: list, max_tokens: int = 8192, only_key: str = None) -> tuple:
    """(текст, модель). Для каждой модели перебирает ключи; на 429 ключ «остывает» и берётся следующий."""
    keys = [only_key] if only_key else list(config.GROQ_API_KEYS)
    if not keys:
        raise LLMError("Не задан ни один ключ Groq (GROQ_API_KEY / GROQ_API_KEYS в .env).")
    problems, soonest = [], None
    for model in models:
        for key in keys:
            if key in _dead and not only_key:
                continue
            until = _cooldown.get((key, model), 0)
            if until > time.time() and not only_key:
                soonest = min(soonest or until, until)
                continue
            try:
                key.encode("ascii")
            except UnicodeEncodeError:
                problems.append(f"ключ {config.mask_key(key)} содержит не-ASCII символы (заглушка?).")
                continue
            try:
                r = _client(key).chat.completions.create(
                    model=model, messages=messages, temperature=0.0, max_tokens=max_tokens)
                return r.choices[0].message.content or "", model
            except groq.AuthenticationError as e:
                _dead.add(key)
                problems.append(f"ключ {config.mask_key(key)}: {_explain(model, e)}")
            except groq.RateLimitError as e:
                wait = min(max(_retry_after(e), 5), 3600)
                _cooldown[(key, model)] = time.time() + wait
                soonest = min(soonest or time.time() + wait, time.time() + wait)
                log.warning("429: ключ %s на %s, пауза %.0f с — пробую следующий", config.mask_key(key), model, wait)
                problems.append(f"ключ {config.mask_key(key)}: {_explain(model, e)}")
            except groq.APIError as e:
                log.exception("Ошибка Groq: %s", model)
                problems.append(f"ключ {config.mask_key(key)}: {_explain(model, e)}")
    if soonest and not only_key:
        mins = max(1, int((soonest - time.time()) / 60) + 1)
        raise LLMError(f"Лимиты всех ключей исчерпаны. Освободится примерно через {mins} мин. "
                       "Добавьте ещё ключи в GROQ_API_KEYS (с других аккаунтов Groq).")
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
