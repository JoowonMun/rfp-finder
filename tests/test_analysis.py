import copy

import pytest

from g2b_scout.analysis import AnalysisError, validate_analysis

GOOD = {
    "bid_no": "R26BK1", "fit": 2, "fit_reason": "일부 일치", "summary": "AI 플랫폼 구축",
    "detail": {
        "overview": "개요", "requirements": ["a"], "why_fit": ["b"], "gaps": [], "eligibility_risks": [],
        "evaluation": "기술 80 : 가격 20", "rfp_read": True,
    },
}


def test_validate_ok():
    assert validate_analysis(copy.deepcopy(GOOD))["fit"] == 2


def test_validate_rejects_fit_4():
    bad = copy.deepcopy(GOOD)
    bad["fit"] = 4
    with pytest.raises(AnalysisError, match="fit"):
        validate_analysis(bad)


def test_validate_missing_detail_key():
    bad = copy.deepcopy(GOOD)
    del bad["detail"]["gaps"]
    with pytest.raises(AnalysisError, match="gaps"):
        validate_analysis(bad)


def test_validate_empty_summary():
    bad = copy.deepcopy(GOOD)
    bad["summary"] = "  "
    with pytest.raises(AnalysisError, match="summary"):
        validate_analysis(bad)


def test_validate_rfp_read_must_be_bool():
    bad = copy.deepcopy(GOOD)
    bad["detail"]["rfp_read"] = "yes"
    with pytest.raises(AnalysisError, match="rfp_read"):
        validate_analysis(bad)


def test_validate_list_fields():
    bad = copy.deepcopy(GOOD)
    bad["detail"]["requirements"] = "문자열"
    with pytest.raises(AnalysisError, match="requirements"):
        validate_analysis(bad)


def test_validate_checklist_optional_but_typed():
    ok = copy.deepcopy(GOOD)
    ok["detail"]["eligibility_checklist"] = [{"item": "공동수급 허용", "ok": True}]
    ok["detail"]["duration"] = "6개월"
    validate_analysis(ok)
    bad = copy.deepcopy(GOOD)
    bad["detail"]["eligibility_checklist"] = [{"item": "x", "ok": "yes"}]
    with pytest.raises(AnalysisError, match="eligibility_checklist"):
        validate_analysis(bad)


def test_requirements_may_be_title_details_objects():
    ok = copy.deepcopy(GOOD)
    ok["detail"]["requirements"] = [{"title": "로드맵", "details": ["3개년"]}, "현황 진단"]
    validate_analysis(ok)
    bad = copy.deepcopy(GOOD)
    bad["detail"]["requirements"] = [{"title": "로드맵", "details": "3개년"}]
    with pytest.raises(AnalysisError, match="requirements"):
        validate_analysis(bad)


def test_overview_may_be_object():
    ok = copy.deepcopy(GOOD)
    ok["detail"]["overview"] = {"client": "A", "content": "B", "period": "C", "budget": "D", "contract": "E"}
    validate_analysis(ok)
    bad = copy.deepcopy(GOOD)
    bad["detail"]["overview"] = {"client": 3}
    with pytest.raises(AnalysisError, match="overview"):
        validate_analysis(bad)
