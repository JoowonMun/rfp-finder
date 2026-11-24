"""HWP 5.x(OLE) 본문 텍스트 추출. BodyText/Section* 의 HWPTAG_PARA_TEXT 레코드를 읽는다."""
from __future__ import annotations

import re
import zlib
from pathlib import Path

import olefile

HWPTAG_PARA_TEXT = 67
_SINGLE = {0, 10, 13} | set(range(24, 32))  # 1 wchar 짜리 제어문자


def _records(data: bytes):
    i, n = 0, len(data)
    while i + 4 <= n:
        h = int.from_bytes(data[i : i + 4], "little")
        i += 4
        tag, size = h & 0x3FF, (h >> 20) & 0xFFF
        if size == 0xFFF:
            size = int.from_bytes(data[i : i + 4], "little")
            i += 4
        yield tag, data[i : i + size]
        i += size


def _para_text(payload: bytes) -> str:
    units = bytearray()  # 일반 문자의 UTF-16LE 코드 유닛 (서로게이트 쌍 보존)
    i, n = 0, len(payload) // 2
    while i < n:
        raw = payload[2 * i : 2 * i + 2]
        c = int.from_bytes(raw, "little")
        if c >= 32:
            units += raw
            i += 1
        elif c in _SINGLE:
            if c == 10:
                units += "\n".encode("utf-16-le")
            i += 1
        else:
            if c == 9:
                units += "\t".encode("utf-16-le")
            i += 8  # 인라인/확장 제어문자는 8 wchar
    return units.decode("utf-16-le", errors="replace")


def extract(path: Path) -> str:
    with olefile.OleFileIO(str(path)) as ole:
        header = ole.openstream("FileHeader").read()
        if not header.startswith(b"HWP Document File"):
            raise ValueError("HWP 헤더 아님")
        flags = int.from_bytes(header[36:40], "little")
        if flags & 0x2:
            raise ValueError("암호가 걸린 HWP")
        if flags & 0x4:
            raise ValueError("배포용(보호) HWP")
        compressed = bool(flags & 0x1)
        sections = sorted(
            (e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText" and e[1].startswith("Section")),
            key=lambda e: int(e[1][7:] or 0),
        )
        if not sections:
            raise ValueError("BodyText 섹션 없음")
        paras = []
        for e in sections:
            data = ole.openstream("/".join(e)).read()
            if compressed:
                data = zlib.decompress(data, -15)
            for tag, payload in _records(data):
                if tag == HWPTAG_PARA_TEXT:
                    paras.append(_para_text(payload))
    text = "\n".join(p.strip("\r") for p in paras)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
