"""공고 첨부 다운로드 → RFP 선택·변환 → 발췌 저장."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

import requests

from .convert import convert, pick_rfp
from .excerpt import make_excerpt
from .models import DocResult, Notice

TIMEOUT = 60
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str, max_len: int = 120) -> str:
    name = _BAD.sub("_", unquote(name)).strip().rstrip(".") or "file"
    if len(name) <= max_len:
        return name
    stem, dot, ext = name.rpartition(".")
    if not dot or len(ext) > 10:
        return name[:max_len]
    return stem[: max_len - len(ext) - 1] + "." + ext


def filename_from_disposition(cd: str | None) -> str | None:
    if not cd:
        return None
    m = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", cd, re.I)
    if not m:
        m = re.search(r'filename\s*=\s*"?([^";]+)"?', cd, re.I)
    return unquote(m.group(1)).strip() if m else None


def _download(url: str, session) -> requests.Response | None:
    for _ in range(2):
        try:
            r = session.get(url, timeout=TIMEOUT)
        except requests.RequestException:
            continue
        if r.status_code == 200:
            return r
    return None


def fetch_documents(notice: Notice, out_dir: Path, session=requests) -> DocResult:
    if not notice.attachments:
        return DocResult(ok=False, error="첨부 없음")
    folder = Path(out_dir) / safe_filename(notice.key)
    folder.mkdir(parents=True, exist_ok=True)

    saved: dict[str, tuple[Path, str]] = {}  # 표시 이름 → (경로, URL)
    errors = []
    for att in notice.attachments:
        r = _download(att.url, session)
        if r is None:
            errors.append(f"{att.name}: 다운로드 실패")
            continue
        if "text/html" in (r.headers.get("Content-Type") or "").lower():
            errors.append(f"{att.name}: HTML 응답(로그인 페이지 등)")
            continue
        name = filename_from_disposition(r.headers.get("Content-Disposition")) or att.name
        base, n = name, 2
        while name in saved:
            name = f"{n}_{base}"
            n += 1
        path = folder / safe_filename(name)
        path.write_bytes(r.content)
        saved[name] = (path, att.url)

    for name in pick_rfp(list(saved)):
        path, url = saved[name]
        result = convert(path)
        if result.ok:
            excerpt = folder / "excerpt.txt"
            excerpt.write_text(make_excerpt(result.text), encoding="utf-8")
            return DocResult(ok=True, rfp_path=path, rfp_name=name, rfp_url=url, excerpt_path=excerpt)
        errors.append(f"{name}: 변환 실패({result.error})")

    # 변환은 모두 실패했지만 받은 파일이 있으면 노션 첨부용으로 1순위 파일 정보는 남긴다
    first = pick_rfp(list(saved))[0] if saved else None
    return DocResult(
        ok=False,
        rfp_path=saved[first][0] if first else None,
        rfp_name=first,
        rfp_url=saved[first][1] if first else (notice.attachments[0].url if notice.attachments else None),
        error="; ".join(errors)[:500] or "변환 가능한 문서 없음",
    )
