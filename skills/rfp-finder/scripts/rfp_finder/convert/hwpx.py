"""HWPX(zip + XML) 본문 텍스트 추출. 표준 라이브러리만 사용."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

_SECTION = re.compile(r"Contents/section(\d+)\.xml")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _walk(el, out: list[str]) -> None:
    name = _local(el.tag)
    if name == "p":
        out.append("\n")
    if name == "t":
        out.append("".join(el.itertext()))
        return
    for child in el:
        _walk(child, out)


def is_hwpx(zf: zipfile.ZipFile) -> bool:
    return any(_SECTION.fullmatch(n) for n in zf.namelist())


def extract(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        sections = sorted(
            (n for n in zf.namelist() if _SECTION.fullmatch(n)),
            key=lambda n: int(_SECTION.fullmatch(n).group(1)),
        )
        if not sections:
            raise ValueError("HWPX 본문 섹션 없음")
        out: list[str] = []
        for s in sections:
            _walk(ET.fromstring(zf.read(s)), out)
    return re.sub(r"\n{3,}", "\n\n", "".join(out)).strip()
