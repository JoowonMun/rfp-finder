import json
from datetime import date, datetime
from pathlib import Path

import pytest

from g2b_scout.models import Attachment, DocResult, Notice
from g2b_scout.notion_db import (
    DB_PROPERTIES,
    NotionClient,
    build_blocks,
    build_properties,
    parse_notion_id,
)

TODAY = date(2026, 11, 20)


def notice(kind="bid", ord_="000", detail="https://g2b/detail"):
    return Notice(
        kind=kind, key="R26BK1-" + ord_ if kind == "bid" else "PS-R1", bid_no="R26BK1", bid_ord=ord_,
        title="2027 생성형 AI 행정혁신 ISP", agency="○○시청", budget_krw=420000000,
        deadline=datetime(2027, 1, 15, 10, 0), posted_at=None, category="일반용역", detail_url=detail,
        attachments=[Attachment("제안요청서.hwp", "https://g2b/file1")],
    )


def analysis(fit=3, summary="생성형 AI 도입 전략 수립"):
    return {
        "bid_no": "R26BK1", "fit": fit, "fit_reason": "핵심 과업이 AX 컨설팅과 일치", "summary": summary,
        "detail": {
            "overview": "기간 6개월, 예산 4.2억", "requirements": ["현황 진단", "AI 도입 로드맵"],
            "why_fit": ["ISP 경험"], "gaps": ["구축 일부 포함"], "eligibility_risks": ["실적 요건 확인 필요"],
            "evaluation": "기술 90 : 가격 10", "rfp_read": True,
        },
    }


OK_DOC = DocResult(ok=True, rfp_path=Path("x.hwp"), rfp_name="제안요청서.hwp", rfp_url="https://g2b/file1")
FAIL_DOC = DocResult(ok=False, rfp_name="제안요청서.hwp", rfp_url="https://g2b/file1", error="no text")


def sel(props, name):
    return props[name]["select"]["name"]


def text(props, name):
    return "".join(t["text"]["content"] for t in props[name]["rich_text"])


def test_build_properties_fit3():
    p = build_properties(notice(), analysis(3), OK_DOC, "upl-1", "joowon", TODAY)
    assert p["공고명"]["title"][0]["text"]["content"] == "2027 생성형 AI 행정혁신 ISP"
    assert sel(p, "적합도") == "★★★"
    assert sel(p, "상태") == "검토전"
    assert sel(p, "구분") == "본공고"
    assert sel(p, "RFP 분석") == "완료"
    assert text(p, "공고번호") == "R26BK1-000"
    assert p["예산"]["number"] == 420000000
    assert p["마감일"]["date"]["start"].startswith("2027-01-15T10:00")
    assert p["원문 링크"]["url"] == "https://g2b/detail"
    assert p["제안요청서"]["files"][0] == {"type": "file_upload", "file_upload": {"id": "upl-1"}, "name": "제안요청서.hwp"}
    assert text(p, "수집자") == "joowon"
    assert p["수집일"]["date"]["start"] == "2026-11-20"
    assert set(p) == set(DB_PROPERTIES)


def test_build_properties_fit1_auto_excluded():
    p = build_properties(notice(), analysis(1), OK_DOC, None, "j", TODAY)
    assert sel(p, "적합도") == "★" and sel(p, "상태") == "자동제외"


def test_build_properties_file_fallback_link():
    p = build_properties(notice(), analysis(2), OK_DOC, None, "j", TODAY)
    f = p["제안요청서"]["files"][0]
    assert f["type"] == "external" and f["external"]["url"] == "https://g2b/file1" and f["name"] == "제안요청서.hwp"


def test_build_properties_rfp_failed():
    p = build_properties(notice(), analysis(2), FAIL_DOC, None, "j", TODAY)
    assert sel(p, "RFP 분석") == "실패"


def test_prespec_label_and_link_fallback():
    p = build_properties(notice(kind="prespec", detail=""), analysis(2), OK_DOC, None, "j", TODAY)
    assert sel(p, "구분") == "사전규격"
    assert p["원문 링크"]["url"] == "https://g2b/file1"


def test_budget_none():
    n = notice()
    n.budget_krw = None
    assert build_properties(n, analysis(), OK_DOC, None, "j", TODAY)["예산"]["number"] is None


def test_long_summary_truncated():
    p = build_properties(notice(), analysis(summary="가" * 3000), OK_DOC, None, "j", TODAY)
    assert len(text(p, "한줄 요약")) <= 2000


def test_revised_notice_marked():
    p = build_properties(notice(ord_="001"), analysis(), OK_DOC, None, "j", TODAY)
    assert text(p, "한줄 요약").startswith("[정정공고] ")
    p0 = build_properties(notice(ord_="000"), analysis(), OK_DOC, None, "j", TODAY)
    assert not text(p0, "한줄 요약").startswith("[정정공고]")


def _headings(blocks):
    return [b["heading_2"]["rich_text"][0]["text"]["content"] for b in blocks if b["type"] == "heading_2"]


def test_build_blocks_failed_warning():
    blocks = build_blocks(analysis(), FAIL_DOC)
    assert blocks[0]["type"] == "callout"
    assert blocks[0]["callout"]["rich_text"][0]["text"]["content"] == "⚠ 제안요청서 변환 실패 — 원문 직접 확인 필요"


def test_build_blocks_sections():
    blocks = build_blocks(analysis(), OK_DOC)
    assert blocks[0]["type"] != "callout"
    assert _headings(blocks) == ["적합도 판단", "사업 개요", "주요 요구사항", "우리 팀과 맞는 이유", "안 맞는 부분", "참가 자격·리스크", "평가 방식"]
    bullets = [b for b in blocks if b["type"] == "bulleted_list_item"]
    assert any(b["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "AI 도입 로드맵" for b in bullets)


def test_parse_notion_id():
    assert parse_notion_id("https://www.notion.so/team/AX-1f2e3d4c5b6a79881f2e3d4c5b6a7988?pvs=4") == "1f2e3d4c-5b6a-7988-1f2e-3d4c5b6a7988"
    assert parse_notion_id("1f2e3d4c5b6a79881f2e3d4c5b6a7988") == "1f2e3d4c-5b6a-7988-1f2e-3d4c5b6a7988"
    with pytest.raises(ValueError):
        parse_notion_id("not an id")


class Resp:
    def __init__(self, payload, status=200, headers=None):
        self._p, self.status_code, self.headers = payload, status, headers or {}
        self.text = json.dumps(payload)

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return self.responses.pop(0)


def _row(key):
    return {"properties": {"공고번호": {"rich_text": [{"plain_text": key}]}}}


def test_existing_keys_paginates():
    s = FakeSession([
        Resp({"results": [_row(f"k{i}") for i in range(100)], "has_more": True, "next_cursor": "c2"}),
        Resp({"results": [_row(f"k{i}") for i in range(100, 103)], "has_more": False, "next_cursor": None}),
    ])
    keys = NotionClient("tok", session=s).existing_keys("db1")
    assert len(keys) == 103
    assert s.calls[1][2]["json"]["start_cursor"] == "c2"


def test_upload_skips_oversize(tmp_path):
    f = tmp_path / "big.pdf"
    f.write_bytes(b"0" * (6 * 1024 * 1024))
    s = FakeSession([])
    assert NotionClient("tok", session=s).upload_file(f, max_mb=5) is None
    assert s.calls == []


def test_upload_returns_id(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-1.4 small")
    s = FakeSession([Resp({"id": "upl-9", "status": "pending"}), Resp({"id": "upl-9", "status": "uploaded"})])
    assert NotionClient("tok", session=s).upload_file(f, max_mb=5) == "upl-9"
    assert s.calls[1][1].endswith("/file_uploads/upl-9/send")
    assert "files" in s.calls[1][2]


def test_upload_failure_returns_none(tmp_path):
    f = tmp_path / "a.hwp"
    f.write_bytes(b"x")
    s = FakeSession([Resp({"object": "error", "message": "unsupported"}, status=400)])
    assert NotionClient("tok", session=s).upload_file(f, max_mb=5) is None


def test_retry_on_429(monkeypatch):
    import g2b_scout.notion_db as nd
    monkeypatch.setattr(nd.time, "sleep", lambda s: None)
    s = FakeSession([
        Resp({}, status=429, headers={"Retry-After": "1"}),
        Resp({"results": [], "has_more": False}),
    ])
    assert NotionClient("tok", session=s).existing_keys("db1") == set()
    assert len(s.calls) == 2
