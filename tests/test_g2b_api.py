import json
from datetime import date, datetime
from pathlib import Path

import pytest

from g2b_scout import g2b_api
from g2b_scout.g2b_api import G2BApiError, parse_bid, parse_budget, parse_items, parse_prespec

FIX = Path(__file__).parent / "fixtures" / "api"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _bid_fixture():
    real = FIX / "bid_service.json"
    return _load("bid_service.json") if real.exists() else _load("bid_service.synthetic.json")


def test_parse_bid_from_fixture():
    item = next(i for i in parse_items(_bid_fixture()) if i.get("ntceSpecDocUrl1"))
    n = parse_bid(item)
    assert n.kind == "bid"
    assert n.key == f"{n.bid_no}-{n.bid_ord}"
    assert n.title and n.agency
    assert isinstance(n.deadline, datetime) and n.deadline.tzinfo is None
    assert len(n.attachments) >= 1 and all(a.url for a in n.attachments)


def test_parse_prespec_from_fixture():
    item = parse_items(_load("prespec_service.json"))[0]
    n = parse_prespec(item)
    assert n.kind == "prespec"
    assert n.key == "PS-R26BD00301277"
    assert n.title.startswith("서울대학교 지능형 캠퍼스")
    assert n.category == "기술용역"
    assert n.budget_krw == 1119000000
    assert n.deadline == datetime(2026, 11, 20, 10, 0)
    assert len(n.attachments) == 2


def test_parse_items_handles_empty_and_single():
    assert parse_items({"response": {"header": {"resultCode": "00"}, "body": {"items": "", "totalCount": 0}}}) == []
    single = {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": {"a": 1}}, "totalCount": 1}}}
    assert parse_items(single) == [{"a": 1}]
    as_dict = {"response": {"header": {"resultCode": "00"}, "body": {"items": {"a": 1}, "totalCount": 1}}}
    assert parse_items(as_dict) == [{"a": 1}]


def test_parse_budget_variants():
    assert parse_budget("") is None
    assert parse_budget(None) is None
    assert parse_budget("0") is None
    assert parse_budget("1,000,000") == 1000000
    assert parse_budget("250000000") == 250000000
    assert parse_budget(381818182.0) == 381818182


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status
        self.text = json.dumps(payload)

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, total, per_page_items):
        self.total, self.calls = total, []
        self.per = per_page_items

    def get(self, url, params=None, timeout=None):
        self.calls.append(params["pageNo"])
        n = params["numOfRows"]
        start = (params["pageNo"] - 1) * n
        count = max(0, min(n, self.total - start))
        items = [dict(self.per, bfSpecRgstNo=f"R{start + i}") for i in range(count)]
        return FakeResp({"response": {"header": {"resultCode": "00"}, "body": {"items": items, "totalCount": self.total}}})


def test_fetch_paginates(monkeypatch):
    base = parse_items(_load("prespec_service.json"))[0]
    s = FakeSession(25, base)
    monkeypatch.setattr(g2b_api, "PAGE_SIZE", 10)
    out = g2b_api.fetch_prespecs("KEY", date(2026, 11, 17), date(2026, 11, 20), session=s)
    assert len(out) == 25 and s.calls == [1, 2, 3]
    assert len({n.key for n in out}) == 25


def test_api_error_hides_key():
    class ErrSession:
        def get(self, url, params=None, timeout=None):
            return FakeResp({"OpenAPI_ServiceResponse": {"cmmMsgHeader": {
                "errMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR", "returnAuthMsg": "등록되지 않은 서비스키",
                "returnReasonCode": "30"}}}, status=403)
    with pytest.raises(G2BApiError) as e:
        g2b_api.fetch_bid_notices("SECRET-KEY-123", date(2026, 11, 17), date(2026, 11, 20), session=ErrSession())
    assert "SECRET-KEY-123" not in str(e.value)
    assert "30" in str(e.value)


def test_header_error_code_raises():
    class S:
        def get(self, url, params=None, timeout=None):
            return FakeResp({"response": {"header": {"resultCode": "07", "resultMsg": "입력범위값 초과 에러"}}})
    with pytest.raises(G2BApiError, match="07"):
        g2b_api.fetch_prespecs("K", date(2026, 11, 17), date(2026, 11, 20), session=S())


def test_fetch_bid_notices_drops_cancelled():
    base = parse_items(_bid_fixture())[0]

    class S:
        def get(self, url, params=None, timeout=None):
            items = [dict(base, bidNtceNo="A", ntceKindNm="등록공고"), dict(base, bidNtceNo="B", ntceKindNm="취소공고"),
                     dict(base, bidNtceNo="C", ntceKindNm="재공고")]
            return FakeResp({"response": {"header": {"resultCode": "00"}, "body": {"items": items, "totalCount": 3}}})
    out = g2b_api.fetch_bid_notices("K", date(2026, 11, 17), date(2026, 11, 20), session=S())
    assert [n.bid_no for n in out] == ["A", "C"]


def test_fetch_bid_attachments():
    calls = []

    class S:
        def get(self, url, params=None, timeout=None):
            calls.append((url, params))
            return FakeResp(_load("bid_atch_file.json"))
    atts = g2b_api.fetch_bid_attachments("K", "R26BK01837750", "000", session=S())
    assert [a.name for a in atts] == ["관리용역 사업(공고문).hwpx", "관리용역 제안요청서.hwpx"]
    assert calls[0][0].endswith("/getBidPblancListInfoAtchFileInfo02")
    assert calls[0][1]["bidNtceNo"] == "R26BK01837750" and calls[0][1]["inqryDiv"] == 2
