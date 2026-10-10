"""Реестр типов документов: плагин = модуль в doc_types/ с DOC_TYPE, LABEL, DETECT, PROMPT, build_xml."""
import importlib
import logging
from pathlib import Path

log = logging.getLogger(__name__)
_PLUGINS: dict = {}


def _load_plugins():
    for f in sorted((Path(__file__).parent / "doc_types").glob("*.py")):
        if f.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"upd_service.doc_types.{f.stem}")
            if getattr(mod, "DOC_TYPE", None):
                _PLUGINS[mod.DOC_TYPE] = mod
        except Exception:
            log.exception("Ошибка загрузки плагина %s", f.name)


_load_plugins()


def detect_doc_type(text: str) -> str:
    for doc_type, mod in _PLUGINS.items():
        fn = getattr(mod, "DETECT", None)
        if fn and fn(text):
            return doc_type
    return "УПД"


def get_prompt(doc_type: str) -> str:
    mod = _PLUGINS.get(doc_type)
    return getattr(mod, "PROMPT", "") if mod else ""


def build_xml(doc_type: str, data: dict) -> str:
    mod = _PLUGINS.get(doc_type)
    if not mod or not getattr(mod, "build_xml", None):
        raise ValueError(f"Неизвестный тип документа: {doc_type}")
    return mod.build_xml(data)


def list_types() -> list:
    return [{"type": k, "label": getattr(v, "LABEL", k)} for k, v in _PLUGINS.items()]
