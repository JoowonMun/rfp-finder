"""RFP 본문을 분석용 텍스트로. 보통은 전문 그대로, 비정상적으로 길 때만 중요한 섹션을 우선 남긴다."""
from __future__ import annotations

import re

MARK = "[... 일부 생략 ...]"
# 상한: 여러 첨부를 합친 zip 등 비정상적으로 긴 문서용 안전장치 (일반 제안요청서는 4~13만 자)
MAX_CHARS = 300_000
# 앞에 있을수록 먼저 담는다. 요구사항 세부 표와 평가 기준은 문서 뒷부분에 있어도 반드시 남긴다.
_PRIORITY = [
    re.compile(r"요구사항"),
    re.compile(r"평가"),
    re.compile(r"과업|사업\s*개요|추진"),
    re.compile(r"자격|제안"),
]
# 섹션 제목처럼 보이는 짧은 줄: 로마숫자 / 제N장 / 1. / 가. 로 시작
_HEADING = re.compile(r"^\s*([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.|제\s*\d+\s*[장절]|\d{1,2}\.|[가-하]\.)\s*\S")


def _sections(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        if _HEADING.match(line) and len(line.strip()) <= 60:
            out.append((line.strip(), [line]))
        else:
            out[-1][1].append(line)
    return [(h, "\n".join(body)) for h, body in out if body]


def make_excerpt(text: str, max_chars: int = MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    budget = max_chars - len(MARK) - 1
    secs = _sections(text)
    picked: dict[int, str] = {}
    used = 0
    for pat in _PRIORITY:
        for idx, (head, body) in enumerate(secs):
            if idx in picked or not head or not pat.search(head) or used >= budget:
                continue
            chunk = body[: budget - used]
            picked[idx] = chunk
            used += len(chunk) + 1
    # 남는 분량은 문서 앞부분(사업명·개요가 보통 여기 있음)으로 채움
    if used < budget and 0 not in picked:
        picked[-1] = text[: budget - used - 1]
    return "\n".join(picked[i] for i in sorted(picked)) + "\n" + MARK
