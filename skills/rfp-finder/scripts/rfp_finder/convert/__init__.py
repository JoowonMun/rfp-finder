"""첨부 문서 → 텍스트. 파일 시그니처로 형식을 판별하고, 어떤 경우에도 예외를 던지지 않는다."""
from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path

from ..models import ConvertResult
from . import docx, hwp5, hwpx, pdf

MIN_TEXT = 200

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# 앞에서부터 시도. zip 묶음은 안에 제안요청서가 들어 있는 경우가 많아 공고문보다 먼저 연다.
# 공고문·양식은 텍스트가 충분해서 '변환 성공'으로 먼저 잡히면 제안요청서를 못 보게 되므로 맨 뒤.
_RANKS = [r"제안요청서", r"과업지시서|과업내용서", r"규격서|사양서", r"\.zip$"]
_LAST = [r"공고서|공고문|입찰공고", r"양식|서약|신청서|사유서|확약|위임|동의서"]


class _PlainZip(Exception):
    """HWPX가 아닌 일반 zip 묶음."""


def pick_rfp(names: list[str]) -> list[str]:
    def rank(name: str) -> int:
        for i, pat in enumerate(_RANKS):
            if re.search(pat, name, re.I):
                return i
        for i, pat in enumerate(_LAST):
            if re.search(pat, name):
                return len(_RANKS) + 1 + i
        return len(_RANKS)  # 그 밖의 파일: zip 다음, 공고문 앞

    return sorted(names, key=rank)  # 안정 정렬 → 같은 등급은 원래 순서


def _zip_name(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def _extract_single(path: Path) -> str:
    with open(path, "rb") as f:
        head = f.read(8)
    if head.startswith(b"%PDF"):
        return pdf.extract(path)
    if head.startswith(_OLE):
        return hwp5.extract(path)
    if head.startswith(b"PK"):
        with zipfile.ZipFile(path) as zf:
            if hwpx.is_hwpx(zf):
                return hwpx.extract(path)
            if docx.is_docx(zf):
                return docx.extract(path)
        raise _PlainZip()
    raise ValueError(f"지원하지 않는 형식: {path.suffix or '확장자 없음'}")


def _result(text: str, name: str) -> ConvertResult:
    if len(text.strip()) < MIN_TEXT:
        return ConvertResult(ok=False, text=text, source_name=name, error="no text")
    return ConvertResult(ok=True, text=text, source_name=name)


def _convert_zip(path: Path) -> ConvertResult:
    parts: list[str] = []
    first_ok: str | None = None
    with zipfile.ZipFile(path) as zf, tempfile.TemporaryDirectory() as tmp:
        members = {_zip_name(i): i for i in zf.infolist() if not i.is_dir()}
        for idx, name in enumerate(pick_rfp(list(members))):
            target = Path(tmp) / f"m{idx}{Path(name).suffix}"
            target.write_bytes(zf.read(members[name]))
            try:
                text = _extract_single(target)
            except Exception:  # noqa: BLE001 - 묶음 안 개별 실패는 건너뜀 (중첩 zip 포함)
                continue
            if first_ok is None and len(text.strip()) >= MIN_TEXT:
                first_ok = Path(name).name
            parts.append(f"=== {Path(name).name} ===\n{text}")
    return _result("\n\n".join(parts), first_ok or path.name)


def convert(path: Path) -> ConvertResult:
    path = Path(path)
    try:
        if not path.exists():
            return ConvertResult(ok=False, text="", source_name=path.name, error="파일 없음")
        try:
            text = _extract_single(path)
        except _PlainZip:
            return _convert_zip(path)
        return _result(text, path.name)
    except Exception as e:  # noqa: BLE001 - 변환 실패는 결과로 보고
        return ConvertResult(ok=False, text="", source_name=path.name, error=f"{type(e).__name__}: {e}"[:300])
