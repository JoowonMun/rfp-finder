"""노션 DB 연동: DB 생성, 중복 조회, 파일 업로드, 행 생성. 속성/블록 빌더는 순수 함수."""
from __future__ import annotations

import mimetypes
import re
import time
from datetime import date, datetime
from pathlib import Path

import requests

from .models import DocResult, Notice

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
TEXT_LIMIT = 2000
FILE_NAME_LIMIT = 100
FIRST_ORD = {"", "0", "00", "000"}

FIT_LABEL = {3: "★★★", 2: "★★", 1: "★"}


def _select(options: dict[str, str]) -> dict:
    """{옵션 이름: 색} → 노션 select 정의. 색이 있어야 표에서 한눈에 구분된다."""
    return {"select": {"options": [{"name": n, "color": c} for n, c in options.items()]}}


DB_PROPERTIES: dict[str, dict] = {
    "공고명": {"title": {}},
    "구분": _select({"본공고": "blue", "사전규격": "purple"}),
    "발주기관": {"rich_text": {}},
    "예산": {"number": {"format": "won"}},
    "마감일": {"date": {}},
    "적합도": _select({"★★★": "green", "★★": "yellow", "★": "gray"}),
    "한줄 요약": {"rich_text": {}},
    "제안요청서": {"files": {}},
    "원문 링크": {"url": {}},
    "RFP 분석": _select({"완료": "green", "실패": "red"}),
    "공고번호": {"rich_text": {}},
    "수집일": {"date": {}},
}


class NotionError(Exception):
    pass


def parse_notion_id(value: str) -> str:
    m = re.search(r"([0-9a-fA-F]{32})(?![0-9a-fA-F])", value.replace("-", ""))
    if not m:
        raise ValueError(f"노션 페이지/DB ID를 찾을 수 없습니다: {value}")
    h = m.group(1).lower()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def _chunks16(s: str, limit: int = TEXT_LIMIT) -> list[str]:
    """노션은 글자 수를 UTF-16 단위로 센다 → 그 기준으로 limit 이하 조각으로 자른다."""
    out, cur, n = [], [], 0
    for ch in s:
        w = 2 if ord(ch) > 0xFFFF else 1
        if n + w > limit:
            out.append("".join(cur))
            cur, n = [], 0
        cur.append(ch)
        n += w
    if cur:
        out.append("".join(cur))
    return out


def _rt(s: str) -> list[dict]:
    s = (_chunks16((s or "").replace("**", "")) or [""])[0]
    return [{"type": "text", "text": {"content": s}}] if s else []


def _kst(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "+09:00"


def build_properties(
    notice: Notice, analysis: dict, doc: DocResult, file_upload_id: str | None, today: date
) -> dict:
    fit = int(analysis["fit"])
    summary = analysis.get("summary", "")
    if notice.kind == "bid" and notice.bid_ord not in FIRST_ORD:
        summary = "[정정공고] " + summary

    link = notice.detail_url or doc.rfp_url or (notice.attachments[0].url if notice.attachments else None)
    file_name = (doc.rfp_name or "제안요청서")[:FILE_NAME_LIMIT]
    if file_upload_id:
        files = [{"type": "file_upload", "file_upload": {"id": file_upload_id}, "name": file_name}]
    elif doc.rfp_url:
        files = [{"type": "external", "name": file_name, "external": {"url": doc.rfp_url}}]
    else:
        files = []

    return {
        "공고명": {"title": _rt(notice.title)},
        "구분": {"select": {"name": "본공고" if notice.kind == "bid" else "사전규격"}},
        "발주기관": {"rich_text": _rt(notice.agency)},
        "예산": {"number": notice.budget_krw},
        "마감일": {"date": {"start": _kst(notice.deadline)} if notice.deadline else None},
        "적합도": {"select": {"name": FIT_LABEL[fit]}},
        "한줄 요약": {"rich_text": _rt(summary)},
        "제안요청서": {"files": files},
        "원문 링크": {"url": link},
        "RFP 분석": {"select": {"name": "완료" if doc.ok else "실패"}},
        "공고번호": {"rich_text": _rt(notice.key)},
        "수집일": {"date": {"start": today.isoformat()}},
    }


FIT_CARD = {3: ("바로 검토", "green_background"), 2: ("검토 권장", "yellow_background"), 1: ("참고", "gray_background")}
WEEKDAY = "월화수목금토일"


_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)


def _rich(s: str) -> list[dict]:
    """'**키워드**' 표시를 굵은 글씨로 바꾼 rich_text. 표시 없는 글은 그대로."""
    out, pos = [], 0
    for m in _BOLD.finditer(s or ""):
        out += [(s[pos:m.start()], False), (m.group(1), True)]
        pos = m.end()
    out.append(((s or "")[pos:], False))
    rich = []
    for text, bold in out:
        for chunk in _chunks16(text.replace("**", "")):
            r = {"type": "text", "text": {"content": chunk}}
            if bold:
                r["annotations"] = {"bold": True}
            rich.append(r)
    return rich[:100]


def _block(kind: str, content: str, *, bold: bool = False, **extra) -> dict:
    rich = _rich(content)
    if bold:
        for r in rich:
            r["annotations"] = {"bold": True}
    return {"object": "block", "type": kind, kind: {"rich_text": rich, **extra}}


def _callout(content: str, emoji: str, color: str) -> dict:
    return _block("callout", content, icon={"type": "emoji", "emoji": emoji}, color=color)


def _card(label: str, value: str, sub: list[str], emoji: str, color: str) -> dict:
    """카드: 항목명·값은 굵게, 보조 줄은 보통 글씨."""
    rich = [
        {"type": "text", "text": {"content": label + "\n"}, "annotations": {"bold": True}},
        {"type": "text", "text": {"content": value}, "annotations": {"bold": True}},
    ]
    if sub:
        rich.append({"type": "text", "text": {"content": "\n" + "\n".join(sub)}})
    return {"object": "block", "type": "callout",
            "callout": {"rich_text": rich, "icon": {"type": "emoji", "emoji": emoji}, "color": color}}


def _columns(children_per_column: list[list[dict]]) -> dict:
    return {
        "object": "block", "type": "column_list",
        "column_list": {"children": [
            {"object": "block", "type": "column", "column": {"children": kids}} for kids in children_per_column
        ]},
    }


def _won(v: int | None) -> str:
    if not v:
        return "미기재"
    if v >= 100_000_000:
        return f"{v / 100_000_000:.1f}".rstrip("0").rstrip(".") + "억"
    return f"{v // 10_000:,}만원"


def _deadline_card(notice: Notice, today: date) -> dict:
    label = "의견마감" if notice.kind == "prespec" else "마감"
    if not notice.deadline:
        return _card(label, "미기재", [], "⏰", "orange_background")
    days = (notice.deadline.date() - today).days
    dday = "D-day" if days == 0 else (f"D-{days}" if days > 0 else f"D+{-days}")
    d = notice.deadline
    return _card(label, dday, [f"({today:%m.%d} 기준)", f"{d:%m.%d}({WEEKDAY[d.weekday()]}) {d:%H:%M}"],
                 "⏰", "orange_background")


OVERVIEW_FIELDS = [("client", "발주"), ("content", "내용"), ("period", "기간"), ("budget", "예산"), ("contract", "계약")]


def _overview_box(overview) -> dict:
    """사업 개요 흰 콜아웃. 객체면 '항목명(굵게)  값' 한 줄씩, 문자열이면 그대로.
    (표는 노션 API로 너비를 못 정해 좁게 나오므로 쓰지 않음)"""
    if not isinstance(overview, dict):
        return _callout(str(overview or "-"), "📄", "default")
    rich = []
    for key, label in OVERVIEW_FIELDS:
        value = str(overview.get(key) or "").strip().replace("**", "")
        if not value:
            continue
        if rich:
            rich.append({"type": "text", "text": {"content": "\n"}})
        rich.append({"type": "text", "text": {"content": label}, "annotations": {"bold": True}})
        rich.append({"type": "text", "text": {"content": "  " + (_chunks16(value) or [""])[0]}})
    if not rich:
        return _callout("-", "📄", "default")
    return {"object": "block", "type": "callout",
            "callout": {"rich_text": rich, "icon": {"type": "emoji", "emoji": "📄"}, "color": "default"}}


def _eval_lines(text: str | None) -> list[str]:
    """'기술 90 : 가격 10, 협상에 의한 계약' → ['기술 90', '가격 10', '협상에 의한 계약']"""
    parts = re.split(r"\s*[:：,/·\n]\s*", (text or "").strip())
    return [x for x in parts if x] or ["미기재"]


def _list_box(title: str, items, emoji: str, color: str) -> dict:
    """색 콜아웃 안에 제목(heading_3) + 노션 불릿 목록.
    단(column) 안의 콜아웃 자식은 3단계 중첩이라 페이지 생성 때 못 넣는다 → split_deep 이 떼어내
    create_entry 가 페이지를 만든 뒤 콜아웃에 덧붙인다."""
    items = [str(i) for i in (items or [])] or ["-"]
    # 이모지는 콜아웃 아이콘에만 (제목에 또 넣으면 중복으로 보임)
    kids = [_block("heading_3", title), *(_block("bulleted_list_item", i) for i in items)]
    return {"object": "block", "type": "callout",
            "callout": {"rich_text": [], "icon": {"type": "emoji", "emoji": emoji}, "color": color, "children": kids}}


MAX_DEPTH = 2  # 노션 API: 한 요청 안에서 블록 중첩은 2단계까지


def split_deep(blocks: list[dict], depth: int = 0, path: tuple = ()) -> tuple[list[dict], list[tuple[tuple, list[dict]]]]:
    """중첩 한도를 넘는 자식을 떼어낸 사본과 [(블록 위치 경로, 자식 목록)]을 돌려준다."""
    out, deferred = [], []
    for i, b in enumerate(blocks):
        b = {**b, b["type"]: dict(b[b["type"]])}
        payload = b[b["type"]]
        kids = payload.get("children")
        if kids:
            if depth >= MAX_DEPTH:
                deferred.append((path + (i,), payload.pop("children")))
            else:
                payload["children"], sub = split_deep(kids, depth + 1, path + (i,))
                deferred += sub
        out.append(b)
    return out, deferred


def build_blocks(analysis: dict, doc: DocResult, notice: Notice, today: date) -> list[dict]:
    d = analysis.get("detail", {})
    fit = int(analysis["fit"])
    label, color = FIT_CARD[fit]
    blocks: list[dict] = []
    if not doc.ok:
        blocks.append(_callout("⚠ 제안요청서 변환 실패 — 원문 직접 확인 필요", "⚠️", "red_background"))

    duration = d.get("duration") or ""
    blocks.append(_columns([
        [_card("적합도", FIT_LABEL[fit], [label], "🎯", color)],
        [_card("예산", _won(notice.budget_krw), [duration] if duration else [], "💰", "blue_background")],
        [_deadline_card(notice, today)],
        [_card("평가", "\n".join(_eval_lines(d.get("evaluation"))), [], "📊", "purple_background")],
    ]))
    blocks.append(_callout(analysis.get("fit_reason", ""), "💬", "gray_background"))

    blocks.append(_block("heading_3", "📌 사업 개요"))
    blocks.append(_overview_box(d.get("overview")))

    blocks.append(_block("heading_3", "📋 주요 요구사항"))
    reqs = d.get("requirements", []) or []
    for r in reqs:
        title, details = (r.get("title", ""), r.get("details") or []) if isinstance(r, dict) else (str(r), [])
        item = _block("numbered_list_item", str(title), bold=True)
        if details:
            item["numbered_list_item"]["children"] = [_block("bulleted_list_item", str(x)) for x in details]
        blocks.append(item)
    if not reqs:
        blocks.append(_block("paragraph", "-"))

    blocks.append(_columns([
        [_list_box("우리 팀과 맞는 점", d.get("why_fit"), "✅", "green_background")],
        [_list_box("안 맞는 점·리스크", d.get("gaps"), "⚠️", "red_background")],
    ]))

    blocks.append(_block("heading_3", "☑ 참가 자격 체크리스트"))
    checklist = d.get("eligibility_checklist") or [{"item": r, "ok": False} for r in d.get("eligibility_risks", [])]
    if checklist:
        blocks.extend(_block("to_do", str(c.get("item", "")), checked=bool(c.get("ok"))) for c in checklist)
    else:
        blocks.append(_block("paragraph", "제안요청서에 명시된 자격 요건 없음"))

    blocks.append(_block("heading_3", "📊 평가 방식"))
    blocks.extend(_block("bulleted_list_item", x) for x in _eval_lines(d.get("evaluation")))
    return blocks[:100]


class NotionClient:
    def __init__(self, token: str, session=requests):
        self.token, self.session = token, session

    def _headers(self, json_body: bool = True) -> dict:
        h = {"Authorization": f"Bearer {self.token}", "Notion-Version": NOTION_VERSION}
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    def _request(self, method: str, path: str, *, json=None, files=None) -> dict:
        for attempt in range(4):
            try:
                resp = self.session.request(
                    method, f"{API}{path}", headers=self._headers(files is None), json=json, files=files, timeout=60
                )
            except requests.RequestException as e:
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise NotionError(f"노션 연결 실패: {type(e).__name__}") from None
            if (resp.status_code == 429 or resp.status_code >= 500) and attempt < 3:
                time.sleep(float(resp.headers.get("Retry-After") or 2 ** attempt))
                continue
            if resp.status_code >= 400:
                try:
                    msg = resp.json().get("message", "")
                except ValueError:
                    msg = resp.text[:200]
                raise NotionError(f"노션 API 오류 HTTP {resp.status_code}: {msg}")
            return resp.json()
        raise NotionError("노션 API 요청 한도 초과(429)")

    def create_database(self, parent_page_id: str, title: str = "나라장터 추천 공고") -> str:
        body = {
            "parent": {"type": "page_id", "page_id": parse_notion_id(parent_page_id)},
            "title": _rt(title),
            "is_inline": True,  # 부모 페이지 안에 표로 바로 보이게
            "properties": DB_PROPERTIES,
        }
        return self._request("POST", "/databases", json=body)["id"]

    def existing_keys(self, database_id: str) -> set[str]:
        keys: set[str] = set()
        body: dict = {"page_size": 100}
        while True:
            data = self._request("POST", f"/databases/{database_id}/query", json=body)
            for row in data.get("results", []):
                rt = ((row.get("properties") or {}).get("공고번호") or {}).get("rich_text") or []
                k = "".join(t.get("plain_text", "") for t in rt).strip()
                if k:
                    keys.add(k)
            if not data.get("has_more"):
                return keys
            body = {"page_size": 100, "start_cursor": data["next_cursor"]}

    def has_key(self, database_id: str, key: str) -> bool:
        body = {"page_size": 1, "filter": {"property": "공고번호", "rich_text": {"equals": key}}}
        return bool(self._request("POST", f"/databases/{database_id}/query", json=body).get("results"))

    def archive_key(self, database_id: str, key: str) -> int:
        """같은 공고번호 페이지를 휴지통으로 (페이지 다시 만들기·재분류용)."""
        body = {"page_size": 100, "filter": {"property": "공고번호", "rich_text": {"equals": key}}}
        rows = self._request("POST", f"/databases/{database_id}/query", json=body).get("results", [])
        for row in rows:
            self._request("PATCH", f"/pages/{row['id']}", json={"archived": True})
        return len(rows)

    def archive_older_versions(self, database_id: str, bid_no: str, keep_key: str) -> int:
        """같은 입찰번호의 다른 차수(예: 정정 전 -000) 페이지를 휴지통으로."""
        body = {"page_size": 100, "filter": {"property": "공고번호", "rich_text": {"starts_with": f"{bid_no}-"}}}
        rows = self._request("POST", f"/databases/{database_id}/query", json=body).get("results", [])
        n = 0
        for row in rows:
            key = "".join(t.get("plain_text", "") for t in row["properties"]["공고번호"]["rich_text"])
            if key != keep_key:
                self._request("PATCH", f"/pages/{row['id']}", json={"archived": True})
                n += 1
        return n

    def get_database(self, database_id: str) -> dict:
        return self._request("GET", f"/databases/{database_id}")

    def upload_file(self, path: Path, max_mb: int) -> str | None:
        path = Path(path)
        try:
            if path.stat().st_size > max_mb * 1024 * 1024:
                return None
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            up = self._request("POST", "/file_uploads", json={"filename": path.name, "content_type": ctype})
            with open(path, "rb") as f:
                self._request("POST", f"/file_uploads/{up['id']}/send", files={"file": (path.name, f.read(), ctype)})
            return up["id"]
        except (NotionError, OSError, KeyError, requests.RequestException):
            return None

    def create_entry(
        self, database_id: str, notice: Notice, analysis: dict, doc: DocResult,
        file_upload_id: str | None, today: date | None = None,
    ) -> dict:
        shallow, deferred = split_deep(build_blocks(analysis, doc, notice, today or date.today()))
        body = {
            "parent": {"database_id": database_id},
            "properties": build_properties(notice, analysis, doc, file_upload_id, today or date.today()),
            "children": shallow,
        }
        page = self._request("POST", "/pages", json=body)
        listed: dict[str, list[dict]] = {}
        for path, kids in deferred:
            block_id = page["id"]
            for idx in path:
                if block_id not in listed:
                    listed[block_id] = self._request("GET", f"/blocks/{block_id}/children?page_size=100").get("results", [])
                block_id = listed[block_id][idx]["id"]
            self._request("PATCH", f"/blocks/{block_id}/children", json={"children": kids})
        return page
