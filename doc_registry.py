"""
Реестр типов документов.
Каждый тип документа — отдельный модуль в папке doc_types/.
Добавить новый тип = создать файл doc_types/новый_тип.py

Структура плагина:
    DOC_TYPE   — строка-идентификатор ("УПД", "СЧФ", ...)
    LABEL      — человекочитаемое название
    DETECT     — функция(text) -> bool, определяет тип по тексту PDF
    PROMPT     — промпт для LLM
    build_xml  — функция(data) -> str, строит XML
"""

import importlib
import os
from pathlib import Path

# Автозагрузка всех плагинов из папки doc_types/
_PLUGINS: dict = {}

def _load_plugins():
    plugins_dir = Path(__file__).parent / "doc_types"
    if not plugins_dir.exists():
        return
    for f in sorted(plugins_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        module_name = f"doc_types.{f.stem}"
        try:
            mod = importlib.import_module(module_name)
            doc_type = getattr(mod, "DOC_TYPE", None)
            if doc_type:
                _PLUGINS[doc_type] = mod
        except Exception as e:
            print(f"[registry] Ошибка загрузки плагина {f.name}: {e}")

_load_plugins()


def detect_doc_type(text: str) -> str:
    """Определить тип документа по тексту PDF. Возвращает DOC_TYPE."""
    for doc_type, mod in _PLUGINS.items():
        detect_fn = getattr(mod, "DETECT", None)
        if detect_fn and detect_fn(text):
            return doc_type
    return "УПД"  # по умолчанию


def get_plugin(doc_type: str):
    """Получить плагин по типу документа."""
    return _PLUGINS.get(doc_type)


def get_prompt(doc_type: str) -> str:
    """Получить промпт для LLM."""
    mod = _PLUGINS.get(doc_type)
    if mod:
        return getattr(mod, "PROMPT", "")
    return ""


def build_xml(doc_type: str, data: dict) -> str:
    """Построить XML для данного типа документа."""
    mod = _PLUGINS.get(doc_type)
    if not mod:
        raise ValueError(f"Неизвестный тип документа: {doc_type}")
    fn = getattr(mod, "build_xml", None)
    if not fn:
        raise ValueError(f"Плагин {doc_type} не имеет функции build_xml")
    return fn(data)


def list_types() -> list:
    """Список всех зарегистрированных типов."""
    return [
        {"type": k, "label": getattr(v, "LABEL", k)}
        for k, v in _PLUGINS.items()
    ]
