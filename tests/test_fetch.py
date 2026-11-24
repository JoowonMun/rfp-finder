import io
import zipfile
from datetime import datetime
from urllib.parse import quote

from rfp_finder.fetch import fetch_documents, filename_from_disposition, safe_filename
from rfp_finder.models import Attachment, Notice

FILLER = "과업 내용 및 요구사항을 상세히 기술한다. " * 20


def hwpx_bytes(text):
    buf = io.BytesIO()
    xml = (
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
        'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        f"<hp:p><hp:run><hp:t>{text} {FILLER}</hp:t></hp:run></hp:p></hs:sec>"
    )
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section0.xml", xml)
    return buf.getvalue()


class Resp:
    def __init__(self, content, ctype="application/octet-stream", cd=None, status=200):
        self.content, self.status_code = content, status
        self.headers = {"Content-Type": ctype}
        if cd:
            self.headers["Content-Disposition"] = cd


class Session:
    def __init__(self, mapping):
        self.mapping, self.calls = mapping, []

    def get(self, url, timeout=None):
        self.calls.append(url)
        r = self.mapping[url]
        if isinstance(r, Exception):
            raise r
        return r


def notice(atts):
    return Notice(kind="prespec", key="PS-R1", bid_no="R1", bid_ord="", title="AI", agency="a",
                  budget_krw=None, deadline=datetime(2026, 12, 1), posted_at=None, category="",
                  detail_url="", attachments=atts)


def test_safe_filename():
    assert safe_filename("%EC%A0%9C%EC%95%88:요청서?.hwp") == "제안_요청서_.hwp"
    long = safe_filename("가" * 300 + ".hwp")
    assert len(long) <= 120 and long.endswith(".hwp")
    assert safe_filename("a\x01b.pdf") == "a_b.pdf"


def test_filename_from_disposition():
    cd = "attachment;filename=" + quote("[붙임2] 제안요청서(안).hwpx") + ";"
    assert filename_from_disposition(cd) == "[붙임2] 제안요청서(안).hwpx"
    assert filename_from_disposition(None) is None
    assert filename_from_disposition("attachment; filename*=UTF-8''" + quote("과업지시서.pdf")) == "과업지시서.pdf"


def test_fetch_html_response_is_failure(tmp_path):
    s = Session({"u1": Resp(b"<html>login</html>", ctype="text/html;charset=UTF-8")})
    r = fetch_documents(notice([Attachment("규격서1", "u1")]), tmp_path, session=s)
    assert not r.ok and "HTML" in r.error


def test_fetch_picks_rfp_and_writes_excerpt(tmp_path):
    s = Session({
        "u1": Resp(hwpx_bytes("보안서약서"), cd="attachment;filename=" + quote("붙임1 보안서약서.hwpx") + ";"),
        "u2": Resp(hwpx_bytes("제안요청서 본문 AI"), cd="attachment;filename=" + quote("제안요청서.hwpx") + ";"),
    })
    r = fetch_documents(notice([Attachment("규격서1", "u1"), Attachment("규격서2", "u2")]), tmp_path, session=s)
    assert r.ok, r.error
    assert r.rfp_name == "제안요청서.hwpx"
    assert r.rfp_url == "u2"
    assert r.rfp_path.exists() and r.rfp_path.parent == tmp_path / "PS-R1"
    assert "제안요청서 본문 AI" in r.excerpt_path.read_text(encoding="utf-8")


def test_fetch_retries_once_then_fails(tmp_path):
    import requests
    s = Session({"u1": requests.ConnectionError("boom")})
    r = fetch_documents(notice([Attachment("규격서1", "u1")]), tmp_path, session=s)
    assert not r.ok and s.calls == ["u1", "u1"]


def test_fetch_no_attachments(tmp_path):
    r = fetch_documents(notice([]), tmp_path, session=Session({}))
    assert not r.ok and r.error == "첨부 없음"


def bid_notice(atts, bid_no="R26BK01843717"):
    return Notice(kind="bid", key=f"{bid_no}-000", bid_no=bid_no, bid_ord="000", title="데이터 파이프라인 구축",
                  agency="a", budget_krw=None, deadline=datetime(2026, 12, 1), posted_at=None, category="",
                  detail_url="", attachments=atts)


def test_document_for_other_bid_is_rejected(tmp_path):
    s = Session({"u1": Resp(hwpx_bytes("입찰공고번호: R26BK01845527-000 AI-OS 시범 서비스"),
                            cd="attachment;filename=" + quote("공고문.hwpx") + ";")})
    r = fetch_documents(bid_notice([Attachment("공고문", "u1")]), tmp_path, session=s)
    assert not r.ok and "다른 공고" in r.error
    assert r.rfp_url == "u1"


def test_document_mentioning_own_bid_is_accepted(tmp_path):
    s = Session({"u1": Resp(hwpx_bytes("입찰공고번호: R26BK01843717-000 참조 R26BK01845527"),
                            cd="attachment;filename=" + quote("제안요청서.hwpx") + ";")})
    assert fetch_documents(bid_notice([Attachment("x", "u1")]), tmp_path, session=s).ok


def test_document_without_bid_numbers_is_accepted(tmp_path):
    s = Session({"u1": Resp(hwpx_bytes("과업 내용"), cd="attachment;filename=" + quote("제안요청서.hwpx") + ";")})
    assert fetch_documents(bid_notice([Attachment("x", "u1")]), tmp_path, session=s).ok
