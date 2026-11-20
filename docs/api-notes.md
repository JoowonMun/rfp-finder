# 조달청 OpenAPI 확인 기록 (Task 1 스파이크, 2026-11-20)

## 엔드포인트

| 서비스 | 확정 엔드포인트 | 상태 |
|---|---|---|
| 사전규격 | `https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc` | ✅ 200, resultCode 00 |
| 입찰공고(용역) | `https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc` | ⏳ 경로는 존재(403 "등록되지 않은 서비스키") — 활용신청/승인 대기 |
| 구 경로 `BidPublicInfoService05/*` | — | ❌ "서비스가 없거나 폐기됨"(12) |

## 공통 요청 파라미터

`serviceKey`(Decoding 키), `pageNo`, `numOfRows`, `type=json`, `inqryDiv=1`(등록일 기준), `inqryBgnDt`/`inqryEndDt` = `YYYYMMDDHHMM`.

## 오류 응답 형식

성공: `{"response": {"header": {"resultCode": "00", ...}, "body": {"items": [...], "totalCount": N}}}`
인증 오류 등: HTTP 4xx + `{"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"errMsg", "returnAuthMsg", "returnReasonCode"}}}` — 파서는 두 형식 모두 처리해야 함.

## 사전규격 필드

| 의미 | 키 | 예 |
|---|---|---|
| 등록번호 | `bfSpecRgstNo` | R26BD00301277 |
| 품명(=공고명) | `prdctClsfcNoNm` | |
| 업무구분 | `bsnsDivNm` | 기술용역 / 일반용역 |
| 발주기관 | `orderInsttNm` (수요기관 `rlDminsttNm`) | |
| 예산 | `asignBdgtAmt` | "1119000000" |
| 접수일시 | `rcptDt` | `2026-11-17 08:02:13` |
| 의견 마감 | `opninRgstClseDt` | `2026-11-20 10:00:00` |
| 규격서 URL | `specDocFileUrl1`~`specDocFileUrl5` (빈 문자열 = 없음) | |
| 첨부 파일명 | **응답에 없음** → 다운로드 응답 `Content-Disposition: attachment;filename=<퍼센트 인코딩>;` 에서 얻음 | |
| 상세 URL | **응답에 없음** → 원문 링크는 첫 규격서 URL 또는 나라장터 검색으로 대체 | |
| 연결된 본공고 | `bidNtceNoList` | |

## 입찰공고 필드

(입찰공고 서비스 승인 후 기록)

## 게이트: 첨부 다운로드

- 사전규격 `specDocFileUrl*` → `requests.get` 그대로 200, `application/octet-stream`, 실제 파일 바이트. 로그인 불필요. ✅
- **확장자를 믿으면 안 됨:** `.hwpx` 이름인데 OLE 시그니처(`D0 CF 11 E0`, 즉 HWP5)인 파일 확인 → 변환기는 시그니처로 분기해야 함.
- 시그니처: HWPX/ZIP `PK\x03\x04`, HWP5 `D0 CF 11 E0 A1 B1 1A E1`, PDF `%PDF`.
