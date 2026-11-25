import json
from datetime import date, datetime
from pathlib import Path

import pytest

from rfp_finder.models import Attachment, DocResult, Notice
from rfp_finder.notion_db import (
    DB_PROPERTIES,
    NotionClient,
    build_blocks,
    split_deep,
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
    p = build_properties(notice(), analysis(3), OK_DOC, "upl-1", TODAY)
    assert p["공고명"]["title"][0]["text"]["content"] == "2027 생성형 AI 행정혁신 ISP"
    assert sel(p, "적합도") == "★★★"
    assert "상태" not in p and "수집자" not in p
    assert sel(p, "구분") == "본공고"
    assert sel(p, "RFP 분석") == "완료"
    assert text(p, "공고번호") == "R26BK1-000"
    assert p["예산"]["number"] == 420000000
    assert p["마감일"]["date"]["start"].startswith("2027-01-15T10:00")
    assert p["원문 링크"]["url"] == "https://g2b/detail"
    assert p["제안요청서"]["files"][0] == {"type": "file_upload", "file_upload": {"id": "upl-1"}, "name": "제안요청서.hwp"}
    assert p["수집일"]["date"]["start"] == "2026-11-20"
    assert set(p) == set(DB_PROPERTIES)


def test_build_properties_file_fallback_link():
    p = build_properties(notice(), analysis(2), OK_DOC, None, TODAY)
    f = p["제안요청서"]["files"][0]
    assert f["type"] == "external" and f["external"]["url"] == "https://g2b/file1" and f["name"] == "제안요청서.hwp"


def test_build_properties_rfp_failed():
    p = build_properties(notice(), analysis(2), FAIL_DOC, None, TODAY)
    assert sel(p, "RFP 분석") == "실패"


def test_prespec_label_and_link_fallback():
    p = build_properties(notice(kind="prespec", detail=""), analysis(2), OK_DOC, None, TODAY)
    assert sel(p, "구분") == "사전규격"
    assert p["원문 링크"]["url"] == "https://g2b/file1"


def test_budget_none():
    n = notice()
    n.budget_krw = None
    assert build_properties(n, analysis(), OK_DOC, None, TODAY)["예산"]["number"] is None


def test_long_summary_truncated():
    p = build_properties(notice(), analysis(summary="가" * 3000), OK_DOC, None, TODAY)
    assert len(text(p, "한줄 요약")) <= 2000


def test_revised_notice_marked():
    p = build_properties(notice(ord_="001"), analysis(), OK_DOC, None, TODAY)
    assert text(p, "한줄 요약").startswith("[정정공고] ")
    p0 = build_properties(notice(ord_="000"), analysis(), OK_DOC, None, TODAY)
    assert not text(p0, "한줄 요약").startswith("[정정공고]")


def _types(blocks):
    return [b["type"] for b in blocks]


def _plain(rich):
    return "".join(t["text"]["content"] for t in rich)


def _cards(blocks):
    cl = next(b for b in blocks if b["type"] == "column_list")
    return [_plain(col["column"]["children"][0]["callout"]["rich_text"]) for col in cl["column_list"]["children"]], cl


def dash(fit=3, doc=OK_DOC, n=None, **detail):
    a = analysis(fit)
    a["detail"].update(detail)
    return build_blocks(a, doc, n or notice(), TODAY)


def test_build_blocks_failed_warning():
    blocks = dash(doc=FAIL_DOC)
    assert blocks[0]["type"] == "callout"
    assert _plain(blocks[0]["callout"]["rich_text"]) == "⚠ 제안요청서 변환 실패 — 원문 직접 확인 필요"


def test_dashboard_cards():
    blocks = dash(fit=3, duration="6개월")
    assert blocks[0]["type"] == "column_list"
    texts, cl = _cards(blocks)
    assert len(texts) == 4
    assert "★★★" in texts[0] and "바로 검토" in texts[0]
    assert "4.2억" in texts[1] and "6개월" in texts[1]
    assert "D-56" in texts[2] and "01.15(금) 10:00" in texts[2]
    assert "기술 90\n가격 10" in texts[3]
    fit_card = cl["column_list"]["children"][0]["column"]["children"][0]["callout"]
    assert fit_card["color"] == "green_background"


def test_card_colors_and_labels_by_fit():
    for fit, color, label in [(2, "yellow_background", "검토 권장"), (1, "gray_background", "참고")]:
        texts, cl = _cards(dash(fit=fit))
        assert label in texts[0]
        assert cl["column_list"]["children"][0]["column"]["children"][0]["callout"]["color"] == color


def test_cards_missing_values():
    n = notice()
    n.budget_krw, n.deadline = None, None
    texts, _ = _cards(dash(n=n))
    assert "미기재" in texts[1] and "미기재" in texts[2]


def test_prespec_deadline_label():
    texts, _ = _cards(dash(n=notice(kind="prespec")))
    assert "의견마감" in texts[2]


def _h3(blocks):
    return [_plain(b["heading_3"]["rich_text"]) for b in blocks if b["type"] == "heading_3"]


def test_dashboard_layout_order():
    blocks = dash()
    t = _types(blocks)
    assert t[:2] == ["column_list", "callout"]
    assert "table" not in t
    assert _h3(blocks) == ["📌 사업 개요", "📋 주요 요구사항", "☑ 참가 자격 체크리스트", "📊 평가 방식"]
    assert "toggle" not in t  # 원문 발췌 토글은 넣지 않음
    # 맞는 점/안 맞는 점 2단은 요구사항 다음, 자격 체크리스트 앞
    i_cols = [i for i, b in enumerate(blocks) if b["type"] == "column_list"][1]
    i_req = next(i for i, b in enumerate(blocks) if b["type"] == "numbered_list_item")
    i_chk = next(i for i, b in enumerate(blocks) if b["type"] == "to_do")
    assert i_req < i_cols < i_chk


def test_cards_are_bold():
    _, cl = _cards(dash())
    rich = cl["column_list"]["children"][0]["column"]["children"][0]["callout"]["rich_text"]
    bold = [r["text"]["content"] for r in rich if r.get("annotations", {}).get("bold")]
    assert any("적합도" in b for b in bold) and any("★★★" in b for b in bold)


def test_two_columns_fit_and_gaps():
    blocks = dash()
    cl = [b for b in blocks if b["type"] == "column_list"][1]
    left, right = [c["column"]["children"] for c in cl["column_list"]["children"]]
    assert len(left) == 1 and len(right) == 1
    lbox, rbox = left[0]["callout"], right[0]["callout"]
    assert lbox["color"] == "green_background" and rbox["color"] == "red_background"
    assert lbox["rich_text"] == []
    lk, rk = lbox["children"], rbox["children"]
    assert lk[0]["type"] == "heading_3" and _plain(lk[0]["heading_3"]["rich_text"]) == "우리 팀과 맞는 점"
    assert lk[1]["type"] == "bulleted_list_item" and _plain(lk[1]["bulleted_list_item"]["rich_text"]) == "ISP 경험"
    assert _plain(rk[0]["heading_3"]["rich_text"]) == "안 맞는 점·리스크"
    assert _plain(rk[1]["bulleted_list_item"]["rich_text"]) == "구축 일부 포함"


def test_split_deep_defers_third_level():
    blocks = dash()
    shallow, deferred = split_deep(blocks)
    i_cols = [i for i, b in enumerate(blocks) if b["type"] == "column_list"][1]
    assert [p for p, _ in deferred] == [(i_cols, 0, 0), (i_cols, 1, 0)]
    assert deferred[0][1][0]["type"] == "heading_3"
    box = shallow[i_cols]["column_list"]["children"][0]["column"]["children"][0]["callout"]
    assert "children" not in box
    # 원본은 그대로
    assert "children" in blocks[i_cols]["column_list"]["children"][0]["column"]["children"][0]["callout"]
    # 2단계 이내 자식(번호 목록의 불릿)은 그대로 둠
    shallow2, _ = split_deep(dash(requirements=[{"title": "A", "details": ["a1"]}]))
    assert any("children" in b.get("numbered_list_item", {}) for b in shallow2)


def test_create_entry_appends_deferred_children():
    blocks = dash()
    i_cols = [i for i, b in enumerate(blocks) if b["type"] == "column_list"][1]
    top = [{"id": f"t{i}"} for i in range(len(blocks))]
    s = FakeSession([
        Resp({"id": "page1"}),
        Resp({"results": top}),
        Resp({"results": [{"id": "colL"}, {"id": "colR"}]}),
        Resp({"results": [{"id": "boxL"}]}),
        Resp({}),
        Resp({"results": [{"id": "boxR"}]}),
        Resp({}),
    ])
    NotionClient("tok", session=s).create_entry("db1", notice(), analysis(3), OK_DOC, None, TODAY)
    urls = [(m, u.split("/v1")[-1]) for m, u, _ in s.calls]
    assert urls == [
        ("POST", "/pages"),
        ("GET", "/blocks/page1/children?page_size=100"),
        ("GET", f"/blocks/t{i_cols}/children?page_size=100"),
        ("GET", "/blocks/colL/children?page_size=100"),
        ("PATCH", "/blocks/boxL/children"),
        ("GET", "/blocks/colR/children?page_size=100"),
        ("PATCH", "/blocks/boxR/children"),
    ]
    assert s.calls[4][2]["json"]["children"][0]["type"] == "heading_3"


def test_checklist_from_explicit_items():
    blocks = dash(eligibility_checklist=[{"item": "공동수급 허용", "ok": True}, {"item": "SW사업자", "ok": False}])
    todos = [(_plain(b["to_do"]["rich_text"]), b["to_do"]["checked"]) for b in blocks if b["type"] == "to_do"]
    assert todos == [("공동수급 허용", True), ("SW사업자", False)]


def test_checklist_falls_back_to_risks():
    todos = [(_plain(b["to_do"]["rich_text"]), b["to_do"]["checked"]) for b in dash() if b["type"] == "to_do"]
    assert todos == [("실적 요건 확인 필요", False)]


def test_requirements_numbered_bold():
    items = [b for b in dash() if b["type"] == "numbered_list_item"]
    assert [_plain(b["numbered_list_item"]["rich_text"]) for b in items] == ["현황 진단", "AI 도입 로드맵"]
    assert all(r["annotations"]["bold"] for b in items for r in b["numbered_list_item"]["rich_text"])


def test_overview_and_evaluation_shown_inline():
    blocks = dash()
    text = " ".join(_plain(b[b["type"]]["rich_text"]) for b in blocks if b["type"] in ("callout", "bulleted_list_item"))
    assert "기간 6개월, 예산 4.2억" in text and "기술 90" in text and "가격 10" in text


def test_nesting_depth_at_most_two():
    def depth(block):
        inner = block[block["type"]].get("children", [])
        return 0 if not inner else 1 + max(depth(c) for c in inner)
    shallow, _ = split_deep(dash(requirements=[{"title": "A", "details": ["a1"]}]))
    assert max(depth(b) for b in shallow) <= 2


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
    import rfp_finder.notion_db as nd
    monkeypatch.setattr(nd.time, "sleep", lambda s: None)
    s = FakeSession([
        Resp({}, status=429, headers={"Retry-After": "1"}),
        Resp({"results": [], "has_more": False}),
    ])
    assert NotionClient("tok", session=s).existing_keys("db1") == set()
    assert len(s.calls) == 2


def test_has_key_uses_filter():
    s = FakeSession([Resp({"results": [_row("B1")], "has_more": False}), Resp({"results": [], "has_more": False})])
    c = NotionClient("tok", session=s)
    assert c.has_key("db1", "B1") is True
    assert s.calls[0][2]["json"]["filter"] == {"property": "공고번호", "rich_text": {"equals": "B1"}}
    assert c.has_key("db1", "B2") is False


def test_create_database_is_inline():
    s = FakeSession([Resp({"id": "db-new"})])
    assert NotionClient("tok", session=s).create_database("1f2e3d4c5b6a79881f2e3d4c5b6a7988") == "db-new"
    body = s.calls[0][2]["json"]
    assert body["is_inline"] is True
    assert set(body["properties"]) == set(DB_PROPERTIES)


def _u16(s):
    return len(s.encode("utf-16-le")) // 2


def test_text_limits_count_utf16_units():
    wide = "\U000f02b1"  # HWP 사용자 정의 기호: UTF-16 2칸
    blocks = dash(why_fit=[("가" * 1999 + wide) * 3])
    cl = [b for b in blocks if b["type"] == "column_list"][1]
    item = cl["column_list"]["children"][0]["column"]["children"][0]["callout"]["children"][1]["bulleted_list_item"]
    assert all(_u16(r["text"]["content"]) <= 2000 for r in item["rich_text"])
    p = build_properties(notice(), analysis(summary=wide * 1500), OK_DOC, None, TODAY)
    assert _u16(text(p, "한줄 요약")) <= 2000


def test_network_error_becomes_notion_error():
    import requests as rq
    from rfp_finder.notion_db import NotionError

    class Down:
        def request(self, *a, **kw):
            raise rq.ConnectionError("offline")
    with pytest.raises(NotionError, match="연결"):
        NotionClient("tok", session=Down()).existing_keys("db1")


def test_deadline_card_states_reference_date():
    texts, _ = _cards(dash())
    assert "11.20 기준" in texts[2]


def test_select_options_have_colors():
    colors = {p: {o["name"]: o["color"] for o in DB_PROPERTIES[p]["select"]["options"]}
              for p in ("구분", "적합도", "RFP 분석")}
    assert colors["적합도"] == {"★★★": "green", "★★": "yellow", "★": "gray"}
    assert colors["구분"] == {"본공고": "blue", "사전규격": "purple"}
    assert colors["RFP 분석"] == {"완료": "green", "실패": "red"}


def test_archive_key_archives_matching_pages():
    s = FakeSession([Resp({"results": [{"id": "p1"}, {"id": "p2"}], "has_more": False}), Resp({}), Resp({})])
    assert NotionClient("tok", session=s).archive_key("db1", "B1") == 2
    assert s.calls[1][0] == "PATCH" and s.calls[1][1].endswith("/pages/p1") and s.calls[1][2]["json"] == {"archived": True}


def test_requirements_with_details_render_nested_bullets():
    blocks = dash(requirements=[
        {"title": "AI 도입 로드맵 수립", "details": ["3개년 단계별 로드맵", "우선 과제 10건 선정"]},
        "현황 진단",
    ])
    items = [b for b in blocks if b["type"] == "numbered_list_item"]
    assert [_plain(b["numbered_list_item"]["rich_text"]) for b in items] == ["AI 도입 로드맵 수립", "현황 진단"]
    kids = items[0]["numbered_list_item"]["children"]
    assert [_plain(k["bulleted_list_item"]["rich_text"]) for k in kids] == ["3개년 단계별 로드맵", "우선 과제 10건 선정"]
    assert "children" not in items[1]["numbered_list_item"]


def test_card_label_is_not_gray():
    _, cl = _cards(dash())
    rich = cl["column_list"]["children"][0]["column"]["children"][0]["callout"]["rich_text"]
    assert all(r.get("annotations", {}).get("color", "default") == "default" for r in rich)


def test_evaluation_split_into_lines():
    texts, _ = _cards(dash(evaluation="기술 90 : 가격 10, 협상에 의한 계약"))
    assert "기술 90\n가격 10\n협상에 의한 계약" in texts[3]
    blocks = dash(evaluation="기술 90 : 가격 10, 협상에 의한 계약")
    i = _h3(blocks).index("📊 평가 방식")
    h_idx = [k for k, b in enumerate(blocks) if b["type"] == "heading_3"][i]
    after = [_plain(b["bulleted_list_item"]["rich_text"]) for b in blocks[h_idx + 1:h_idx + 4] if b["type"] == "bulleted_list_item"]
    assert after == ["기술 90", "가격 10", "협상에 의한 계약"]


def test_overview_in_white_callout():
    blocks = dash()
    h_idx = next(k for k, b in enumerate(blocks) if b["type"] == "heading_3" and "사업 개요" in _plain(b["heading_3"]["rich_text"]))
    box = blocks[h_idx + 1]
    assert box["type"] == "callout" and box["callout"]["color"] == "default"
    assert "기간 6개월, 예산 4.2억" in _plain(box["callout"]["rich_text"])


OV = {"client": "농협대학교 산학협력단", "content": "NHU AX교육플랫폼 구축", "period": "계약일부터 2026년 12월 31일까지",
      "budget": "5,500만 원", "contract": "일반경쟁입찰, 협상에 의한 계약"}


def _overview_box(blocks):
    h_idx = next(k for k, b in enumerate(blocks) if b["type"] == "heading_3" and "사업 개요" in _plain(b["heading_3"]["rich_text"]))
    box = blocks[h_idx + 1]
    assert box["type"] == "callout" and box["callout"]["color"] == "default"
    return box["callout"]["rich_text"]


def test_overview_object_renders_labeled_lines():
    rich = _overview_box(dash(overview=OV))
    assert _plain(rich) == "발주  농협대학교 산학협력단\n내용  NHU AX교육플랫폼 구축\n기간  계약일부터 2026년 12월 31일까지\n예산  5,500만 원\n계약  일반경쟁입찰, 협상에 의한 계약"
    labels = [r["text"]["content"].strip() for r in rich if r.get("annotations", {}).get("bold")]
    assert labels == ["발주", "내용", "기간", "예산", "계약"]


def test_overview_object_skips_missing_fields():
    assert _plain(_overview_box(dash(overview={"client": "A기관", "content": "구축"}))) == "발주  A기관\n내용  구축"


def test_overview_object_all_empty_falls_back():
    assert _plain(_overview_box(dash(overview={"client": ""}))) == "-"


def _bold_parts(rich):
    return [r["text"]["content"] for r in rich if r.get("annotations", {}).get("bold")]


def test_fit_reason_keywords_bold():
    a = analysis(3)
    a["fit_reason"] = "**RAG 학습튜터** 직접 개발이라 주력과 일치. 다만 **기간 1개월**"
    blocks = build_blocks(a, OK_DOC, notice(), TODAY)
    rich = blocks[1]["callout"]["rich_text"]
    assert _plain(rich) == "RAG 학습튜터 직접 개발이라 주력과 일치. 다만 기간 1개월"
    assert _bold_parts(rich) == ["RAG 학습튜터", "기간 1개월"]


def test_why_fit_and_gaps_keywords_bold():
    blocks = dash(why_fit=["**LLMOps** 경험이 있는 팀이 유리"], gaps=["**GPU 서버 구매** 비중이 큼"])
    cl = [b for b in blocks if b["type"] == "column_list"][1]
    left, right = [c["column"]["children"] for c in cl["column_list"]["children"]]
    item_l = left[0]["callout"]["children"][1]["bulleted_list_item"]["rich_text"]
    item_r = right[0]["callout"]["children"][1]["bulleted_list_item"]["rich_text"]
    assert _plain(item_l) == "LLMOps 경험이 있는 팀이 유리"
    assert _bold_parts(item_l) == ["LLMOps"] and _bold_parts(item_r) == ["GPU 서버 구매"]


def test_bold_markers_stripped_from_properties():
    p = build_properties(notice(), analysis(summary="**AI 챗봇** 구축"), OK_DOC, None, TODAY)
    assert text(p, "한줄 요약") == "AI 챗봇 구축"


def test_archive_older_versions_keeps_current():
    s = FakeSession([
        Resp({"results": [{"id": "p0", **_row("R1-000")}, {"id": "p1", **_row("R1-001")}]}),
        Resp({}),
    ])
    n = NotionClient("tok", session=s).archive_older_versions("db1", "R1", "R1-001")
    assert n == 1
    assert s.calls[0][2]["json"]["filter"]["rich_text"] == {"starts_with": "R1-"}
    assert s.calls[1][0] == "PATCH" and s.calls[1][1].endswith("/pages/p0")


def test_rfp_status_failed_when_only_announcement_read():
    a = analysis(2)
    a["detail"]["rfp_read"] = False
    p = build_properties(notice(), a, OK_DOC, None, TODAY)
    assert p["RFP 분석"]["select"]["name"] == "실패"
    blocks = build_blocks(a, OK_DOC, notice(), TODAY)
    assert blocks[0]["type"] == "callout" and "공고문만 보고 판단" in _plain(blocks[0]["callout"]["rich_text"])


def test_rfp_status_done_when_read():
    p = build_properties(notice(), analysis(2), OK_DOC, None, TODAY)
    assert p["RFP 분석"]["select"]["name"] == "완료"
