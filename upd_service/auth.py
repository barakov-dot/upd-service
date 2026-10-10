"""Вход по логину/паролю: подписанная cookie-сессия (без внешних зависимостей)."""
import base64
import hashlib
import hmac
import logging
import time

from fastapi import HTTPException, Request

from . import config

log = logging.getLogger(__name__)
COOKIE = "session"
_fails: dict = {}  # ip -> [число неудач, время блокировки до]


def enabled() -> bool:
    return bool(config.AUTH_USERS)


def _sign(payload: str) -> str:
    return hmac.new(config.AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(user: str) -> str:
    payload = base64.urlsafe_b64encode(f"{user}|{int(time.time()) + config.SESSION_HOURS * 3600}".encode()).decode()
    return f"{payload}.{_sign(payload)}"


def read_token(token: str):
    try:
        payload, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        user, exp = base64.urlsafe_b64decode(payload).decode().rsplit("|", 1)
        return user if int(exp) > time.time() and user in config.AUTH_USERS else None
    except Exception:
        return None


def check_password(ip: str, user: str, password: str) -> bool:
    n, until = _fails.get(ip, [0, 0])
    if until > time.time():
        raise HTTPException(429, f"Слишком много попыток. Повторите через {int(until - time.time()) + 1} с.")
    expected = config.AUTH_USERS.get(user)
    ok = expected is not None and hmac.compare_digest(expected.encode(), password.encode())
    if ok:
        _fails.pop(ip, None)
        return True
    n += 1
    _fails[ip] = [n, time.time() + 60 if n >= 5 else 0]
    if n >= 5:
        _fails[ip][0] = 0
    log.warning("Неудачный вход: %s с %s", user, ip)
    return False


def current_user(request: Request) -> str:
    """Зависимость FastAPI: имя пользователя или 401. Если авторизация не настроена — 'anonymous'."""
    if not enabled():
        return "anonymous"
    user = read_token(request.cookies.get(COOKIE, ""))
    if not user:
        raise HTTPException(401, "Требуется вход")
    return user
