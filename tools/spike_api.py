"""조달청 OpenAPI 명세 확인용 스파이크 스크립트 (Task 1).

.env의 DATA_GO_KR_SERVICE_KEY로 후보 엔드포인트를 호출해 첫 성공 응답을
tests/fixtures/api/<name>.json 에 저장한다. 서비스키는 출력하지 않는다.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "api"

CANDIDATES = {
    "bid_service": [
        "https://apis.data.go.kr/1230000/ad/BidPublicInfoService02/getBidPblancListInfoServc02",
        "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc",
        "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch",
        "https://apis.data.go.kr/1230000/BidPublicInfoService05/getBidPblancListInfoServc",
        "https://apis.data.go.kr/1230000/BidPublicInfoService05/getBidPblancListInfoServcPPSSrch",
    ],
    "prespec_service": [
        "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc",
        "https://apis.data.go.kr/1230000/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc",
    ],
}


def mask(text: str, key: str) -> str:
    return text.replace(key, "***") if key else text


def main() -> int:
    env = dotenv_values(ROOT / ".env")
    key = os.environ.get("DATA_GO_KR_SERVICE_KEY") or env.get("DATA_GO_KR_SERVICE_KEY", "")
    bid_key = os.environ.get("DATA_GO_KR_BID_SERVICE_KEY") or env.get("DATA_GO_KR_BID_SERVICE_KEY") or key
    if not key or "붙여넣기" in key:
        print("DATA_GO_KR_SERVICE_KEY 가 .env에 없습니다.")
        return 2
    end = datetime.now()
    start = end - timedelta(days=3)
    params = {
        "serviceKey": key,
        "pageNo": 1,
        "numOfRows": 10,
        "type": "json",
        "inqryDiv": 1,
        "inqryBgnDt": start.strftime("%Y%m%d0000"),
        "inqryEndDt": end.strftime("%Y%m%d2359"),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    ok_all = True
    for name, urls in CANDIDATES.items():
        saved = False
        svc_key = bid_key if name == "bid_service" else key
        for url in urls:
            try:
                r = requests.get(url, params={**params, "serviceKey": svc_key}, timeout=30)
            except requests.RequestException as e:
                print(f"[{name}] {url} -> 요청 실패: {type(e).__name__}")
                continue
            body = mask(mask(r.text, key), bid_key)
            print(f"[{name}] {url} -> HTTP {r.status_code}, {body[:200]!r}")
            try:
                data = r.json()
            except ValueError:
                continue
            code = (data.get("response", {}).get("header", {}) or {}).get("resultCode")
            if r.status_code == 200 and code == "00":
                if (OUT / f"{name}.json").exists():
                    print(f"  -> {name}.json 이미 있음 (테스트 고정용, 덮어쓰지 않음)")
                    saved = True
                    break
                (OUT / f"{name}.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                (OUT / f"{name}.endpoint.txt").write_text(url, encoding="utf-8")
                print(f"  -> 저장: {name}.json")
                saved = True
                break
        ok_all &= saved
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
