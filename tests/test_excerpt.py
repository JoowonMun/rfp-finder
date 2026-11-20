from g2b_scout.excerpt import make_excerpt


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
