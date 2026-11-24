---
name: rfp-finder
description: 나라장터(조달청) 용역 입찰공고·사전규격을 수집하고 제안요청서(HWP/HWPX/PDF) 본문을 읽어 팀 역량 대비 적합도를 매긴 뒤 팀 노션 DB에 쌓아주는 스킬. "나라장터 공고 찾아줘", "입찰 공고 추천", "제안할 만한 사업 찾아줘", "RFP 수집", "사전규격 확인", "/rfp-finder" 같은 요청에 사용.
---

# 나라장터 공고 추천 (rfp-finder)

나라장터 공고 중 **우리 팀이 제안서를 써볼 만한 것**을 골라 노션 표에 올린다.
반복 작업은 `scripts/scout.py`가 하고, 너(Claude)는 **제안요청서를 읽고 판단·요약**하는 일만 한다.

`SCOUT` = `python "<이 스킬의 base directory>/scripts/scout.py"`
모든 명령은 stdout **마지막 줄에 JSON**을 출력한다. 그 JSON만 읽으면 된다.

## 무인 실행 여부

프롬프트가 `claude -p` 등 비대화형 실행이면(사용자에게 물을 수 없으면) **질문하지 말고**, 막히는 지점에서 문제를 한 줄로 출력하고 종료한다.

## 1. 점검

```
SCOUT doctor
```

`ok: true`면 2단계로. 아니면 `needs`에 따라:

- `config` → **첫 설정 인터뷰** (대화형일 때만). 한 번에 하나씩 묻는다:
  1. 팀 이름
  2. 팀이 하는 일·잘하는 일 (자유 서술, 적합도 판단의 핵심이라 구체적으로 받기)
  3. 대표 수행 실적 (선택)
  4. 관심 키워드 (예시: AI, 인공지능, 생성형, AX, ISP, 데이터)
  5. 제외 키워드 (예시: 유지보수, 구매, 임차, 공사)
  6. 가장 먼저 보고 싶은 사업 유형 키워드 = 우선 키워드 (예시: ISP, ISMP, 전략, 컨설팅, 로드맵, PMO)
  7. 예산 범위 (하한·상한, 모르면 비워둠)
  8. 사전규격도 볼지 (기본: 예)

  답을 `<이 스킬의 base directory>/config.example.yaml` 형식에 맞춰 `doctor`가 알려준 `home` 폴더의 `config.yaml`로 저장한다. 그다음 다시 `doctor`.
- `secrets` → `references/setup-guide.md`의 키 발급 절차를 안내하고 **중단**한다. 키 값을 대화에 붙여넣으라고 하지 말 것(파일에 직접 넣게 한다).
- `notion_db` → 사용자에게 DB를 만들 팀 노션 페이지 URL을 받아 `SCOUT setup-notion --parent-page "<URL>"`.
- `notion_access` → 노션 통합을 그 페이지에 연결하라고 안내(setup-guide 3단계)하고 중단.

## 2. 수집과 문서 준비

```
SCOUT candidates                 → run_dir, selected, overflow, warnings
SCOUT fetch --run "<run_dir>"    → 공고별 ok / excerpt_path
```

- `selected`가 0이면 "새로 볼 공고 없음"이라고 보고하고 끝낸다.
- `warnings`가 있으면 기억해 두었다가 마지막 보고에 포함한다 (예: 입찰공고 API 키 미승인).

## 3. 공고별 분석 → 즉시 업로드 (한 건씩)

`<run_dir>/candidates.json`의 `selected` 순서대로, **각 공고마다**:

1. 메타데이터(공고명·기관·예산·마감·구분)를 확인한다.
2. `fetch` 결과에서 그 공고가 `ok: true`면 `excerpt_path` 파일을 읽는다. `ok: false`면 메타데이터만으로 판단하고 `rfp_read: false`로 둔다.
3. 팀 정보는 `home`의 `config.yaml` → `team.capabilities`, `team.past_projects`.
4. `references/analysis-guide.md` 기준으로 분석 JSON을 만들어 `<run_dir>/analysis/<공고키>.json`에 저장한다. (`<공고키>`는 candidates의 `key` 그대로, 파일명에 못 쓰는 문자는 `_`로)
5. 바로 업로드: `SCOUT publish --run "<run_dir>" --key "<공고키>"`
   - 오류가 `분석 JSON 오류`면 그 필드를 고쳐 다시 publish.
   - `skipped_duplicate`는 정상(다른 사람이 먼저 올림).
   - `excluded`는 정상: 적합도 1(★)은 노션 표에 올리지 않고 로컬 제외 기록에만 남긴다.

한 건 끝나면 다음 건. 여러 건을 모아서 한꺼번에 올리지 않는다(중간에 끊겨도 끝난 건은 남게).

## 4. 보고

```
SCOUT summary --run "<run_dir>"
```

사용자에게 짧게:
- 노션에 올린 건수(★★★ n / ★★ n)와 자동제외 건수(★, 표에 안 올림)
- ★★★ 공고 목록: 공고명 · 마감일 · 노션 링크
- 제안요청서를 못 읽은 건수 (`rfp_failed`) — 있으면 "노션에서 원문 직접 확인 필요"
- `overflow > 0`이면: "이번에 다 못 본 공고 n건 — 한 번 더 실행하면 이어서 분석"
- `warnings` 내용

## 반드시 지킬 것

- **제안요청서를 못 읽었으면 읽은 척하지 않는다.** `rfp_read: false`, 근거는 메타데이터로 한정하고 그렇게 적는다.
- 키·토큰 값을 출력하거나 대화·노션에 쓰지 않는다.
- 스크립트를 고치거나 우회하지 않는다. 오류가 나면 오류 메시지를 그대로 보고한다.
