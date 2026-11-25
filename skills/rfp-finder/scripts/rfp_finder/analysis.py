"""Claude가 작성한 분석 JSON 검증 (스펙 6.4)."""
from __future__ import annotations

DETAIL_TEXT = ("overview", "evaluation")
# 노션 '사업유형' 태그로 쓰는 값 (한 공고에 여러 개 가능)
PROJECT_TYPES = ("AI 구축", "AI 개발 컨설팅", "ISP", "ISMP", "전략·마스터플랜", "PMO", "연구용역")
DETAIL_LIST = ("requirements", "why_fit", "gaps", "eligibility_risks")


class AnalysisError(Exception):
    pass


def validate_analysis(data: dict) -> dict:
    if not isinstance(data, dict):
        raise AnalysisError("분석 결과가 JSON 객체가 아님")
    if data.get("fit") not in (0, 1, 2, 3) or isinstance(data.get("fit"), bool):
        raise AnalysisError(f"fit 은 0~3 정수여야 함 (0=제외, 1~3=별 개수, 현재: {data.get('fit')!r})")
    for k in ("summary", "fit_reason"):
        if not isinstance(data.get(k), str) or not data[k].strip():
            raise AnalysisError(f"{k} 가 비어 있음")
    types = data.get("types", [])
    if not isinstance(types, list) or any(t not in PROJECT_TYPES for t in types):
        raise AnalysisError(f"types 는 {list(PROJECT_TYPES)} 중에서 고른 목록이어야 함 (현재: {types!r})")
    detail = data.get("detail")
    if not isinstance(detail, dict):
        raise AnalysisError("detail 객체 없음")
    for k in DETAIL_TEXT + DETAIL_LIST + ("rfp_read",):
        if k not in detail:
            raise AnalysisError(f"detail.{k} 누락")
    for k in DETAIL_LIST:
        if not isinstance(detail[k], list):
            raise AnalysisError(f"detail.{k} 는 목록이어야 함")
    ov = detail["overview"]
    if isinstance(ov, dict):
        allowed = {"client", "content", "period", "budget", "contract"}
        if set(ov) - allowed or not all(isinstance(v, str) for v in ov.values()):
            raise AnalysisError("detail.overview 객체는 client/content/period/budget/contract 문자열만 가질 수 있음")
    elif not isinstance(ov, str):
        raise AnalysisError("detail.overview 는 문자열 또는 객체여야 함")
    for r in detail["requirements"]:
        ok = isinstance(r, str) or (
            isinstance(r, dict) and isinstance(r.get("title"), str)
            and isinstance(r.get("details", []), list) and all(isinstance(x, str) for x in r.get("details", []))
        )
        if not ok:
            raise AnalysisError('detail.requirements 항목은 문자열 또는 {"title": 문자열, "details": [문자열]} 이어야 함')
    if not isinstance(detail["rfp_read"], bool):
        raise AnalysisError("detail.rfp_read 는 true/false 여야 함")
    checklist = detail.get("eligibility_checklist")
    if checklist is not None:
        if not isinstance(checklist, list) or not all(
            isinstance(c, dict) and isinstance(c.get("item"), str) and isinstance(c.get("ok"), bool) for c in checklist
        ):
            raise AnalysisError('detail.eligibility_checklist 는 [{"item": 문자열, "ok": true/false}] 목록이어야 함')
    return data
