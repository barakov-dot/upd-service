"""Конфигурация: .env читается автоматически, переменные окружения приоритетнее."""
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
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(ROOT / ".env")


def _chain(plural: str, singular: str, default: str) -> list:
    """Цепочка моделей: GROQ_*_MODELS (через запятую) или одиночная GROQ_*_MODEL."""
    raw = os.environ.get(plural) or os.environ.get(singular) or default
    return [m.strip() for m in raw.split(",") if m.strip()]


GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
VISION_MODELS = _chain("GROQ_VISION_MODELS", "GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
TEXT_MODELS = _chain("GROQ_TEXT_MODELS", "GROQ_TEXT_MODEL", "qwen/qwen3.8-27b,openai/gpt-oss-120b")
TIMEOUT = float(os.environ.get("GROQ_TIMEOUT", "90"))
MAX_PAGES = int(os.environ.get("MAX_PAGES", "3"))  # сколько страниц скана отправлять в vision

# Прокси для запросов к Groq (если сервер в регионе, который Groq блокирует → 403):
# GROQ_PROXY=http://user:pass@host:port
GROQ_PROXY = os.environ.get("GROQ_PROXY", "").strip()
