from rfp_finder.excerpt import make_excerpt


def test_excerpt_short_text_unchanged():
    t = "짧은 문서\n내용"
    assert make_excerpt(t, max_chars=1000) == t


def test_excerpt_prioritizes_sections():
    front = "\n".join(["표지 및 목차 " + "가" * 50] * 40)
    noise = "\n".join(["Ⅶ. 보안 서약 관련 부속 서류"] + ["부속서류 " + "나" * 50] * 40)
    key = "\n".join(["Ⅲ. 과업 내용 및 요구사항"] + ["요구사항 상세: AI 모델 구축 " + "다" * 30] * 5)
    text = front + "\n" + noise + "\n" + key
    out = make_excerpt(text, max_chars=1500)
    assert len(out) <= 1500 + 50
    assert "Ⅲ. 과업 내용 및 요구사항" in out
    assert "요구사항 상세: AI 모델 구축" in out
    assert "[... 일부 생략 ...]" in out
    assert "부속서류" not in out


def test_default_keeps_full_long_rfp():
    t = "Ⅰ. 사업 개요\n" + "가" * 150_000 + "\nⅤ. 평가 기준\n기술 90 가격 10"
    assert make_excerpt(t) == t  # 30만 자 이하는 자르지 않음


def test_over_cap_keeps_requirements_and_evaluation_first():
    front = "\n".join(["Ⅱ. 과업 내용"] + ["과업 서술 " + "가" * 50] * 60)
    req = "\n".join(["Ⅲ. 요구사항 세부내용"] + ["SFR-001 요구사항 정의 " + "다" * 30] * 5)
    ev = "\n".join(["Ⅴ. 제안서 평가 기준"] + ["기술평가 90점 " + "라" * 30] * 3)
    out = make_excerpt(front + "\n" + req + "\n" + ev, max_chars=1500)
    assert "SFR-001 요구사항 정의" in out and "기술평가 90점" in out
