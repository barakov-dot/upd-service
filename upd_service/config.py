"""Конфигурация: .env читается автоматически и ПЕРЕКРЫВАЕТ переменные окружения
(чтобы старый экспорт в оболочке/systemd не подменял ключ)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")


ENV_FILE = ROOT / ".env"
ENV_ORIGINAL = os.environ.get("GROQ_API_KEY", "")  # что было в окружении до чтения .env
_load_env(ENV_FILE)


def _chain(plural: str, singular: str, default: str) -> list:
    """Цепочка моделей: GROQ_*_MODELS (через запятую) или одиночная GROQ_*_MODEL."""
    raw = os.environ.get(plural) or os.environ.get(singular) or default
    return [m.strip() for m in raw.split(",") if m.strip()]


# Жёсткая прошивка ключа (только на сервере, не коммитить!). Если не пусто — .env игнорируется.
HARDCODED_KEY = ""
def _keys() -> list:
    """Пул ключей: HARDCODED_KEY, GROQ_API_KEYS (через запятую) и GROQ_API_KEY, без дублей."""
    raw = [HARDCODED_KEY] + os.environ.get("GROQ_API_KEYS", "").split(",") + [os.environ.get("GROQ_API_KEY", "")]
    out = []
    for k in (x.strip() for x in raw):
        if k and k not in out:
            out.append(k)
    return out


GROQ_API_KEYS = _keys()
GROQ_API_KEY = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""
VISION_MODELS = _chain("GROQ_VISION_MODELS", "GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
TEXT_MODELS = _chain("GROQ_TEXT_MODELS", "GROQ_TEXT_MODEL", "qwen/qwen3.8-27b,openai/gpt-oss-120b")
TIMEOUT = float(os.environ.get("GROQ_TIMEOUT", "90"))
MAX_PAGES = int(os.environ.get("MAX_PAGES", "3"))  # сколько страниц скана отправлять в vision

# Прокси для запросов к Groq (если сервер в регионе, который Groq блокирует → 403):
# GROQ_PROXY=http://user:pass@host:port
GROQ_PROXY = os.environ.get("GROQ_PROXY", "").strip()


def mask_key(k: str) -> str:
    return f"{k[:4]}…{k[-4:]} (длина {len(k)})" if len(k) > 8 else f"<короткий ключ, длина {len(k)}>"


# ── Очередь ──
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "1"))      # сколько документов распознаётся одновременно
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
JOB_TTL_MIN = int(os.environ.get("JOB_TTL_MIN", "30"))           # сколько хранить результат в памяти

# ── Авторизация ──
# AUTH_USERS=алекс:пароль1,иван:пароль2 ; если пусто — вход не требуется (только для разработки!)
AUTH_USERS = {}
for _pair in os.environ.get("AUTH_USERS", "").split(","):
    if ":" in _pair:
        _u, _p = _pair.split(":", 1)
        if _u.strip() and _p:
            AUTH_USERS[_u.strip()] = _p
AUTH_SECRET = os.environ.get("AUTH_SECRET", "") or os.urandom(32).hex()  # без AUTH_SECRET сессии сбрасываются при рестарте
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "12"))
