"""DOCX(zip + XML) 본문 텍스트 추출. 표준 라이브러리만 사용."""
from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

_DOC = "word/document.xml"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def is_docx(zf: zipfile.ZipFile) -> bool:
    return _DOC in zf.namelist()


def extract(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read(_DOC))
    out: list[str] = []
    for el in root.iter():
        name = _local(el.tag)
        if name == "p":
            out.append("\n")
        elif name == "t" and el.text:
            out.append(el.text)
        elif name == "tab":
            out.append("\t")
    return "".join(out).strip()
