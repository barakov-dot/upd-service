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
GROQ_API_KEY = (HARDCODED_KEY or os.environ.get("GROQ_API_KEY", "")).strip()
VISION_MODELS = _chain("GROQ_VISION_MODELS", "GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
TEXT_MODELS = _chain("GROQ_TEXT_MODELS", "GROQ_TEXT_MODEL", "qwen/qwen3.8-27b,openai/gpt-oss-120b")
TIMEOUT = float(os.environ.get("GROQ_TIMEOUT", "90"))
MAX_PAGES = int(os.environ.get("MAX_PAGES", "3"))  # сколько страниц скана отправлять в vision

# Прокси для запросов к Groq (если сервер в регионе, который Groq блокирует → 403):
# GROQ_PROXY=http://user:pass@host:port
GROQ_PROXY = os.environ.get("GROQ_PROXY", "").strip()


def key_hint() -> dict:
    """Безопасный отпечаток ключа для диагностики (сам ключ не раскрывается)."""
    k = GROQ_API_KEY
    return {
        "env_file": str(ENV_FILE), "env_file_exists": ENV_FILE.exists(),
        "length": len(k), "starts": k[:4], "ends": k[-4:] if len(k) > 8 else "",
        "shell_env_differs": bool(ENV_ORIGINAL) and ENV_ORIGINAL != k,
    }
