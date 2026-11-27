"""조달청 공공데이터포털 OpenAPI 클라이언트. 필드 이름은 docs/api-notes.md 참고."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import requests

from .models import Attachment, Notice

BID_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService02/getBidPblancListInfoServc02"
BID_ATCH_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService02/getBidPblancListInfoAtchFileInfo02"
PRESPEC_URL = "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc"
PAGE_SIZE = 999  # API 허용 최대치. 30일치(수만 건)도 수십 번 요청으로 끝남
TIMEOUT = 30


class G2BApiError(Exception):
    pass


def parse_items(payload: dict) -> list[dict]:
    body = (payload.get("response") or {}).get("body") or {}
    items = body.get("items")
    if not items:
        return []
    if isinstance(items, dict):
        items = items.get("item", items)
    if isinstance(items, dict):
        return [items]
    return list(items)


def parse_budget(value) -> int | None:
    if value is None:
        return None
    s = str(value).replace(",", "").strip()
    if not s:
        return None
    try:
        n = int(float(s))
    except ValueError:
        return None
    return n or None


def _dt(value) -> datetime | None:
    s = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_bid(item: dict) -> Notice:
    no = str(item.get("bidNtceNo", "")).strip()
    ord_ = str(item.get("bidNtceOrd", "")).strip() or "000"
    atts = []
    for i in range(1, 11):
        url = (item.get(f"ntceSpecDocUrl{i}") or "").strip()
        if url:
            name = (item.get(f"ntceSpecFileNm{i}") or "").strip() or f"첨부{i}"
            atts.append(Attachment(name=name, url=url))
    return Notice(
        kind="bid",
        key=f"{no}-{ord_}",
        bid_no=no,
        bid_ord=ord_,
        title=(item.get("bidNtceNm") or "").strip(),
        agency=(item.get("ntceInsttNm") or item.get("dminsttNm") or "").strip(),
        budget_krw=parse_budget(item.get("asignBdgtAmt")) or parse_budget(item.get("presmptPrce")),
        deadline=_dt(item.get("bidClseDt")),
        posted_at=_dt(item.get("bidNtceDt")),
        category=(item.get("srvceDivNm") or item.get("ntceKindNm") or "").strip(),
        detail_url=(item.get("bidNtceDtlUrl") or item.get("bidNtceUrl") or "").strip(),
        attachments=atts,
    )


PRESPEC_URL = "https://www.g2b.go.kr/link/PRVA004_02/single/?bfSpecRegNo={no}"


def prespec_url(reg_no: str) -> str:
    """사전규격 상세 화면 주소. API 응답에는 없어서 등록번호로 만든다(본공고 링크와 같은 /single/ 형식)."""
    return PRESPEC_URL.format(no=reg_no) if reg_no else ""


def parse_prespec(item: dict) -> Notice:
    no = str(item.get("bfSpecRgstNo", "")).strip()
    atts = []
    for i in range(1, 6):
        url = (item.get(f"specDocFileUrl{i}") or "").strip()
        if url:
            # 파일명은 응답에 없음 → 다운로드 시 Content-Disposition으로 갱신
            atts.append(Attachment(name=f"규격서{i}", url=url))
    return Notice(
        kind="prespec",
        key=f"PS-{no}",
        bid_no=no,
        bid_ord="",
        title=(item.get("prdctClsfcNoNm") or "").strip(),
        agency=(item.get("orderInsttNm") or item.get("rlDminsttNm") or "").strip(),
        budget_krw=parse_budget(item.get("asignBdgtAmt")),
        deadline=_dt(item.get("opninRgstClseDt")),
        posted_at=_dt(item.get("rcptDt") or item.get("rgstDt")),
        category=(item.get("bsnsDivNm") or "").strip(),
        detail_url=prespec_url(no),
        attachments=atts,
    )


def _check(resp, payload: dict) -> None:
    if "OpenAPI_ServiceResponse" in payload:
        h = payload["OpenAPI_ServiceResponse"].get("cmmMsgHeader", {})
        raise G2BApiError(
            f"조달청 API 오류 {h.get('returnReasonCode')}: {h.get('returnAuthMsg')} ({h.get('errMsg')}), HTTP {resp.status_code}"
        )
    header = (payload.get("response") or {}).get("header") or {}
    code = header.get("resultCode")
    if code != "00":
        raise G2BApiError(f"조달청 API 오류 {code}: {header.get('resultMsg')}, HTTP {resp.status_code}")


WINDOW_DAYS = 7  # 긴 조회 기간은 API가 거부할 수 있어 7일 단위로 나눠 요청


def _fetch_all(url: str, parser, service_key: str, start: date, end: date, session, keep=lambda item: True) -> list[Notice]:
    out: list[Notice] = []
    seen: set[str] = set()
    cur = start
    while cur <= end:
        win_end = min(cur + timedelta(days=WINDOW_DAYS - 1), end)
        for n in _fetch_window(url, parser, service_key, cur, win_end, session, keep):
            if n.key not in seen:
                seen.add(n.key)
                out.append(n)
        cur = win_end + timedelta(days=1)
    return out


def _fetch_window(url: str, parser, service_key: str, start: date, end: date, session, keep) -> list[Notice]:
    out: list[Notice] = []
    page = 1
    while True:
        params = {
            "serviceKey": service_key,
            "pageNo": page,
            "numOfRows": PAGE_SIZE,
            "type": "json",
            "inqryDiv": 1,
            "inqryBgnDt": start.strftime("%Y%m%d") + "0000",
            "inqryEndDt": end.strftime("%Y%m%d") + "2359",
        }
        try:
            resp = session.get(url, params=params, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise G2BApiError(f"조달청 API 요청 실패: {type(e).__name__}") from None
        try:
            payload = resp.json()
        except ValueError:
            raise G2BApiError(f"조달청 API 응답이 JSON이 아님 (HTTP {resp.status_code})") from None
        _check(resp, payload)
        items = parse_items(payload)
        out.extend(parser(i) for i in items if keep(i))
        total = int(((payload.get("response") or {}).get("body") or {}).get("totalCount") or 0)
        if not items or page * PAGE_SIZE >= total:
            return out
        page += 1


def fetch_bid_notices(service_key: str, start: date, end: date, session=requests) -> list[Notice]:
    """용역 입찰공고. 취소공고는 제외."""
    return _fetch_all(BID_URL, parse_bid, service_key, start, end, session,
                      keep=lambda i: (i.get("ntceKindNm") or "").strip() != "취소공고")


def fetch_bid_attachments(service_key: str, bid_no: str, bid_ord: str, session=requests) -> list[Attachment]:
    """목록 응답에 첨부 URL이 없는 공고용: 첨부파일정보 전용 오퍼레이션."""
    params = {"serviceKey": service_key, "pageNo": 1, "numOfRows": 50, "type": "json",
              "inqryDiv": 2, "bidNtceNo": bid_no, "bidNtceOrd": bid_ord}
    try:
        resp = session.get(BID_ATCH_URL, params=params, timeout=TIMEOUT)
        payload = resp.json()
    except (requests.RequestException, ValueError):
        raise G2BApiError("첨부파일정보 조회 실패") from None
    _check(resp, payload)
    return [
        Attachment(name=(i.get("atchFileNm") or "").strip() or f"첨부{n}", url=i["atchFileUrl"].strip())
        for n, i in enumerate(parse_items(payload), 1)
        if (i.get("atchFileUrl") or "").strip()
    ]


def fetch_prespecs(service_key: str, start: date, end: date, session=requests) -> list[Notice]:
    return _fetch_all(PRESPEC_URL, parse_prespec, service_key, start, end, session)
