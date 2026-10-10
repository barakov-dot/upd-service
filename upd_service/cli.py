"""Проверка без браузера: python -m upd_service.cli файл.pdf [--xml]"""
import json
import sys

from . import pipeline, registry


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit("usage: python -m upd_service.cli файл.pdf [--xml]")
    data = pipeline.recognize(open(args[0], "rb").read())
    if "--xml" in sys.argv:
        print(registry.build_xml(data["meta"]["doc_type"], data))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
