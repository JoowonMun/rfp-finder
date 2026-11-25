"""키워드·예산·마감 기반 1차 필터와 후보 선정 (스펙 6.8). 순수 함수, Claude 미개입."""
from __future__ import annotations

from datetime import datetime, timedelta

from .config import Config
from .models import Notice


def _haystack(n: Notice) -> str:
    return f"{n.title} {n.category}".lower()


def keyword_hits(notice: Notice, keywords: list[str]) -> int:
    text = _haystack(notice)
    return sum(1 for k in keywords if k and k.lower() in text)


def passes(notice: Notice, cfg: Config, now: datetime) -> bool:
    if notice.kind == "prespec" and not cfg.include_pre_spec:
        return False
    if keyword_hits(notice, cfg.include_keywords) == 0:
        return False  # 제외 키워드만 있는 경우도 여기서 탈락
    b = notice.budget_krw
    if b is not None:
        if cfg.budget_min_krw is not None and b < cfg.budget_min_krw:
            return False
        if cfg.budget_max_krw is not None and b > cfg.budget_max_krw:
            return False
    if notice.deadline is not None:
        if notice.kind == "bid":
            if notice.deadline < now + timedelta(days=cfg.min_days_to_deadline):
                return False
        elif notice.deadline < now:
            return False
    return True


def _priority(n: Notice, cfg: Config):
    has_exclude = keyword_hits(n, cfg.exclude_keywords) > 0
    deadline = n.deadline or datetime.max
    # 우선 키워드를 '몇 개' 맞췄는지가 먼저. 포함 키워드 개수는 그다음
    # (포함 개수를 먼저 보면 "AI 전환(AX) ISP"처럼 키워드가 몰린 제목이 늘 앞섬)
    priority_hits = keyword_hits(n, cfg.priority_keywords)
    return (-priority_hits, has_exclude, -keyword_hits(n, cfg.include_keywords), n.deadline is None, deadline)


def select_candidates(
    notices: list[Notice], existing_keys: set[str], cfg: Config, now: datetime
) -> tuple[list[Notice], list[Notice]]:
    # 같은 입찰번호의 여러 차수(원공고·정정공고)는 가장 최신 차수만 남긴다.
    # 이미 노션에 더 높은 차수가 있으면 옛 차수는 건너뛴다.
    latest: dict[str, str] = {}
    for k in existing_keys:
        no, _, ord_ = k.rpartition("-")
        if no and ord_.isdigit():
            latest[no] = max(latest.get(no, ""), ord_)
    for n in notices:
        if n.kind == "bid":
            latest[n.bid_no] = max(latest.get(n.bid_no, ""), n.bid_ord)

    seen: set[str] = set()
    fresh = []
    for n in notices:
        if n.key in existing_keys or n.key in seen:
            continue
        if n.kind == "bid" and n.bid_ord < latest.get(n.bid_no, ""):
            continue
        seen.add(n.key)
        if passes(n, cfg, now):
            fresh.append(n)
    fresh.sort(key=lambda n: _priority(n, cfg))
    return fresh[: cfg.max_per_run], fresh[cfg.max_per_run :]
