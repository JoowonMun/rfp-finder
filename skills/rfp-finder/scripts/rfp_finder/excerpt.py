"""긴 RFP에서 분석에 필요한 섹션을 우선 발췌한다."""
from __future__ import annotations

import re

MARK = "[... 일부 생략 ...]"
_KEY = re.compile(r"과업|요구사항|평가|자격|제안|사업\s*개요|추진")
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


def make_excerpt(text: str, max_chars: int = 60000) -> str:
    if len(text) <= max_chars:
        return text
    budget = max_chars - len(MARK) - 1
    secs = _sections(text)
    picked: dict[int, str] = {}
    used = 0
    for idx, (head, body) in enumerate(secs):
        if head and _KEY.search(head) and used < budget:
            chunk = body[: budget - used]
            picked[idx] = chunk
            used += len(chunk) + 1
    # 남는 분량은 문서 앞부분(사업명·개요가 보통 여기 있음)으로 채움
    if used < budget and 0 not in picked:
        picked[-1] = text[: budget - used - 1]
    return "\n".join(picked[i] for i in sorted(picked)) + "\n" + MARK
