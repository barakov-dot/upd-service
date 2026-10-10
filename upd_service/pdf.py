"""Работа с PDF: текст, рендер страниц, превью."""
import base64

import pymupdf as fitz


def extract_text(pdf_bytes: bytes) -> str:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return "".join(p.get_text() for p in doc)


def is_text_pdf(text: str) -> bool:
    return len(text.strip()) > 100


def render_pages_b64(pdf_bytes: bytes, max_pages: int = 1, dpi: int = 200, rotation: int = 0) -> list:
    """Первые max_pages страниц в JPEG (base64)."""
    out = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i in range(min(max_pages, len(doc))):
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            if rotation:
                mat = mat.prerotate(rotation)
            out.append(base64.b64encode(doc[i].get_pixmap(matrix=mat).tobytes("jpeg")).decode())
    return out


def preview_b64(pdf_bytes: bytes, rotation: int = 0) -> str:
    """'pdf:<b64>' для нативного iframe или 'img:<b64>' если нужен поворот."""
    if rotation:
        return "img:" + render_pages_b64(pdf_bytes, 1, dpi=150, rotation=rotation)[0]
    return "pdf:" + base64.b64encode(pdf_bytes).decode()
