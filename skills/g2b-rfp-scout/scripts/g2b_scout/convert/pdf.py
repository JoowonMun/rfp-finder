"""PDF 텍스트 추출. 스캔본(이미지)은 빈 문자열이 나온다."""
from __future__ import annotations

import logging
from pathlib import Path

import pdfplumber

logging.getLogger("pdfminer").setLevel(logging.ERROR)


def extract(path: Path) -> str:
    with pdfplumber.open(str(path)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages).strip()
