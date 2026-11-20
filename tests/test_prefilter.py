from datetime import datetime, timedelta

from g2b_scout.config import Config
from g2b_scout.models import Notice
from g2b_scout.prefilter import keyword_hits, passes, select_candidates

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
