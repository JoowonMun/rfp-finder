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
STATUS_OPTIONS = ["검토전", "검토중", "참여", "보류", "자동제외"]


def _select(options: list[str]) -> dict:
    return {"select": {"options": [{"name": o} for o in options]}}


DB_PROPERTIES: dict[str, dict] = {
    "공고명": {"title": {}},
    "구분": _select(["본공고", "사전규격"]),
    "발주기관": {"rich_text": {}},
    "예산": {"number": {"format": "won"}},
    "마감일": {"date": {}},
    "적합도": _select(["★★★", "★★", "★"]),
    "한줄 요약": {"rich_text": {}},
    "제안요청서": {"files": {}},
    "원문 링크": {"url": {}},
    "상태": _select(STATUS_OPTIONS),
    "RFP 분석": _select(["완료", "실패"]),
    "공고번호": {"rich_text": {}},
    "수집일": {"date": {}},
    "수집자": {"rich_text": {}},
}


class NotionError(Exception):
    pass


def parse_notion_id(value: str) -> str:
    m = re.search(r"([0-9a-fA-F]{32})(?![0-9a-fA-F])", value.replace("-", ""))
    if not m:
        raise ValueError(f"노션 페이지/DB ID를 찾을 수 없습니다: {value}")
    h = m.group(1).lower()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def _rt(s: str) -> list[dict]:
    s = (s or "")[:TEXT_LIMIT]
    return [{"type": "text", "text": {"content": s}}] if s else []


def _kst(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "+09:00"


def build_properties(
    notice: Notice, analysis: dict, doc: DocResult, file_upload_id: str | None, collector: str, today: date
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
        "상태": {"select": {"name": "자동제외" if fit == 1 else "검토전"}},
        "RFP 분석": {"select": {"name": "완료" if doc.ok else "실패"}},
        "공고번호": {"rich_text": _rt(notice.key)},
        "수집일": {"date": {"start": today.isoformat()}},
        "수집자": {"rich_text": _rt(collector)},
    }


def _block(kind: str, content: str) -> dict:
    return {"object": "block", "type": kind, kind: {"rich_text": _rt(content)}}


def build_blocks(analysis: dict, doc: DocResult) -> list[dict]:
    d = analysis.get("detail", {})
    blocks: list[dict] = []
    if not doc.ok:
        blocks.append({
            "object": "block", "type": "callout",
            "callout": {"rich_text": _rt("⚠ 제안요청서 변환 실패 — 원문 직접 확인 필요"), "icon": {"type": "emoji", "emoji": "⚠️"}},
        })

    def section(title: str, body) -> None:
        blocks.append(_block("heading_2", title))
        items = body if isinstance(body, list) else None
        if items is None:
            blocks.append(_block("paragraph", str(body or "-")))
        elif not items:
            blocks.append(_block("paragraph", "-"))
        else:
            blocks.extend(_block("bulleted_list_item", str(i)) for i in items)

    section("적합도 판단", f"{FIT_LABEL[int(analysis['fit'])]} {analysis.get('fit_reason', '')}")
    section("사업 개요", d.get("overview"))
    section("주요 요구사항", d.get("requirements", []))
    section("우리 팀과 맞는 이유", d.get("why_fit", []))
    section("안 맞는 부분", d.get("gaps", []))
    section("참가 자격·리스크", d.get("eligibility_risks", []))
    section("평가 방식", d.get("evaluation"))
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
            resp = self.session.request(
                method, f"{API}{path}", headers=self._headers(files is None), json=json, files=files, timeout=60
            )
            if resp.status_code == 429 and attempt < 3:
                time.sleep(float(resp.headers.get("Retry-After") or 1))
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
        file_upload_id: str | None, collector: str, today: date | None = None,
    ) -> dict:
        body = {
            "parent": {"database_id": database_id},
            "properties": build_properties(notice, analysis, doc, file_upload_id, collector, today or date.today()),
            "children": build_blocks(analysis, doc),
        }
        return self._request("POST", "/pages", json=body)
