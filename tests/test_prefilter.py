from datetime import datetime, timedelta

from rfp_finder.config import Config
from rfp_finder.models import Notice
from rfp_finder.prefilter import keyword_hits, passes, select_candidates

NOW = datetime(2026, 11, 20, 9, 0)


def cfg(**kw):
    base = dict(
        team_name="t", capabilities="c", notion_database_id="d",
        include_keywords=["AI", "인공지능", "ISP", "데이터"],
        exclude_keywords=["유지보수", "유지관리", "구매"],
        budget_min_krw=50_000_000, budget_max_krw=3_000_000_000,
    )
    base.update(kw)
    return Config(**base)


def notice(title, kind="bid", budget=300_000_000, days=10, key=None, category="일반용역"):
    return Notice(
        kind=kind, key=key or title, bid_no="N", bid_ord="000", title=title, agency="기관",
        budget_krw=budget, deadline=NOW + timedelta(days=days) if days is not None else None,
        posted_at=NOW, category=category, detail_url="", attachments=[],
    )


def test_keyword_hits_case_insensitive_title_and_category():
    assert keyword_hits(notice("생성형 ai 도입 ISP"), ["AI", "ISP", "LLM"]) == 2
    assert keyword_hits(notice("행정 혁신", category="데이터 용역"), ["데이터"]) == 1


def test_requires_include_keyword():
    assert not passes(notice("청사 시설 유지관리 용역"), cfg(), NOW)


def test_exclude_only_drops():
    assert not passes(notice("전산장비 유지보수"), cfg(), NOW)


def test_exclude_with_include_passes():
    assert passes(notice("AI 플랫폼 구축 및 유지보수"), cfg(), NOW)


def test_budget_range():
    assert not passes(notice("AI 컨설팅", budget=10_000_000), cfg(), NOW)
    assert not passes(notice("AI 컨설팅", budget=5_000_000_000), cfg(), NOW)
    assert passes(notice("AI 컨설팅", budget=50_000_000), cfg(), NOW)


def test_budget_none_passes():
    assert passes(notice("AI 컨설팅", budget=None), cfg(), NOW)


def test_bid_deadline_min_days():
    assert not passes(notice("AI 컨설팅", days=4), cfg(), NOW)
    assert passes(notice("AI 컨설팅", days=5), cfg(), NOW)


def test_bid_without_deadline_passes():
    assert passes(notice("AI 컨설팅", days=None), cfg(), NOW)


def test_prespec_ignores_min_days_but_drops_expired():
    assert passes(notice("AI 컨설팅", kind="prespec", days=2), cfg(), NOW)
    assert not passes(notice("AI 컨설팅", kind="prespec", days=-1), cfg(), NOW)


def test_prespec_excluded_when_disabled():
    assert not passes(notice("AI 컨설팅", kind="prespec", days=3), cfg(include_pre_spec=False), NOW)


def test_dedupe_and_cap_order():
    notices = [notice(f"AI 사업 {i}", key=f"k{i}", days=30 - i) for i in range(17)]
    notices.append(notice("AI 인공지능 데이터 ISP", key="best", days=40))
    notices.append(notice("AI 이미 있음", key="dup", days=10))
    selected, overflow = select_candidates(notices, {"dup"}, cfg(), NOW)
    assert len(selected) == 15 and len(overflow) == 3
    assert selected[0].key == "best"            # 매칭 수 최다
    assert selected[1].key == "k16"             # 그다음은 마감 빠른 순 (days=14)
    assert "dup" not in {n.key for n in selected + overflow}


def test_exclude_matched_sorted_after_clean():
    clean = notice("AI 전략 수립", key="clean", days=30)
    mixed = notice("AI 인공지능 플랫폼 유지보수", key="mixed", days=6)
    selected, _ = select_candidates([mixed, clean], set(), cfg(), NOW)
    assert [n.key for n in selected] == ["clean", "mixed"]


def test_priority_keywords_go_first():
    c = cfg(priority_keywords=["ISP", "전략", "컨설팅"])
    many = notice("AI 인공지능 데이터 플랫폼", key="many", days=6)
    consult = notice("AI 전환 ISP 수립", key="consult", days=40)
    selected, _ = select_candidates([many, consult], set(), c, NOW)
    assert [n.key for n in selected] == ["consult", "many"]


def test_more_priority_hits_rank_higher_than_more_include_hits():
    c = cfg(include_keywords=["AI", "AX", "ISP", "데이터"], priority_keywords=["구축", "개발", "플랫폼", "ISP"])
    isp = notice("AI 전환(AX) ISP 데이터 수립", key="isp", days=6)          # 우선 1개, 포함 4개
    build = notice("AI 에이전트 플랫폼 구축", key="build", days=40)         # 우선 2개, 포함 1개
    selected, _ = select_candidates([isp, build], set(), c, NOW)
    assert [n.key for n in selected] == ["build", "isp"]


def test_priority_keywords_default_empty():
    assert cfg().priority_keywords == []


def _bid(no, ord_, title="AI 챗봇 구축"):
    n = notice(title, key=f"{no}-{ord_}")
    n.bid_no, n.bid_ord = no, ord_
    return n


def test_only_latest_bid_order_selected():
    old, new = _bid("R26BK1", "000"), _bid("R26BK1", "001")
    other = _bid("R26BK2", "000")
    selected, overflow = select_candidates([old, new, other], set(), cfg(), NOW)
    keys = {n.key for n in selected + overflow}
    assert keys == {"R26BK1-001", "R26BK2-000"}


def test_older_order_skipped_when_newer_already_in_notion():
    old = _bid("R26BK1", "000")
    selected, overflow = select_candidates([old], {"R26BK1-001"}, cfg(), NOW)
    assert selected == [] and overflow == []
